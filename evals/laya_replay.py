#!/usr/bin/env python3
"""Replay saved Laya probabilities offline; never tune policy or call a model."""

import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/codex-model-router/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import laya_classifier as laya
import router
from evaluate import read_cases

CASES = Path(__file__).with_name("laya_cases.jsonl")
THRESHOLDS = (0.8, 0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.0)
LIMITS = (
    "Offline replay of recorded, adapter-validated probabilities, not new inference or "
    "revalidation of the original HTTP response. Authored stress cases are not representative "
    "or held-out calibration data. Matches include retention and fallback. No threshold "
    "is recommended; policy is unchanged. Recorded latency is from the original run."
)


def source_hashes():
    return {name: hashlib.sha256((SCRIPTS / name).read_bytes()).hexdigest()
            for name in ("router.py", "laya_classifier.py")}


def evidence(path, cases_path):
    report = json.loads(path.read_text(encoding="utf-8"))
    cases = {row["id"]: row for row in read_cases(cases_path)}
    if (not isinstance(report, dict) or report.get("schema_version") != 1
            or report.get("kind") != "local-classifier-comparison"):
        raise ValueError("Expected a version 1 local-classifier-comparison report")
    if report.get("source_sha256") != source_hashes():
        raise ValueError("Source hashes differ; replay requires the recorded router/classifier revision")
    if report.get("cases_sha256") != hashlib.sha256(cases_path.read_bytes()).hexdigest():
        raise ValueError("Corpus hash differs from the recorded run")
    laya.config({"model": report.get("checkpoint_requested"), "min_probability": report.get("threshold")})
    rows, summary = report.get("cases"), report.get("summary")
    if (not isinstance(rows, list) or not rows or not isinstance(summary, dict)
            or summary.get("requested") != len(rows) or summary.get("evaluated") != len(rows)):
        raise ValueError("Replay requires a complete nonempty comparison")
    selected, seen = [], set()
    for row in rows:
        case_id = row.get("id") if isinstance(row, dict) else None
        if not isinstance(case_id, str) or case_id not in cases or case_id in seen:
            raise ValueError("Unknown or duplicate case ID")
        seen.add(case_id)
        if row.get("expected") != cases[case_id]["expected"]:
            raise ValueError("Recorded expectation differs from the corpus")
        detail = row.get("classifier")
        if (not isinstance(detail, dict) or detail.get("backend") != "laya"
                or detail.get("mode") != "laya"
                or detail.get("status") not in ("recommended", "low_probability", "skipped")):
            raise ValueError("Replay supports complete active-mode comparisons without service errors or abstention")
        if detail["status"] != "skipped":
            if detail.get("checkpoint") != report["checkpoint_requested"] or detail.get("threshold") != report["threshold"]:
                raise ValueError("Per-case checkpoint or threshold differs from the report")
            elapsed = detail.get("elapsed_ms")
            if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
                raise ValueError("Invalid recorded elapsed time")
        selected.append(cases[case_id])
    return report, selected


def recorded_answer(detail, checkpoint):
    # The source report retained probabilities, not raw HTTP or usage metadata.
    # Reconstruct only the adapter's accepted probability contract for replay.
    return {"routing": {"model": checkpoint},
            "usage": {"truncated": False, "state_tokens_dropped": 0},
            "answers": {"profile": {"type": "choice", "choice": detail.get("profile") or "retain",
                        "probabilities": detail.get("probabilities"),
                        "answer_confidence": detail.get("probability")}}}


async def replay(report, cases, threshold, mode="laya"):
    cfg = laya.config({"mode": mode, "model": report["checkpoint_requested"], "min_probability": threshold})
    results = []
    for case, saved in zip(cases, report["cases"]):
        detail = saved["classifier"]
        if detail["status"] != "skipped":
            laya.recommendation(recorded_answer(detail, cfg["model"]), cfg)

        async def request(settings, payload):
            if detail["status"] == "skipped":
                raise ValueError("A previously skipped case now requires inference")
            return recorded_answer(detail, cfg["model"])

        followup = "previous" in case
        previous = case.get("previous")
        raw_rules = router.classify(case["prompt"])
        decision, record = await laya.classify(case["prompt"], {"classifier": cfg}, raw_rules,
                                               laya.LayaClient(request=request), previous, followup)
        rules = router.selective_phase(case["prompt"], previous, decision=raw_rules) if followup else raw_rules
        effective = router.selective_phase(case["prompt"], previous, decision=decision) if followup else decision
        results.append({"id": case["id"], "expected": case["expected"], "rules": rules[0],
                        "effective": effective[0], "status": record["status"], "used": record["used"]})
    return results


def summarize(rows, threshold):
    return {"threshold": threshold,
            "recommended": sum(row["status"] == "recommended" for row in rows),
            "effective_matches": sum(row["effective"] == row["expected"] for row in rows),
            "recommended_effective_matches": sum(row["used"] and row["effective"] == row["expected"] for row in rows),
            "improved_over_rules": [row["id"] for row in rows if row["rules"] != row["expected"] and row["effective"] == row["expected"]],
            "regressed_from_rules": [row["id"] for row in rows if row["rules"] == row["expected"] and row["effective"] != row["expected"]],
            "recommendation_errors": [row["id"] for row in rows if row["used"] and row["effective"] != row["expected"]]}


async def analyze(report, cases, thresholds):
    baseline = await replay(report, cases, report["threshold"])
    for row, saved in zip(baseline, report["cases"]):
        if (row["rules"] != saved.get("rules") or row["effective"] != saved.get("effective_with_laya")
                or row["status"] != saved["classifier"]["status"] or row["used"] != saved["classifier"].get("used")):
            raise ValueError("Original threshold does not reproduce the saved decisions")
    shadow = await replay(report, cases, report["threshold"], mode="shadow")
    if any(row["used"] or row["effective"] != row["rules"] for row in shadow):
        raise ValueError("Shadow replay changed a rule decision")
    responses = [row["classifier"] for row in report["cases"] if row["classifier"]["status"] != "skipped"]
    probability_values = [row["probability"] for row in responses]
    times = [row["elapsed_ms"] for row in responses]
    return {"schema_version": 1, "kind": "offline-laya-threshold-replay", "limits": LIMITS,
            "cases_sha256": report["cases_sha256"], "source_sha256": report["source_sha256"],
            "recorded_at": report["recorded_at"], "checkpoint": report["checkpoint_requested"],
            "cases": len(cases), "responses": len(responses), "skipped": len(cases) - len(responses),
            "probability_range": [min(probability_values), max(probability_values)] if responses else None,
            "recorded_median_ms": median(times) if times else None, "recorded_max_ms": max(times) if times else None,
            "rules_matches": sum(row["rules"] == row["expected"] for row in baseline),
            "shadow_matches": sum(row["effective"] == row["expected"] for row in shadow),
            "thresholds": [summarize(await replay(report, cases, threshold), threshold) for threshold in thresholds]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--threshold", type=float, action="append", help="Repeat to inspect specific cutoffs")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        thresholds = args.threshold if args.threshold is not None else THRESHOLDS
        for threshold in thresholds:
            laya.config({"min_probability": threshold})
        report, cases = evidence(args.report, args.cases)
        result = asyncio.run(analyze(report, cases, thresholds))
        result["report_sha256"] = hashlib.sha256(args.report.read_bytes()).hexdigest()
        if args.json:
            print(json.dumps(result, indent=2, allow_nan=False))
        else:
            print(f"Cases: {result['cases']}; model responses: {result['responses']}; skipped: {result['skipped']}")
            print(f"Rules: {result['rules_matches']}/{result['cases']}; shadow: {result['shadow_matches']}/{result['cases']}")
            print("Threshold | Accepted recommendations | Final rubric matches | Wrong accepted recommendations")
            for row in result["thresholds"]:
                print(f"{row['threshold']:.2f} | {row['recommended']} | {row['effective_matches']} | {len(row['recommendation_errors'])}")
            print(LIMITS)
        return 0
    except (OSError, ValueError, KeyError, TypeError, laya.ClassifierFailure) as error:
        print("Laya replay: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

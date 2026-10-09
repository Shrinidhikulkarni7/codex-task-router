#!/usr/bin/env python3
"""Compare local Laya with routing rules. Offline unless --run is supplied."""

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/codex-model-router/scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import router
import laya_classifier as laya
from evaluate import read_cases

CASES = Path(__file__).with_name("laya_cases.jsonl")


async def evaluate(cases, settings, client, report, output):
    for case in cases:
        previous = case.get("previous")
        followup = "previous" in case
        rules = router.classify(case["prompt"])
        decision, details = await laya.classify(case["prompt"], settings, rules, client, previous, followup)
        if followup:
            rules = router.selective_phase(case["prompt"], previous, decision=rules)
            decision = router.selective_phase(case["prompt"], previous, decision=decision)
        record = {"id": case["id"], "expected": case["expected"], "rules": rules[0],
                  "effective_with_laya": decision[0], "classifier": details,
                  "rules_match": rules[0] == case["expected"], "effective_match": decision[0] == case["expected"]}
        report["cases"].append(record)
        report["summary"] = {
            "evaluated": len(report["cases"]), "requested": len(cases),
            "rules_matches": sum(row["rules_match"] for row in report["cases"]),
            "effective_matches_including_fallbacks": sum(row["effective_match"] for row in report["cases"]),
            "usable_recommendations": sum(row["classifier"]["status"] == "recommended" for row in report["cases"]),
        }
        output.seek(0)
        json.dump(report, output, indent=2, allow_nan=False)
        output.truncate()
        output.flush()
        print(f"{case['id']}: rules={rules[0]}, with_laya={decision[0]}, {details['status']}", flush=True)
        if details["status"] == "error" or details.get("reason") in ("service_busy", "service_cooldown"):
            return 2
    return int(any(not row["effective_match"] for row in report["cases"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Send cases to the local Laya service; never starts Codex")
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--case", action="append", help="Select a case ID; repeat for multiple cases")
    parser.add_argument("--output", type=Path, help="New private report, required with --run")
    parser.add_argument("--checkpoint", help="Override the configured Laya checkpoint")
    parser.add_argument("--threshold", type=float, help="Override the provisional probability threshold")
    args = parser.parse_args(argv)
    if args.run and not args.output:
        parser.error("--run requires --output")
    try:
        cases = read_cases(args.cases)
        if args.case:
            wanted = set(args.case)
            unknown = wanted - {case["id"] for case in cases}
            if unknown:
                raise ValueError("Unknown case IDs: " + ", ".join(sorted(unknown)))
            cases = [case for case in cases if case["id"] in wanted]
        if not args.run:
            for case in cases:
                rules = router.selective_phase(case["prompt"], case["previous"]) if "previous" in case else router.classify(case["prompt"])
                print(f"{case['id']}: expected={case['expected']}, rules={rules[0]}")
            print("Offline listing only. --run performs local Laya inference; no Codex inference.")
            return 0
        settings = router.policy()
        cfg = laya.config(settings.get("classifier"))
        cfg["mode"] = "laya"  # Simulated effective selection; no live Codex routing.
        if args.checkpoint is not None:
            cfg["model"] = args.checkpoint
        if args.threshold is not None:
            cfg["min_probability"] = args.threshold
        settings["classifier"] = laya.config(cfg)
        report = {"schema_version": 1, "kind": "local-classifier-comparison",
                  "recorded_at": datetime.now(timezone.utc).isoformat(),
                  "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
                  "checkpoint_requested": cfg["model"], "threshold": cfg["min_probability"],
                  "source_sha256": {name: hashlib.sha256((ROOT / "skills/codex-model-router/scripts" / name).read_bytes()).hexdigest()
                                    for name in ("router.py", "laya_classifier.py")},
                  "limits": "Authored routing rubric. Effective matches include retention/fallbacks, not model accuracy. No Codex inference, task-quality, latency-on-other-hardware or cost claim. Probability threshold is uncalibrated for this workload.",
                  "cases": []}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            return asyncio.run(evaluate(cases, settings, laya.LayaClient(), report, output))
    except (OSError, ValueError, router.RouterError) as error:
        print("Laya comparison: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

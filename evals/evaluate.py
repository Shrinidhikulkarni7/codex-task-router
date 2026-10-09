#!/usr/bin/env python3
"""Offline agreement with an authored routing rubric; never a model benchmark."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "skills/codex-model-router/scripts/router.py"
CASES = Path(__file__).with_name("routing_cases.jsonl")


def load_router(ref=None):
    if ref:
        # Only explicitly requested local repository revisions are executed.
        revision = subprocess.check_output(
            ["git", "rev-parse", "--verify", "--end-of-options", ref + "^{commit}"], cwd=ROOT, text=True).strip()
        source = subprocess.check_output(
            ["git", "show", revision + ":skills/codex-model-router/scripts/router.py"], cwd=ROOT, text=True)
    else:
        revision, source = "working-tree", ROUTER.read_text(encoding="utf-8")
    module = ModuleType("evaluated_router")
    module.__file__ = str(ROUTER)
    exec(compile(source, str(ROUTER), "exec"), module.__dict__)
    return module, {"revision": revision, "source_sha256": hashlib.sha256(source.encode()).hexdigest()}


def read_cases(path):
    cases, seen = [], set()
    profiles = {"precheck", "easy", "coding", "review", "planning", "debugging", "deep-debug", "terra"}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        required = {"id", "category", "prompt", "expected", "why"}
        if not isinstance(row, dict) or not required <= row.keys() or row.keys() - required - {"previous"}:
            raise ValueError(f"Invalid evaluation case at line {number}")
        if any(not isinstance(row[key], str) or not row[key] for key in required - {"expected"}):
            raise ValueError(f"Case strings must be nonempty at line {number}")
        if row["expected"] is not None and (not isinstance(row["expected"], str) or row["expected"] not in profiles):
            raise ValueError(f"Unknown expected profile at line {number}")
        if "previous" in row and (not isinstance(row["previous"], str) or row["previous"] not in profiles):
            raise ValueError(f"Unknown previous profile at line {number}")
        if row["id"] in seen:
            raise ValueError("Duplicate case ID: " + row["id"])
        seen.add(row["id"])
        cases.append(row)
    if not cases:
        raise ValueError("Evaluation set is empty")
    return cases


def evaluate(module, cases):
    results, categories = [], {}
    for case in cases:
        if "previous" in case:
            actual, reason = module.selective_phase(case["prompt"], case["previous"])
        else:
            actual, reason = module.classify(case["prompt"])
        matched = actual == case["expected"]
        category = categories.setdefault(case["category"], {"cases": 0, "matched": 0})
        category["cases"] += 1
        category["matched"] += int(matched)
        results.append({"id": case["id"], "expected": case["expected"], "actual": actual,
                        "matched": matched, "reason": reason})
    return {"cases": len(results), "matched": sum(r["matched"] for r in results),
            "by_category": categories, "results": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--baseline-ref", help="Execute the classifier from this trusted local Git revision for comparison")
    parser.add_argument("--json", action="store_true", help="Print detailed JSON without prompt text")
    args = parser.parse_args(argv)
    try:
        cases = read_cases(args.cases)
        module, source = load_router()
        current = dict(evaluate(module, cases), **source)
        report = {"schema_version": 1, "kind": "authored-routing-rubric",
                  "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
                  "current": current,
                  "limits": "Synthetic cases used for development; agreement is not held-out accuracy, task success, cost savings, or inference evidence."}
        if args.baseline_ref:
            old, old_source = load_router(args.baseline_ref)
            report["baseline"] = dict(evaluate(old, cases), **old_source)
            old_by_id = {row["id"]: row for row in report["baseline"]["results"]}
            report["improved"] = [r["id"] for r in current["results"] if r["matched"] and not old_by_id[r["id"]]["matched"]]
            report["regressed"] = [r["id"] for r in current["results"] if not r["matched"] and old_by_id[r["id"]]["matched"]]
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            if "baseline" in report:
                print(f"Baseline: {report['baseline']['matched']}/{len(cases)} rubric matches")
            print(f"Current: {current['matched']}/{len(cases)} rubric matches")
            for row in current["results"]:
                if not row["matched"]:
                    print(f"  {row['id']}: expected {row['expected']!r}, got {row['actual']!r}")
            if "regressed" in report:
                print(f"Improved: {len(report['improved'])}; regressed: {len(report['regressed'])}")
            print(report["limits"])
        return int(current["matched"] != len(cases))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("Routing evaluation: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Opt-in answer checks using native Codex exec; listing cases is offline."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/codex-model-router/scripts"))
import router

CASES = Path(__file__).with_name("quality_cases.json")
ANSWER_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}},
                 "required": ["answer"], "additionalProperties": False}


def read_cases():
    value = json.loads(CASES.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("cases"), list) or not value["cases"]:
        raise ValueError("Invalid quality-case file")
    seen = set()
    for case in value["cases"]:
        if (not isinstance(case, dict) or set(case) != {"id", "prompt", "expected"}
                or not isinstance(case["id"], str) or not case["id"] or case["id"] in seen
                or not isinstance(case["prompt"], str) or not case["prompt"]
                or not isinstance(case["expected"], dict) or set(case["expected"]) != {"answer"}
                or not isinstance(case["expected"]["answer"], str)):
            raise ValueError("Invalid or duplicate quality case")
        seen.add(case["id"])
    return value["cases"]


def grade(case, answer):
    # No generated code is executed. Exact, intentionally bounded answer checks.
    return isinstance(answer, dict) and answer == case["expected"]


def reported_usage(events):
    latest = None
    for line in events.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("type") != "turn.completed":
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            continue
        fields = ("input_tokens", "cached_input_tokens", "output_tokens")
        counters = {key: usage[key] for key in fields if type(usage.get(key)) is int and 0 <= usage[key] <= 2**63 - 1}
        if counters:
            latest = counters
    return latest


def run_case(case, choice, codex, timeout, execute=subprocess.run):
    record = {"id": case["id"], "requested_model": choice["model"], "requested_effort": choice["effort"],
              "profile": choice.get("profile"), "status": "not_started"}
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="codex-router-quality-") as directory:
        root = Path(directory)
        schema, answer_path = root / "answer-schema.json", root / "answer.json"
        schema.write_text(json.dumps(ANSWER_SCHEMA), encoding="utf-8")
        argv = [codex, "exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
                "--model", choice["model"], "-c", "model_reasoning_effort=" + json.dumps(choice["effort"]),
                "--cd", str(root), "--output-schema", str(schema), "--output-last-message", str(answer_path),
                "--json", "--", case["prompt"]]
        try:
            result = execute(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
            record.update(returncode=result.returncode, reported_usage=reported_usage(result.stdout))
            if result.returncode:
                record.update(status="execution_error", error=result.stderr[-1200:])
            elif not answer_path.is_file() or answer_path.stat().st_size > 65536:
                record.update(status="invalid_answer", error="Final answer missing or larger than 64 KiB")
            else:
                try:
                    answer = json.loads(answer_path.read_text(encoding="utf-8"))
                    record.update(status="passed" if grade(case, answer) else "failed", answer=answer)
                except (ValueError, UnicodeError):
                    record.update(status="invalid_answer", error="Final answer was not valid UTF-8 JSON")
        except subprocess.TimeoutExpired:
            # Stop the benchmark; daemon-owned work can outlive a CLI timeout.
            record.update(status="timeout", error="CLI timed out; daemon completion and final usage are unknown")
        except OSError as error:
            record.update(status="execution_error", error=str(error)[:1200])
    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Start real model inference; otherwise list cases only")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--case", action="append", help="Case ID; repeat to select more than one")
    selection.add_argument("--all", action="store_true", help="Select all seven cases")
    parser.add_argument("--output", type=Path, help="New private JSON report; required with --run")
    parser.add_argument("--model", help="Fixed-model comparison instead of automatic initial selection")
    parser.add_argument("--effort", choices=router.EFFORTS, help="Required with --model")
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")), help="Catalog cache only; set CODEX_HOME separately for Codex runtime")
    parser.add_argument("--timeout", type=int, default=120, help="Seconds per case; stop on timeout or execution error")
    args = parser.parse_args(argv)
    if args.timeout < 1 or args.timeout > 600:
        parser.error("--timeout must be between 1 and 600 seconds")
    if bool(args.model) != bool(args.effort):
        parser.error("--model and --effort must be supplied together")
    if args.run and (not args.output or not (args.case or args.all)):
        parser.error("--run requires --output and either --case ID or --all")
    try:
        cases = read_cases()
        wanted = set(args.case or [case["id"] for case in cases])
        if wanted - {case["id"] for case in cases}:
            raise ValueError("Unknown case IDs: " + ", ".join(sorted(wanted - {case["id"] for case in cases})))
        cases = [case for case in cases if case["id"] in wanted]
        if not args.run:
            for case in cases:
                profile, reason = router.classify(case["prompt"])
                print(f"{case['id']}: {profile} ({reason})")
            print("Offline listing only. --run starts real Codex inference and consumes normal usage.")
            return 0
        settings, catalog = router.policy(), router.cached_catalog(args.codex_home)
        if not settings["enabled"] and not args.model:
            raise ValueError("Routing is disabled; choose a fixed --model/--effort or enable policy")
        choices = []
        for case in cases:
            profile, _ = router.classify(case["prompt"])
            if profile is None and not args.model:
                raise ValueError("No fresh-task selection for " + case["id"])
            choices.append(router.select_model(profile, catalog, settings, model=args.model, effort=args.effort))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        report = {"schema_version": 1, "kind": "bounded-answer-checks", "selection": "fixed" if args.model else "router",
                  "limits": "Seven small synthetic tasks, separate native exec sessions. Not a proxy/cache benchmark, model ranking, billing meter, or verification of broad engineering quality. Requested models are not independent backend attribution.",
                  "cases": []}
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            for case, choice in zip(cases, choices):
                print(f"Running {case['id']}: {choice['model']} / {choice['effort']}", flush=True)
                record = run_case(case, choice, args.codex, args.timeout)
                report["cases"].append(record)
                output.seek(0)
                json.dump(report, output, indent=2)
                output.truncate()
                output.flush()
                print(f"  {record['status']} ({record['elapsed_seconds']}s)", flush=True)
                if record["status"] in ("timeout", "execution_error"):
                    break
        return int(len(report["cases"]) != len(cases) or any(r["status"] != "passed" for r in report["cases"]))
    except (OSError, ValueError, router.RouterError) as error:
        print("Task quality check: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

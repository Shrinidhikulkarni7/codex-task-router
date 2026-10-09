"""Evaluation integrity and an inference-free test of the opt-in quality runner."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evaluate = load("routing_evaluation", ROOT / "evals/evaluate.py")
quality = load("quality_evaluation", ROOT / "evals/task_quality.py")


class RubricTests(unittest.TestCase):
    def test_clause_boundaries_do_not_promote_quoted_actions_to_instructions(self):
        module, _ = evaluate.load_router()
        for prompt, expected in (
            ('Summarize the sentence "implement a compiler; investigate a deadlock".', "easy"),
            ('Explain the phrase "plan a database; investigate a deadlock" in one sentence.', "easy"),
            ('"Investigate a deadlock. Implement a compiler."', None),
            ("Summarize `implement a compiler; investigate a deadlock`.", "easy"),
            ("Summarize the logs, diagnose the crash.", "debugging"),
            ("Don't debug it; explain deadlocks in one sentence.", "easy"),
        ):
            with self.subTest(prompt=prompt):
                self.assertEqual(module.classify(prompt)[0], expected)

    def test_report_counts_mismatches_and_retention_without_prompt_text(self):
        module, _ = evaluate.load_router()
        cases = [
            {"id": "a", "category": "definition", "prompt": "Explain deadlocks in one sentence", "expected": "easy"},
            {"id": "b", "category": "retention", "prompt": "Run tests", "previous": "coding", "expected": None},
            {"id": "c", "category": "intentional-error", "prompt": "Implement pagination", "expected": "easy"},
        ]
        report = evaluate.evaluate(module, cases)
        self.assertEqual((report["matched"], report["cases"]), (2, 3))
        self.assertEqual(report["by_category"]["intentional-error"]["matched"], 0)
        self.assertNotIn("Implement pagination", json.dumps(report))

    def test_empty_duplicate_and_invalid_rubrics_fail_validation(self):
        good = {"id": "a", "category": "c", "prompt": "List files", "expected": "easy", "why": "small"}
        values = ["", json.dumps(good) + "\n" + json.dumps(good), json.dumps(dict(good, expected=[])),
                  json.dumps(dict(good, previous={})), json.dumps(dict(good, expected="typo"))]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.jsonl"
            for value in values:
                path.write_text(value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    evaluate.read_cases(path)

    def test_offline_cli_checks_the_full_authored_corpus(self):
        result = subprocess.run([sys.executable, str(ROOT / "evals/evaluate.py"), "--json"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["current"]["matched"], report["current"]["cases"])
        self.assertEqual(report["kind"], "authored-routing-rubric")
        self.assertNotIn("baseline", report)


class QualityTests(unittest.TestCase):
    choice = {"profile": "easy", "model": "fixture-model", "effort": "medium"}

    def test_offline_listing_does_not_open_catalog_or_launch_codex(self):
        with patch.object(quality.router, "cached_catalog", side_effect=AssertionError("No catalog needed")), patch.object(quality, "run_case", side_effect=AssertionError("No inference allowed")), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(quality.main([]), 0)
        self.assertIn("Offline listing only", output.getvalue())

    def test_graders_reject_wrong_and_extra_answers(self):
        for case in quality.read_cases():
            self.assertTrue(quality.grade(case, case["expected"]))
            self.assertFalse(quality.grade(case, {"answer": "wrong"}))
            self.assertFalse(quality.grade(case, dict(case["expected"], extra=True)))
            self.assertFalse(quality.grade(case, None))

    def test_run_uses_private_temporary_directory_and_preserves_codex_guards(self):
        case = quality.read_cases()[0]

        def execute(argv, **kwargs):
            self.assertEqual(argv[1], "exec")
            self.assertIn("--ephemeral", argv)
            self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
            self.assertNotIn("--ignore-user-config", argv)
            self.assertNotIn("--ignore-rules", argv)
            self.assertEqual(argv[-2:], ["--", case["prompt"]])
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(kwargs["timeout"], 12)
            root = Path(argv[argv.index("--cd") + 1])
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertNotIn("expected", " ".join(p.read_text() for p in root.iterdir()))
            Path(argv[argv.index("--output-last-message") + 1]).write_text(json.dumps(case["expected"]))
            return subprocess.CompletedProcess(argv, 0, json.dumps({"type": "turn.completed", "usage": {"input_tokens": 200, "output_tokens": 20}}), "")

        record = quality.run_case(case, self.choice, "fixture-codex", 12, execute=execute)
        self.assertEqual(record["status"], "passed")
        self.assertEqual(record["reported_usage"], {"input_tokens": 200, "output_tokens": 20})
        self.assertEqual(record["requested_model"], "fixture-model")

    def test_timeout_execution_failure_and_missing_answer_are_not_success(self):
        case = quality.read_cases()[0]
        with self.subTest("timeout"):
            def timeout(*args, **kwargs):
                raise subprocess.TimeoutExpired("fixture", 1)
            self.assertEqual(quality.run_case(case, self.choice, "fixture", 1, execute=timeout)["status"], "timeout")
        for code, status in ((1, "execution_error"), (0, "invalid_answer")):
            record = quality.run_case(case, self.choice, "fixture", 1, execute=lambda *args, **kwargs: subprocess.CompletedProcess([], code, "", "fixture error"))
            self.assertEqual(record["status"], status)

    def test_unknown_or_malformed_usage_does_not_become_zero_usage(self):
        self.assertIsNone(quality.reported_usage("not json\n{}"))
        event = {"type": "turn.completed", "usage": {"input_tokens": True, "output_tokens": -1, "prompt": "private"}}
        self.assertIsNone(quality.reported_usage(json.dumps(event)))

    def test_output_is_private_errors_stop_the_run_and_existing_files_are_preserved(self):
        catalog = [{"model": "fixture-model", "supportedReasoningEfforts": [{"reasoningEffort": "medium"}]}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            args = ["--run", "--all", "--model", "fixture-model", "--effort", "medium", "--output", str(path)]
            with patch.object(quality.router, "cached_catalog", return_value=catalog), patch.object(quality, "run_case", return_value={"status": "execution_error", "elapsed_seconds": 0}) as run, redirect_stdout(io.StringIO()):
                self.assertEqual(quality.main(args), 1)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                saved = path.read_bytes()
                with patch.object(sys, "stderr", io.StringIO()):
                    self.assertEqual(quality.main(args), 2)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(path.read_bytes(), saved)


if __name__ == "__main__":
    unittest.main()

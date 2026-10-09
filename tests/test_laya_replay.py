"""Saved evidence must replay without inference, policy edits, or silent drift."""

import asyncio
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
import laya_replay as replay


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "report.json"
        rows = []
        for case_id, profile, probability, expected, rules in (
            ("invoice-download", "coding", 0.6, "coding", None),
            ("followup-approved", "planning", 0.7, "coding", "coding"),
            ("acknowledgment", None, None, None, None),
        ):
            detail = {"backend": "laya", "mode": "laya", "used": False}
            if profile is None:
                detail.update(status="skipped", reason="brief_continuation")
            else:
                detail.update(status="low_probability", checkpoint="typed-decisions", threshold=0.8,
                              profile=profile, probability=probability, elapsed_ms=80,
                              probabilities={key: probability if key == profile else (1 - probability) / 7
                                             for key in replay.laya.CRITERIA})
            rows.append({"id": case_id, "expected": expected, "rules": rules,
                         "effective_with_laya": None, "classifier": detail})
        self.report = {"schema_version": 1, "kind": "local-classifier-comparison",
                       "source_sha256": replay.source_hashes(),
                       "cases_sha256": hashlib.sha256(replay.CASES.read_bytes()).hexdigest(),
                       "checkpoint_requested": "typed-decisions", "threshold": 0.8,
                       "recorded_at": "2026-10-09T00:00:00+00:00", "cases": rows,
                       "summary": {"requested": 3, "evaluated": 3}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report))

    def test_replays_retention_and_shadow_without_network_or_policy_changes(self):
        policy = ROOT / "skills/codex-model-router/policy.json"
        before = policy.read_bytes()
        with patch.object(asyncio, "open_connection", side_effect=AssertionError("Network forbidden")):
            report, cases = replay.evidence(self.path, replay.CASES)
            result = asyncio.run(replay.analyze(report, cases, (0.8, 0.5)))
        self.assertEqual(result["responses"], 2)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["rules_matches"], 2)
        self.assertEqual(result["shadow_matches"], 2)
        self.assertEqual(result["thresholds"][0]["effective_matches"], 1)
        self.assertEqual(result["thresholds"][0]["regressed_from_rules"], ["followup-approved"])
        self.assertEqual(result["thresholds"][1]["recommended"], 2)
        self.assertEqual(result["thresholds"][1]["effective_matches"], 2)
        self.assertEqual(result["thresholds"][1]["recommendation_errors"], ["followup-approved"])
        self.assertEqual(policy.read_bytes(), before)

    def test_refuses_source_corpus_and_case_drift(self):
        original = deepcopy(self.report)
        for mutation in (lambda r: r["source_sha256"].update({"router.py": "changed"}),
                         lambda r: r.update(cases_sha256="changed"),
                         lambda r: r["cases"][0].update(expected="easy"),
                         lambda r: r["cases"][1].update(id="invoice-download"),
                         lambda r: r["summary"].update(requested=4)):
            self.report = deepcopy(original)
            mutation(self.report)
            self.save()
            with self.assertRaises(ValueError):
                replay.evidence(self.path, replay.CASES)

    def test_refuses_unreproducible_decisions_and_invalid_probabilities(self):
        self.report["cases"][0]["effective_with_laya"] = "coding"
        self.save()
        report, cases = replay.evidence(self.path, replay.CASES)
        with self.assertRaisesRegex(ValueError, "does not reproduce"):
            asyncio.run(replay.analyze(report, cases, (0.5,)))
        self.report["cases"][0]["effective_with_laya"] = None
        self.report["cases"][0]["classifier"]["probabilities"]["coding"] = -1
        self.save()
        report, cases = replay.evidence(self.path, replay.CASES)
        with self.assertRaises(replay.laya.ClassifierFailure):
            asyncio.run(replay.analyze(report, cases, (0.5,)))

    def test_cli_outputs_json_and_reports_invalid_threshold(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(replay.main([str(self.path), "--threshold", "0.5", "--json"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["report_sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertNotIn("Can you make it possible", output.getvalue())
        with redirect_stderr(io.StringIO()):
            self.assertEqual(replay.main([str(self.path), "--threshold", "nan"]), 2)


if __name__ == "__main__":
    unittest.main()

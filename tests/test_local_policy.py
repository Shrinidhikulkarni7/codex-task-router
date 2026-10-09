"""Personal settings must preserve defaults and fail before submitting work."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_router import router


class LocalPolicyTests(unittest.TestCase):
    def setUp(self):
        self.defaults = router.policy(include_local=False)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.base = self.root / "policy.json"
        self.base.write_text(json.dumps(self.defaults))
        self.local = self.root / "policy.local.json"
        patcher = patch.object(router, "SKILL", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_partial_nested_overrides_preserve_defaults_and_replace_arrays(self):
        before = self.base.read_bytes()
        self.local.write_text(json.dumps({"classifier": {"mode": "shadow"},
                                         "profiles": {"coding": {"models": ["custom-model"]}}}))
        effective = router.policy()
        self.assertEqual(effective["classifier"]["mode"], "shadow")
        self.assertEqual(effective["profiles"]["coding"], {"models": ["custom-model"], "effort": "medium"})
        self.assertEqual(effective["profiles"]["planning"], self.defaults["profiles"]["planning"])
        self.assertEqual(router.policy(include_local=False), self.defaults)
        self.assertEqual(self.base.read_bytes(), before)
        self.local.unlink()
        self.assertEqual(router.policy(), self.defaults)

    def test_invalid_overrides_stop_before_launch_without_traceback(self):
        for raw in ('[]', '{', '{"routing_mode":"typo"}', '{"profiles":{"coding":{"effort":null}}}',
                    '{"classifier":{"mode":"typo"}}', '{"unknown":true}'):
            with self.subTest(raw=raw):
                self.local.write_text(raw)
                stderr = io.StringIO()
                with patch.object(router.subprocess, "call") as launch, redirect_stderr(stderr):
                    self.assertEqual(router.main(["run", "Implement pagination"]), 1)
                launch.assert_not_called()
                self.assertIn("policy.local.json", stderr.getvalue())
                self.assertNotIn("Traceback", stderr.getvalue())

    def test_config_reports_effective_values_without_daemon_or_secret_access(self):
        self.local.write_text('{"routing_mode":"task", "classifier":{"mode":"shadow"}}')
        output = io.StringIO()
        with patch.object(router, "Rpc", side_effect=AssertionError("No connection")), \
                patch.dict(router.os.environ, {"LAYA_API_KEY": "secret sentinel"}), redirect_stdout(output):
            self.assertEqual(router.main(["config"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["policy"]["routing_mode"], "task")
        self.assertEqual(result["policy"]["classifier"]["timeout_ms"], 2000)
        self.assertTrue(result["local_override_loaded"])
        self.assertNotIn("secret sentinel", output.getvalue())


if __name__ == "__main__":
    unittest.main()

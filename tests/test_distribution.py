"""Public artifacts must be reproducible, independent, and free of local state."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_skill", ROOT / "scripts/build_skill.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class DistributionTests(unittest.TestCase):
    def test_bundle_excludes_private_files_and_runs_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "source"
            for name in builder.FILES:
                target = skill / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(builder.SKILL / name, target)
            (skill / "policy.local.json").write_text('{"enabled": false}')
            (skill / "private-report.json").write_text("private sentinel")
            state = skill / ".router-state"
            state.mkdir()
            (state / "run.json").write_text("private sentinel")
            first = builder.build(root / "one", skill)
            second = builder.build(root / "two", skill)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            digest = hashlib.sha256(first.read_bytes()).hexdigest()
            self.assertEqual((first.parent / "SHA256SUMS").read_text(), f"{digest}  {first.name}\n")
            with zipfile.ZipFile(first) as bundle:
                self.assertEqual(set(bundle.namelist()), {"codex-model-router/" + name for name in builder.FILES})
                bundle.extractall(root / "installed")
            script = root / "installed/codex-model-router/scripts/router.py"
            result = subprocess.run([sys.executable, str(script), "config"], cwd=root,
                                    capture_output=True, text=True, timeout=10, check=True)
            config = json.loads(result.stdout)
            self.assertTrue(config["policy"]["enabled"])
            self.assertEqual(config["policy"]["classifier"]["mode"], "rules")
            self.assertFalse(config["local_override_loaded"])
            self.assertEqual((builder.SKILL / "LICENSE.txt").read_bytes(), (ROOT / "LICENSE").read_bytes())

    def test_bundle_refuses_symlinked_manifest_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "LICENSE.txt").symlink_to(builder.SKILL / "LICENSE.txt")
            with self.assertRaisesRegex(ValueError, "regular distribution file"):
                builder.build(root / "out", root)


if __name__ == "__main__":
    unittest.main()

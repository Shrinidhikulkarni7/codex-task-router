#!/usr/bin/env python3
"""Run repository checks offline, isolated from personal router configuration."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

from build_skill import FILES, ROOT, SKILL


def check_links():
    documents = [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md"), *SKILL.rglob("*.md")]
    count = 0
    for document in documents:
        body = re.sub(r"^```.*?^```[^\n]*$", "", document.read_text(encoding="utf-8"), flags=re.M | re.S)
        for target in re.findall(r"\]\(([^)\s]+)\)", body):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            path = (document.parent / unquote(parsed.path)).resolve()
            if not path.exists():
                raise ValueError(f"Broken file link in {document.relative_to(ROOT)}: {target}")
            if document.is_relative_to(SKILL) and not path.is_relative_to(SKILL):
                raise ValueError(f"Skill reference escapes its distributable: {target}")
            count += 1
    print(f"Documentation: {count} local file links checked (external URLs and anchors not checked).", flush=True)


def run(root, *args):
    result = subprocess.run([sys.executable, "-B", "-W", "error::ResourceWarning", *args], cwd=root,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.rstrip(), flush=True)
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr, flush=True)
    if result.returncode:
        raise ValueError(f"Check failed ({result.returncode}): {' '.join(args)}")


def main():
    try:
        check_links()
        # Copy only test/runtime inputs, never a contributor's overrides, state,
        # model weights, private reports, authentication, or the media project.
        with tempfile.TemporaryDirectory(prefix="router-check-") as directory:
            root = Path(directory)
            inputs = [ROOT / "install.py", ROOT / "LICENSE", ROOT / "scripts/build_skill.py"]
            inputs += [SKILL / name for name in FILES]
            inputs += list((ROOT / "tests").glob("*.py"))
            inputs += [p for p in (ROOT / "evals").iterdir() if p.suffix in (".py", ".json", ".jsonl")]
            for source in inputs:
                destination = root / source.relative_to(ROOT)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                if source.suffix == ".py":
                    compile(source.read_bytes(), str(source), "exec")
            print("Python sources compile; testing an isolated copy with shipped defaults.", flush=True)
            run(root, "-m", "unittest", "discover", "-s", "tests", "-q")
            run(root, "evals/evaluate.py")
            # Both commands must remain offline listings unless --run is given.
            for command in (("install.py", "--help"),
                            ("skills/codex-model-router/scripts/router.py", "--help"),
                            ("evals/task_quality.py",), ("evals/laya_compare.py",)):
                result = subprocess.run([sys.executable, "-B", *command], cwd=root,
                                        capture_output=True, text=True, timeout=20)
                if result.returncode:
                    raise ValueError(result.stderr or "CLI entry-point check failed")
        print("Offline checks passed. No Codex or classifier inference was requested.")
        return 0
    except (OSError, ValueError, SyntaxError, subprocess.SubprocessError) as error:
        print(f"Repository check: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

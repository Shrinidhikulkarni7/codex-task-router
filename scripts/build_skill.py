#!/usr/bin/env python3
"""Build a reproducible skill-only ZIP from an explicit public file manifest."""

import argparse
import hashlib
import os
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/codex-model-router"
FILES = (
    "LICENSE.txt", "SKILL.md", "agents/openai.yaml", "policy.json",
    "references/configuration.md", "references/laya.md", "references/operations.md",
    "scripts/laya_classifier.py", "scripts/router.py", "scripts/session_proxy.py",
)


def build(output, skill=SKILL):
    # Never glob: local policy, diagnostics, bytecode, and newly added files must
    # not enter a distributable without an explicit manifest change.
    entries = []
    for name in sorted(FILES):
        path = skill / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Expected a regular distribution file: {path}")
        entries.append((name, path.read_bytes()))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "codex-model-router.zip"
    with tempfile.TemporaryDirectory(prefix="router-build-", dir=output) as directory:
        temporary = Path(directory) / archive.name
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as bundle:
            for name, data in entries:
                entry = zipfile.ZipInfo("codex-model-router/" + name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                bundle.writestr(entry, data)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        checksum = Path(directory) / "SHA256SUMS"
        checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
        os.replace(temporary, archive)
        os.replace(checksum, output / checksum.name)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        print(build(args.output_dir))
        return 0
    except (OSError, ValueError) as error:
        parser.exit(1, f"Skill build: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())

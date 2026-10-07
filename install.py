#!/usr/bin/env python3
"""Install the automatic router; optionally enable its legacy prompt hook."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile


SOURCE = Path(__file__).resolve().parent / "skills" / "codex-model-router"
NAME = "codex-model-router"


def atomic_write(path, text, original):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlinked hooks.json")
    mode = (path.stat().st_mode & 0o777) if path.exists() else 0o600
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current != original:
        raise ValueError("hooks.json changed during installation; retry")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, prefix=".router-hooks-") as f:
            temporary = Path(f.name)
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        temporary.chmod(mode)
        if path.is_symlink() or (path.read_text(encoding="utf-8") if path.exists() else None) != original:
            raise ValueError("hooks.json changed during installation; retry")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install(codex_home, uninstall=False, dry_run=False, legacy_hook=False):
    if uninstall and legacy_hook:
        raise ValueError("--uninstall cannot be combined with --legacy-hook")
    codex_home = Path(codex_home).expanduser().resolve()
    destination = codex_home / "skills" / NAME
    hooks_path = codex_home / "hooks.json"
    owned_link = destination.is_symlink() and destination.resolve() == SOURCE.resolve()
    if (destination.exists() or destination.is_symlink()) and not owned_link:
        raise ValueError(f"Skill path already exists and is not this installation: {destination}")
    # Auto only needs the skill link. Leave existing hook files byte-for-byte intact.
    change_hooks = legacy_hook or uninstall
    if change_hooks and hooks_path.is_symlink():
        raise ValueError("Refusing to replace a symlinked hooks.json")
    original = hooks_path.read_text(encoding="utf-8") if change_hooks and hooks_path.exists() else None
    data = json.loads(original) if original is not None else {}
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        raise ValueError("hooks.json must contain a hooks object")
    old_data = deepcopy(data)
    hooks = data.get("hooks", {})
    groups = hooks.get("UserPromptSubmit", [])
    if not isinstance(groups, list):
        raise ValueError("UserPromptSubmit must be an array")
    script = destination / "scripts" / "router.py"
    command = shlex.join([sys.executable, str(script), "hook"])

    def ours(handler):
        try:
            parts = shlex.split(handler.get("command", ""))
        except ValueError:
            return False
        return len(parts) == 3 and parts[1:] == [str(script), "hook"]

    merged = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            raise ValueError("Each UserPromptSubmit group must contain a hooks array")
        if not all(isinstance(h, dict) and isinstance(h.get("command", ""), str) for h in group["hooks"]):
            raise ValueError("Each UserPromptSubmit hook must be an object with a string command")
        kept = [h for h in group["hooks"] if not ours(h)]
        if kept or not group["hooks"]:
            merged.append(dict(group, hooks=kept))
    if legacy_hook:
        merged.append({"hooks": [{"type": "command", "command": command, "async": True, "timeout": 12, "statusMessage": "Selecting Codex model"}]})
        data["hooks"] = hooks
    if merged:
        hooks["UserPromptSubmit"] = merged
    else:
        hooks.pop("UserPromptSubmit", None)
    preview = {"action": "uninstall" if uninstall else "install", "skill": str(destination), "hooks": str(hooks_path),
               "hook_action": "remove-owned" if uninstall else ("install" if legacy_hook else "preserve"),
               "hook": merged[-1] if legacy_hook else None, "dry_run": dry_run}
    launch = shlex.join([sys.executable, str(script), "auto"])
    preview["next_step"] = ("Router removed; unrelated hooks preserved." if uninstall else
                            f"Run `{launch}` in your terminal for automatic routing on every new prompt.")
    if legacy_hook:
        preview["legacy_hook_next_step"] = "Run `codex features enable step_model_switching` in your terminal, start a new Codex session, and open /hooks to review/trust the optional UserPromptSubmit hook. Live changes remain subject to Codex compatibility checks."
    if dry_run:
        return preview
    made_link = False
    if not uninstall and not owned_link:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(SOURCE, target_is_directory=True)
        made_link = True
    try:
        if change_hooks and data != old_data and not (uninstall and original is None):
            if original is not None:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                backup = hooks_path.with_name("hooks.json.router-backup-" + stamp)
                descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                    file.write(original)
                preview["backup"] = str(backup)
            atomic_write(hooks_path, json.dumps(data, indent=2) + "\n", original)
    except Exception:
        if made_link and destination.is_symlink() and destination.resolve() == SOURCE.resolve():
            destination.unlink()
        raise
    if uninstall and owned_link:
        destination.unlink()
    return preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--uninstall", action="store_true", help="Remove this installation's link and legacy hook")
    mode.add_argument("--legacy-hook", action="store_true", help="Also install the optional live UserPromptSubmit hook; auto does not need it")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.codex_home, args.uninstall, args.dry_run, args.legacy_hook), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("Router installation: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Regressions for malformed input, installer ownership, and proxy lifecycle."""

import asyncio
from contextlib import redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_router import CATALOG, IsolatedStateTests, installer, router
from test_session_proxy import BufferWriter, MemoryRun, prompt, wire_pair
from session_proxy import Bridge, TurnRouter, WebSocket, choice_from


class PolicyTests(unittest.TestCase):
    def test_invalid_policy_shapes_are_actionable(self):
        original = router.policy(include_local=False)
        cases = [([], "object"), ({}, "enabled"), (dict(original, enabled=1), "enabled"),
                 (dict(original, typo=True), "Unknown policy"), (dict(original, profiles=[]), "profiles")]
        for field, value in (("models", "gpt-6-luna"), ("models", []), ("models", [""]),
                             ("models", ["white space"]), ("models", ["same", "same"]),
                             ("effort", "extra-high"), ("effort", {}), ("typo", "value")):
            config = deepcopy(original)
            config["profiles"]["easy"][field] = value
            cases.append((config, "policy.profiles.easy"))
        for key in ("unknown", "missing"):
            config = deepcopy(original)
            if key == "unknown":
                config["profiles"]["typo"] = config["profiles"]["easy"]
            else:
                del config["profiles"]["easy"]
            cases.append((config, "profiles"))
        for config, error in cases:
            with self.subTest(config=config), self.assertRaisesRegex(router.RouterError, error):
                router.validate_policy(config)

    def test_malformed_policy_cli_fails_cleanly_without_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "policy.json").write_text("[]")
            stderr = io.StringIO()
            with patch.object(router, "SKILL", root), patch.object(router.subprocess, "call") as launch, redirect_stderr(stderr):
                self.assertEqual(router.main(["run", "Implement pagination"]), 1)
            launch.assert_not_called()
            self.assertIn("must contain an object", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_malformed_catalog_and_rpc_responses_have_router_errors(self):
        for value in (None, {}, [None], [{"model": 1}], [{"model": "test", "supportedReasoningEfforts": {}}]):
            with self.subTest(value=value), self.assertRaises(router.RouterError):
                router.validate_catalog(value)
        for response in ([], {}, {"error": "bad"}, {"error": {"message": None}}):
            with self.subTest(response=response), self.assertRaises(router.RouterError):
                router.rpc_result(response, "fixture/method")
        with self.assertRaisesRegex(router.RouterError, "cursor"):
            router.catalog_page({"data": [], "nextCursor": ["invalid"]})

    def test_malformed_cache_never_causes_an_attribute_error(self):
        for cache in ([], {"models": "bad"}, {"models": [1]},
                      {"models": [{"slug": "test", "supported_reasoning_levels": "bad"}]}):
            with self.subTest(cache=cache), tempfile.TemporaryDirectory() as directory:
                (Path(directory) / "models_cache.json").write_text(json.dumps(cache))
                with self.assertRaises(router.RouterError):
                    router.cached_catalog(directory)

    def test_run_honors_cwd_for_routed_and_unchanged_tasks(self):
        for task in ("hello", "Implement pagination"):
            with self.subTest(task=task), patch.object(router, "cached_catalog", return_value=CATALOG), \
                    patch.object(router.subprocess, "call", return_value=0) as launch, redirect_stderr(io.StringIO()):
                self.assertEqual(router.main(["run", "--cwd", "/project with spaces", task]), 0)
                self.assertEqual(launch.call_args.args[0][:3], ["codex", "--cd", "/project with spaces"])


class StateOwnershipTests(IsolatedStateTests):
    def test_identical_prompts_have_separate_claim_ownership(self):
        first = router.claim_prompt("thread", "private task")
        second = router.claim_prompt("thread", "private task")
        self.assertNotEqual(first, second)
        first.unlink()  # Cleanup by the first bridge must not remove the second's claim.
        self.assertTrue(router.consume_prompt_claim("thread", "private task"))
        self.assertFalse(second.exists())
        self.assertEqual(router.STATE_DIR.stat().st_mode & 0o777, 0o700)

    def test_claims_are_consumed_once_even_with_repeated_prompts(self):
        for _ in range(2):
            router.claim_prompt("thread", "same task")
        self.assertTrue(router.consume_prompt_claim("thread", "same task"))
        self.assertTrue(router.consume_prompt_claim("thread", "same task"))
        self.assertFalse(router.consume_prompt_claim("thread", "same task"))

    def test_malformed_claims_do_not_suppress_hooks(self):
        path = router.claim_prompt("thread", "task")
        for value in ([], {"created_at": "bad", "pid": 1}, {"created_at": router.time.time(), "pid": True},
                      {"created_at": router.time.time(), "pid": 10**100},
                      {"created_at": 10**1000, "pid": router.os.getpid()}):
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                self.assertFalse(router.consume_prompt_claim("thread", "task"))

    def test_symlinked_state_is_not_written_or_pruned(self):
        outside = router.STATE_DIR.parent / "outside"
        outside.mkdir()
        for index in range(202):
            (outside / f"run-{index}.json").write_text("{}")
        router.STATE_DIR.symlink_to(outside, target_is_directory=True)
        run = router.HookRun()
        self.assertIn("not a symlink", run.error)
        self.assertEqual(len(list(outside.iterdir())), 202)
        with self.assertRaisesRegex(OSError, "not a symlink"):
            router.claim_prompt("thread", "task")
        with self.assertRaisesRegex(router.RouterError, "symlinked"):
            router.routing_status()

    def test_damaged_timestamp_does_not_break_status(self):
        router.STATE_DIR.mkdir()
        (router.STATE_DIR / "run-one.json").write_text('{"started_at": []}')
        (router.STATE_DIR / "run-two.json").write_text('{"started_at": "2026-01-01"}')
        self.assertEqual(len(router.routing_status()["runs"]), 2)


class InstallerSafetyTests(unittest.TestCase):
    def test_default_install_only_links_the_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = installer.install(root)
            self.assertTrue((root / "skills" / installer.NAME).is_symlink())
            self.assertFalse((root / "hooks.json").exists())
            self.assertEqual(result["hook_action"], "preserve")
            self.assertIn("auto", result["next_step"])
            installer.install(root, uninstall=True)
            self.assertFalse((root / "skills" / installer.NAME).exists())

    def test_default_install_preserves_existing_hook_bytes_even_if_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "hooks.json"
            path.write_text("# Existing file left untouched by auto installation")
            before = path.read_bytes()
            installer.install(root)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(root.glob("hooks.json.router-backup-*")), [])

    def test_default_rerun_keeps_an_owned_legacy_hook(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installer.install(root, legacy_hook=True)
            path = root / "hooks.json"
            before = path.read_bytes()
            installer.install(root)
            self.assertEqual(path.read_bytes(), before)

    def test_malformed_hook_groups_do_not_create_an_installation(self):
        for group in (None, {}, {"hooks": None}, {"hooks": [None]}, {"hooks": [{"command": 42}]}):
            with self.subTest(group=group), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = root / "hooks.json"
                path.write_text(json.dumps({"hooks": {"UserPromptSubmit": [group]}}))
                original = path.read_bytes()
                with self.assertRaises(ValueError):
                    installer.install(root, legacy_hook=True)
                self.assertEqual(path.read_bytes(), original)
                self.assertFalse((root / "skills").exists())

    def test_uninstall_refuses_a_foreign_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            foreign = root / "foreign"
            foreign.mkdir()
            destination = root / "skills" / installer.NAME
            destination.parent.mkdir()
            destination.symlink_to(foreign, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "not this installation"):
                installer.install(root, uninstall=True)
            self.assertTrue(destination.is_symlink())

    def test_uninstall_without_an_owned_hook_preserves_the_file_exactly(self):
        for original in ('{ "description": "Unrelated configuration" }\n', '{ "hooks": {} }\n'):
            with self.subTest(original=original), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = root / "hooks.json"
                path.write_text(original)
                installer.install(root, uninstall=True)
                self.assertEqual(path.read_text(), original)
                self.assertEqual(list(root.glob("hooks.json.router-backup-*")), [])

    def test_hook_write_failure_rolls_back_only_the_new_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = '{"hooks": {"OtherEvent": []}}'
            (root / "hooks.json").write_text(original)
            with patch.object(installer, "atomic_write", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    installer.install(root, legacy_hook=True)
            self.assertFalse((root / "skills" / installer.NAME).is_symlink())
            self.assertEqual((root / "hooks.json").read_text(), original)
            backup = next(root.glob("hooks.json.router-backup-*"))
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

    def test_atomic_write_detects_changes_after_temporary_file_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hooks.json"
            path.write_text("original")
            with patch.object(installer.os, "fsync", side_effect=lambda *_: path.write_text("concurrent edit")):
                with self.assertRaisesRegex(ValueError, "changed during"):
                    installer.atomic_write(path, "replacement", "original")
            self.assertEqual(path.read_text(), "concurrent edit")
            self.assertEqual(list(path.parent.glob(".router-hooks-*")), [])

    def test_symlinked_hooks_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            other = root / "other.json"
            other.write_text("{}")
            (root / "hooks.json").symlink_to(other)
            installer.install(root)
            for kwargs in ({"legacy_hook": True}, {"uninstall": True}):
                with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "symlinked"):
                    installer.install(root, **kwargs)
            self.assertEqual(other.read_text(), "{}")


class ProxyHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_xhigh_effort_is_not_overridden_by_task_classification(self):
        async def catalog():
            return CATALOG

        state = TurnRouter(settings=lambda: router.policy(include_local=False), record=MemoryRun)
        changed, _ = await state.prepare(prompt("Use xhigh effort to implement pagination"), catalog)
        self.assertEqual(choice_from(changed["params"]), {"model": "gpt-6-astra", "effort": "xhigh"})

    async def test_null_collaboration_settings_can_be_filled(self):
        async def catalog():
            return CATALOG

        message = prompt("Run tests")
        message["params"]["collaborationMode"]["settings"] = None
        changed, _ = await TurnRouter(settings=lambda: router.policy(include_local=False), record=MemoryRun).prepare(message, catalog)
        self.assertEqual(choice_from(changed["params"]), {"model": "gpt-6-luna", "effort": "low"})

    async def test_stale_completion_does_not_make_a_newer_turn_routable(self):
        state = TurnRouter(settings=lambda: router.policy(include_local=False), record=MemoryRun)
        state.observe_notification({"method": "turn/started", "params": {"threadId": "one", "turn": {"id": "new"}}})
        state.observe_notification({"method": "turn/completed", "params": {"threadId": "one", "turn": {"id": "old"}}})
        self.assertIn("one", state.active)
        original = prompt("Run tests")
        changed, run = await state.prepare(original, None)
        self.assertIs(changed, original)
        self.assertIsNone(run)

    async def test_idle_resume_clears_stale_active_state(self):
        state = TurnRouter(settings=lambda: router.policy(include_local=False), record=MemoryRun)
        state.active.add("one")
        state.observe_response("thread/resume", {}, {"result": {"thread": {"id": "one", "status": {"type": "idle"}}}})
        self.assertNotIn("one", state.active)

    async def test_bad_input_is_rejected_without_killing_the_bridge(self):
        client, downstream = wire_pair()
        upstream, server = wire_pair()
        bridge = Bridge(downstream, upstream, TurnRouter(settings=lambda: router.policy(include_local=False), record=MemoryRun), claim=lambda *_: None)
        task = asyncio.create_task(bridge.run())
        try:
            for params in (["invalid"], {"threadId": []}, {"threadId": "one", "input": [None]},
                           {"threadId": "one", "input": [{"type": "text", "text": 1}]}):
                await client.send({"id": 1, "method": "turn/start", "params": params})
                result = await asyncio.wait_for(client.receive(), 1)
                self.assertEqual(result["error"]["code"], -32602)
                self.assertTrue(server.incoming.empty())
            approval_reply = {"id": "approval", "result": {"decision": "decline"}}
            await client.send(approval_reply)
            self.assertEqual(await asyncio.wait_for(server.receive(), 1), approval_reply)
            self.assertFalse(task.done())
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_rejected_start_releases_its_claim_and_forwards_the_error(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(router, "STATE_DIR", Path(directory) / "state"):
            client, downstream = wire_pair()
            upstream, server = wire_pair()
            bridge = Bridge(downstream, upstream, TurnRouter(settings=lambda: router.policy(include_local=False), record=MemoryRun))
            task = asyncio.create_task(bridge.run())
            try:
                await client.send(prompt("Run tests", 12))
                query = await asyncio.wait_for(server.receive(), 1)
                await server.send({"id": query["id"], "result": {"data": CATALOG}})
                submitted = await asyncio.wait_for(server.receive(), 1)
                self.assertEqual(submitted["method"], "turn/start")
                self.assertEqual(len(list(router.STATE_DIR.glob("prompt-*.json"))), 1)
                error = {"id": 12, "error": {"code": -1, "message": "Rejected by Codex"}}
                await server.send(error)
                self.assertEqual(await asyncio.wait_for(client.receive(), 1), error)
                self.assertEqual(list(router.STATE_DIR.glob("prompt-*.json")), [])
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_disconnect_before_ack_marks_submission_unconfirmed(self):
        client, downstream = wire_pair()
        upstream, server = wire_pair()
        records = []

        def record():
            value = MemoryRun()
            records.append(value)
            return value

        bridge = Bridge(downstream, upstream, TurnRouter(settings=lambda: router.policy(include_local=False), record=record), claim=lambda *_: None)
        task = asyncio.create_task(bridge.run())
        try:
            await client.send(prompt("Run tests", 12))
            query = await asyncio.wait_for(server.receive(), 1)
            await server.send({"id": query["id"], "result": {"data": CATALOG}})
            await asyncio.wait_for(server.receive(), 1)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(records[0].record["status"], "unconfirmed")

    async def test_oversized_handshake_has_an_actionable_error(self):
        reader = asyncio.StreamReader(limit=32)
        reader.feed_data(b"x" * 64)
        with self.assertRaisesRegex(router.RouterError, "handshake headers exceeded"):
            await WebSocket(reader, BufferWriter(), client=False).handshake()


if __name__ == "__main__":
    unittest.main()

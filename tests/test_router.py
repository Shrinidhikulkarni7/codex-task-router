from contextlib import redirect_stdout
from copy import deepcopy
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
sys.path.insert(0, str(ROOT / "skills" / "codex-model-router" / "scripts"))
import router

spec = importlib.util.spec_from_file_location("router_installer", ROOT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def model(name, efforts=("low", "medium", "high", "xhigh"), hidden=False):
    return {"model": name, "hidden": hidden, "supportedReasoningEfforts": [{"reasoningEffort": e} for e in efforts]}


CATALOG = [model("gpt-6.1-sol"), model("gpt-6-sol"), model("gpt-6-luna"), model("gpt-6-astra"), model("gpt-5.6-terra")]


class FakeRpc:
    def __init__(self, status="applied", catalog=None, feature_enabled=True):
        self.calls = []
        self.status = status
        self.catalog = catalog if catalog is not None else CATALOG
        self.feature_enabled = feature_enabled

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def request(self, method, params):
        self.calls.append((method, deepcopy(params)))
        if method == "model/list":
            return {"data": self.catalog}
        if method == "thread/turns/list":
            return {"data": [{"id": "turn-active", "status": "inProgress"}]}
        if method == "hooks/list":
            return {"data": [{"cwd": params["cwds"][0], "hooks": [{"command": "python3 /test/codex-model-router/scripts/router.py hook", "eventName": "userPromptSubmit", "enabled": True, "trustStatus": "trusted", "async": True, "sourcePath": "/test/hooks.json"}], "errors": [], "warnings": []}]}
        if method == "thread/loaded/list":
            return {"data": ["thread-one"]}
        if method == "experimentalFeature/list":
            return {"data": [{"name": "step_model_switching", "enabled": self.feature_enabled, "defaultEnabled": False, "stage": "underDevelopment"}]}
        if method == "turn/settings/update":
            return {"status": self.status}
        raise AssertionError("Unexpected RPC method " + method)


class IsolatedStateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch.object(router, "STATE_DIR", Path(directory.name) / "state")
        patcher.start()
        self.addCleanup(patcher.stop)


class RoutingTests(IsolatedStateTests):
    def test_realistic_tasks(self):
        cases = [
            ("Run the existing unit tests", "precheck"),
            ("Run lint and typecheck", "precheck"),
            ("Fix the spelling typo in the footer", "easy"),
            ("Summarize this README", "easy"),
            ("Implement pagination for the search results", "coding"),
            ("Implement the approved plan", "coding"),
            ("Implement the production migration plan", "planning"),
            ("Run pwd and list the first five entries", "easy"),
            ("Write integration tests for the export endpoint", "coding"),
            ("Review the code changes", "review"),
            ("Plan the database architecture", "planning"),
            ("Diagnose the intermittent crash", "debugging"),
            ("Investigate a race condition in the queue", "deep-debug"),
            ("Run tests then implement pagination", "coding"),
            ("Run lint and add OAuth to the login flow", "planning"),
            ("Pretest checks for a production migration", "planning"),
            ("go ahead", None),
            ("continue", None),
            ("yes", None),
            ("please handle this", None),
            ("/model", None),
            ("Use Luna for this task", None),
            ("Use gpt-6.1-sol for this task", None),
            ("Use low reasoning for this task", None),
            ("Review this snippet:\n```\n# implement a deadlock\n```", "review"),
        ]
        for task, profile in cases:
            with self.subTest(task=task):
                self.assertEqual(router.classify(task)[0], profile)

    def test_explicit_directive_wins(self):
        self.assertEqual(router.classify("[route:terra] Implement the plan")[0], "terra")
        self.assertEqual(router.classify("[route:off] Diagnose the crash", "debugging", 2)[0], None)
        with self.assertRaises(router.RouterError):
            router.classify("[route:nonexistent] Do it")

    def test_escalation_uses_explicit_failed_attempts(self):
        self.assertEqual(router.classify("", "debugging", 1)[0], "debugging")
        self.assertEqual(router.classify("", "debugging", 2)[0], "deep-debug")
        self.assertEqual(router.classify("", "precheck", 2)[0], "precheck")

    def test_available_model_and_effort(self):
        config = router.policy()
        self.assertEqual(router.select_model("planning", CATALOG, config)["model"], "gpt-6.1-sol")
        self.assertEqual(router.select_model("planning", [model("gpt-6-sol")], config)["model"], "gpt-6-sol")
        self.assertEqual(router.select_model("terra", CATALOG, config)["model"], "gpt-5.6-terra")
        for catalog in ([model("gpt-6-luna")], [model("gpt-6.1-sol", ("low",))], [model("gpt-6.1-sol", hidden=True)]):
            with self.subTest(catalog=catalog), self.assertRaises(router.RouterError):
                router.select_model("planning", catalog, config)

    def test_explicit_model_is_never_silently_substituted(self):
        with self.assertRaises(router.RouterError):
            router.select_model("coding", CATALOG, router.policy(), "missing-model")
        selected = router.select_model("coding", CATALOG, router.policy(), "gpt-6-luna", "high")
        self.assertEqual((selected["model"], selected["effort"]), ("gpt-6-luna", "high"))

    def test_update_only_changes_current_turn_model_and_effort(self):
        rpc = FakeRpc()
        choice = router.select_model("debugging", CATALOG, router.policy())
        result = router.apply_route(rpc, choice, "thread-one")
        self.assertEqual(result["status"], "applied")
        self.assertEqual(rpc.calls, [
            ("thread/turns/list", {"threadId": "thread-one", "limit": 1}),
            ("turn/settings/update", {"threadId": "thread-one", "turnId": "turn-active", "model": "gpt-6.1-sol", "effort": "high"}),
        ])

    def test_stale_turn_is_not_reported_as_applied(self):
        rpc = FakeRpc(status="targetUnavailable")
        with self.assertRaisesRegex(router.RouterError, "no longer active"):
            router.apply_route(rpc, {"model": "gpt-6-luna", "effort": "low"}, "thread-one", "old-turn")
        self.assertEqual(len(rpc.calls), 1)

    def test_no_active_turn_does_not_trigger_an_update(self):
        rpc = FakeRpc()
        with patch.object(rpc, "request", return_value={"data": [{"id": "old", "status": "completed"}]}):
            with self.assertRaisesRegex(router.RouterError, "No active turn"):
                router.apply_route(rpc, {}, "thread-one")

    def test_hook_retry_targets_the_same_turn(self):
        rpc = FakeRpc()
        responses = [{"status": "targetUnavailable"}, {"status": "applied"}]
        with patch.object(rpc, "request", side_effect=responses) as request, patch.object(router.time, "sleep"):
            result = router.apply_route(rpc, {"model": "gpt-6-luna", "effort": "low"}, "thread-one", "turn-one", retry=True)
            self.assertEqual(result["status"], "applied")
            self.assertEqual(request.call_args_list[0], request.call_args_list[1])

    def test_catalog_pagination(self):
        rpc = FakeRpc()
        with patch.object(rpc, "request", side_effect=[{"data": CATALOG[:2], "nextCursor": "next"}, {"data": CATALOG[2:]}]) as request:
            self.assertEqual(router.live_catalog(rpc), CATALOG)
            self.assertEqual(request.call_args_list[1].args[1]["cursor"], "next")

    def test_repeating_cursor_is_rejected(self):
        rpc = FakeRpc()
        with patch.object(rpc, "request", return_value={"data": [], "nextCursor": "same"}):
            with self.assertRaisesRegex(router.RouterError, "repeated"):
                router.live_catalog(rpc)

    def test_hook_output_confirms_publication_without_claiming_inference(self):
        event = {"hook_event_name": "UserPromptSubmit", "session_id": "thread-one", "turn_id": "turn-one", "prompt": "Run unit tests"}
        out = io.StringIO()
        with patch.object(router, "policy", return_value=dict(router.policy(), routing_mode="prompt")), patch.object(router, "Rpc", return_value=FakeRpc()), patch.object(sys, "stdin", io.StringIO(json.dumps(event))), redirect_stdout(out):
            self.assertEqual(router.main(["hook"]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("published gpt-6-luna / low", result["hookSpecificOutput"]["additionalContext"])

    def test_hook_connection_failure_does_not_block_work(self):
        event = {"hook_event_name": "UserPromptSubmit", "session_id": "t", "turn_id": "u", "prompt": "Run unit tests"}
        out = io.StringIO()
        with patch.object(router, "policy", return_value=dict(router.policy(), routing_mode="prompt")), patch.object(router, "Rpc", side_effect=PermissionError("denied")), patch.object(sys, "stdin", io.StringIO(json.dumps(event))), redirect_stdout(out):
            self.assertEqual(router.main(["hook"]), 0)
        result = json.loads(out.getvalue())
        self.assertIn("did not confirm a switch", result["systemMessage"])
        self.assertNotIn("continue", result)

    def test_off_and_ambiguous_hooks_never_connect(self):
        for prompt in ("continue", "[route:off] Run unit tests"):
            event = {"hook_event_name": "UserPromptSubmit", "prompt": prompt}
            with patch.object(router, "Rpc") as rpc, patch.object(sys, "stdin", io.StringIO(json.dumps(event))), redirect_stdout(io.StringIO()):
                self.assertEqual(router.main(["hook"]), 0)
                rpc.assert_not_called()

    def test_cli_launcher_passes_literal_prompt_without_shell(self):
        task = "Implement pagination; $(touch /tmp/router-must-not-run) `echo nope`"
        with patch.object(router, "cached_catalog", return_value=CATALOG), patch.object(router.subprocess, "call", return_value=7) as call:
            with patch.object(sys, "stderr", io.StringIO()):
                self.assertEqual(router.main(["run", task]), 7)
            self.assertEqual(call.call_args.args[0][-1], task)
            self.assertEqual(call.call_args.args[0][-2], "--")
            self.assertEqual(call.call_args.kwargs, {})

    def test_launcher_selects_luna_before_starting_the_codex_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = {"models": [{"slug": "gpt-6-luna", "supported_reasoning_levels": [{"effort": "medium"}]}]}
            (root / "models_cache.json").write_text(json.dumps(cache))
            fake_codex = root / "fake-codex"
            fake_codex.write_text(f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
            fake_codex.chmod(0o700)
            task = "Run pwd and list the first five entries in the current directory."
            result = subprocess.run(
                [sys.executable, str(ROOT / "skills/codex-model-router/scripts/router.py"), "run", "--codex", str(fake_codex), "--codex-home", str(root), "--phase", "easy", task],
                text=True, capture_output=True, timeout=5,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["--cd", str(Path.cwd()), "--model", "gpt-6-luna", "-c", 'model_reasoning_effort="medium"', "--", task])
        selection = json.loads(result.stderr)
        self.assertEqual(selection["status"], "launching")
        self.assertEqual(selection["scope"], "initial model for a new Codex session")

    def test_ambiguous_cli_task_still_runs(self):
        with patch.object(router.subprocess, "call", return_value=0) as call, patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(router.main(["run", "hello"]), 0)
            call.assert_called_once_with(["codex", "--cd", str(Path.cwd()), "--", "hello"])

    def test_prompt_cannot_become_a_codex_flag(self):
        task = "--dangerously-bypass-approvals-and-sandbox"
        with patch.object(router, "cached_catalog", return_value=CATALOG), patch.object(router.subprocess, "call", return_value=0) as call, patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(router.main(["run", "--phase", "easy", "--", task]), 0)
            self.assertEqual(call.call_args.args[0][-2:], ["--", task])


class DiagnosticsTests(IsolatedStateTests):
    def run_hook(self, prompt="[route:easy] Private task body", rpc=None, **event_fields):
        event = {"hook_event_name": "UserPromptSubmit", "session_id": "thread-one", "turn_id": "turn-one", "prompt": prompt}
        event.update(event_fields)
        out = io.StringIO()
        with patch.object(router, "policy", return_value=dict(router.policy(), routing_mode="prompt")), patch.object(router, "Rpc", return_value=rpc or FakeRpc()), patch.object(sys, "stdin", io.StringIO(json.dumps(event))), redirect_stdout(out):
            self.assertEqual(router.main(["hook"]), 0)
        return json.loads(out.getvalue())

    def test_applied_run_is_recorded_without_prompt(self):
        self.run_hook()
        history = router.routing_status()
        self.assertEqual(history["runs"][0]["status"], "applied")
        self.assertEqual(history["runs"][0]["model"], "gpt-6-luna")
        self.assertEqual(history["runs"][0]["thread_id"], "thread-one")
        self.assertNotIn("Private task body", json.dumps(history))

    def test_legacy_hook_skips_a_prompt_claimed_by_the_session_proxy(self):
        task = "[route:easy] Private task body"
        path = router.claim_prompt("thread-one", task)
        self.assertNotIn(task, path.read_text())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        rpc = FakeRpc()
        result = self.run_hook(task, rpc=rpc)
        self.assertEqual(result, {})
        self.assertEqual(rpc.calls, [])
        self.assertFalse(path.exists())
        self.assertIn("automatic session router", router.routing_status()["runs"][0]["reason"])

    def test_prompt_claim_is_specific_to_the_thread_and_prompt(self):
        router.claim_prompt("thread-one", "private text")
        self.assertFalse(router.consume_prompt_claim("thread-two", "private text"))
        self.assertFalse(router.consume_prompt_claim("thread-one", "different text"))
        self.assertTrue(router.consume_prompt_claim("thread-one", "private text"))
        self.assertFalse(router.consume_prompt_claim("thread-one", "private text"))

    def test_expired_or_stopped_proxy_claim_does_not_suppress_a_hook(self):
        path = router.claim_prompt("thread-one", "private text")
        data = json.loads(path.read_text())
        data["created_at"] -= 61
        path.write_text(json.dumps(data))
        self.assertFalse(router.consume_prompt_claim("thread-one", "private text"))
        router.claim_prompt("thread-one", "private text")
        with patch.object(router.os, "kill", side_effect=ProcessLookupError()):
            self.assertFalse(router.consume_prompt_claim("thread-one", "private text"))

    def test_skipped_directive_and_unsupported_event_have_records(self):
        self.run_hook("[route:off] A private task")
        self.assertEqual(router.routing_status()["runs"][0]["status"], "skipped")
        self.run_hook(hook_event_name="UnexpectedEvent")
        latest = router.routing_status()["runs"][0]
        self.assertEqual(latest["status"], "skipped")
        self.assertEqual(latest["reason"], "Unsupported hook event")

    def test_failed_update_is_recorded(self):
        with patch.object(router.time, "sleep"):
            result = self.run_hook(rpc=FakeRpc(status="targetUnavailable"))
        self.assertIn("did not confirm", result["systemMessage"])
        record = router.routing_status()["runs"][0]
        self.assertEqual(record["status"], "failed")
        self.assertIn("no longer active", record["error"])

    def test_feature_gate_rejection_has_recovery_instructions_and_does_not_block(self):
        rpc = FakeRpc()
        error = router.RouterError("turn/settings/update: turn settings updates require the step_model_switching feature")
        with patch.object(rpc, "request", side_effect=[{"data": CATALOG}, error]) as request:
            result = self.run_hook(rpc=rpc)
        self.assertEqual(request.call_count, 2)
        self.assertNotIn("hookSpecificOutput", result)
        self.assertIn("codex features enable step_model_switching", result["systemMessage"])
        record = router.routing_status()["runs"][0]
        self.assertEqual(record["status"], "failed")
        self.assertIn(str(error), record["error"])

    def test_incompatible_switch_is_explained_without_retry_or_replacement_task(self):
        rpc = FakeRpc()
        error = router.RouterError("turn/settings/update: the destination changes the admitted node REPL review requirement")
        with patch.object(rpc, "request", side_effect=[{"data": CATALOG}, error]) as request, patch.object(router.time, "sleep") as sleep, patch.object(router.subprocess, "call") as launch:
            result = self.run_hook(rpc=rpc)
        self.assertEqual([call.args[0] for call in request.call_args_list], ["model/list", "turn/settings/update"])
        self.assertEqual(request.call_args_list[-1].args[1], {"threadId": "thread-one", "turnId": "turn-one", "model": "gpt-6-luna", "effort": "medium"})
        sleep.assert_not_called()
        launch.assert_not_called()
        self.assertNotIn("hookSpecificOutput", result)
        self.assertIn("before Codex starts", result["systemMessage"])
        record = router.routing_status()["runs"][0]
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["failure_kind"], "incompatible_live_switch")
        self.assertEqual(record["error"], str(error))

    def test_old_incompatible_record_gets_explanation_without_changing_saved_history(self):
        router.STATE_DIR.mkdir()
        path = router.STATE_DIR / "run-old.json"
        saved = json.dumps({"status": "failed", "thread_id": "thread-one", "error": "turn/settings/update: the destination changes the admitted node REPL review requirement"})
        path.write_text(saved)
        record = router.routing_status("thread-one")["runs"][0]
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["failure_kind"], "incompatible_live_switch")
        self.assertIn("`run` command", record["next_step"])
        self.assertEqual(path.read_text(), saved)

    def test_record_write_failure_preserves_routing_confirmation(self):
        file = router.STATE_DIR.parent / "regular-file"
        file.write_text("not a directory")
        with patch.object(router, "STATE_DIR", file):
            result = self.run_hook()
        self.assertIn("published", result["hookSpecificOutput"]["additionalContext"])
        self.assertIn("Could not save router diagnostics", result["systemMessage"])

    def test_status_can_filter_a_thread_without_contacting_codex(self):
        self.run_hook(session_id="first")
        self.run_hook(session_id="second")
        out = io.StringIO()
        with patch.object(router, "Rpc") as rpc, redirect_stdout(out):
            self.assertEqual(router.main(["status", "--thread", "first"]), 0)
            rpc.assert_not_called()
        records = json.loads(out.getvalue())["runs"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["thread_id"], "first")

    def test_doctor_checks_hooks_and_target_without_starting_or_changing_a_task(self):
        rpc = FakeRpc()
        out = io.StringIO()
        with patch.object(router, "Rpc", return_value=rpc), redirect_stdout(out):
            self.assertEqual(router.main(["doctor", "--thread", "thread-one"]), 0)
        result = json.loads(out.getvalue())
        self.assertTrue(result["router_hook"]["ready"])
        self.assertTrue(result["target_thread"]["loaded_on_this_server"])
        self.assertTrue(result["live_switching"]["enabled"])
        self.assertEqual([method for method, _ in rpc.calls], ["model/list", "hooks/list", "thread/loaded/list", "experimentalFeature/list"])
        self.assertEqual(rpc.calls[-1][1], {"limit": 100, "threadId": "thread-one"})

    def test_doctor_reports_disabled_switching_despite_a_trusted_hook(self):
        rpc = FakeRpc(feature_enabled=False)
        out = io.StringIO()
        with patch.object(router, "Rpc", return_value=rpc), redirect_stdout(out):
            self.assertEqual(router.main(["doctor"]), 0)
        result = json.loads(out.getvalue())
        self.assertTrue(result["router_hook"]["ready"])
        self.assertFalse(result["live_switching"]["enabled"])
        self.assertIn("codex features enable step_model_switching", result["live_switching"]["next_step"])
        self.assertEqual(rpc.calls[-1][1], {"limit": 100})
        self.assertEqual([method for method, _ in rpc.calls], ["model/list", "hooks/list", "experimentalFeature/list"])

    def test_feature_query_preserves_thread_scope_across_pages(self):
        pages = [
            {"data": [{"name": "hooks", "enabled": True}], "nextCursor": "page-two"},
            {"data": [{"name": "step_model_switching", "enabled": False, "stage": "underDevelopment"}]},
        ]
        rpc = FakeRpc()
        with patch.object(rpc, "request", side_effect=pages) as request:
            result = router.inspect_live_switching(rpc, "thread-one")
        self.assertTrue(result["listed"])
        self.assertFalse(result["enabled"])
        self.assertEqual(request.call_args_list[-1].args, ("experimentalFeature/list", {"limit": 100, "threadId": "thread-one", "cursor": "page-two"}))

    def test_missing_feature_is_unknown(self):
        with patch.object(FakeRpc, "request", return_value={"data": []}):
            result = router.inspect_live_switching(FakeRpc())
        self.assertFalse(result["listed"])
        self.assertIsNone(result["enabled"])

    def test_feature_query_rejects_repeated_cursors(self):
        with patch.object(FakeRpc, "request", return_value={"data": [], "nextCursor": "repeat"}):
            with self.assertRaisesRegex(router.RouterError, "repeated a pagination cursor"):
                router.inspect_live_switching(FakeRpc())

    def test_doctor_keeps_other_diagnostics_when_feature_query_is_unsupported(self):
        rpc = FakeRpc()
        request = rpc.request

        def unsupported(method, params):
            if method == "experimentalFeature/list":
                raise router.RouterError("experimentalFeature/list: Unsupported method")
            return request(method, params)

        out = io.StringIO()
        with patch.object(rpc, "request", side_effect=unsupported), patch.object(router, "Rpc", return_value=rpc), redirect_stdout(out):
            self.assertEqual(router.main(["doctor"]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["control_socket"], "reachable")
        self.assertTrue(result["router_hook"]["ready"])
        self.assertIsNone(result["live_switching"]["enabled"])
        self.assertIn("Unsupported method", result["live_switching"]["error"])

    def test_target_on_a_different_server_is_reported(self):
        self.assertFalse(router.thread_is_loaded(FakeRpc(), "different-thread"))

    def test_disabled_or_untrusted_hook_is_not_ready(self):
        for enabled, trust in ((False, "trusted"), (True, "modified"), (True, "untrusted")):
            result = {"data": [{"hooks": [{"command": "python3 /test/codex-model-router/scripts/router.py hook", "eventName": "userPromptSubmit", "enabled": enabled, "trustStatus": trust}]}]}
            with self.subTest(enabled=enabled, trust=trust), patch.object(FakeRpc, "request", return_value=result):
                self.assertFalse(router.inspect_router_hook(FakeRpc(), ROOT)["ready"])


class TransportTests(unittest.TestCase):
    def test_real_stdio_transport_handles_split_messages_and_notifications(self):
        server = '''
import sys, json
for line in sys.stdin:
    request = json.loads(line)
    if 'id' not in request:
        continue
    result = {'ok': True} if request['method'] == 'initialize' else {'data': [], 'nextCursor': None}
    wire = json.dumps({'method': 'notice', 'params': {}}) + '\\n' + json.dumps({'id': request['id'], 'result': result}) + '\\n'
    for start in range(0, len(wire), 9):
        sys.stdout.write(wire[start:start+9]); sys.stdout.flush()
'''
        with router.Rpc(command=[sys.executable, "-u", "-c", server], timeout=2, protocol="jsonl") as rpc:
            self.assertEqual(router.live_catalog(rpc), [])
        self.assertIsNotNone(rpc.process.poll())

    def test_failed_control_connection(self):
        server = 'import sys; print("Operation not permitted", file=sys.stderr); sys.exit(1)'
        with self.assertRaisesRegex(router.RouterError, "Cannot connect"):
            with router.Rpc(command=[sys.executable, "-u", "-c", server], timeout=2, protocol="jsonl"):
                pass

    def test_protocol_error_is_not_success(self):
        server = '''
import sys, json
for line in sys.stdin:
    r=json.loads(line)
    if 'id' in r:
        print(json.dumps({'id':r['id'],'error':{'code':-32601,'message':'Unsupported method'}}), flush=True)
'''
        with self.assertRaisesRegex(router.RouterError, "Unsupported method"):
            with router.Rpc(command=[sys.executable, "-u", "-c", server], timeout=2, protocol="jsonl"):
                pass

    def test_silent_server_times_out_and_exits(self):
        server = 'import sys\nfor line in sys.stdin: pass'
        rpc = router.Rpc(command=[sys.executable, "-u", "-c", server], timeout=0.1)
        with self.assertRaisesRegex(router.RouterError, "timed out"):
            with rpc:
                pass
        self.assertIsNotNone(rpc.process.poll())


class WebSocketTransportTests(unittest.TestCase):
    def peer(self, mode="normal", timeout=2, protocol="websocket"):
        return router.Rpc(command=[sys.executable, "-u", str(ROOT / "tests" / "ws_peer.py"), mode], timeout=timeout, protocol=protocol)

    def test_old_jsonl_transport_reproduces_timeout(self):
        with self.assertRaisesRegex(router.RouterError, "timed out during initialize"):
            with self.peer(timeout=0.15, protocol="jsonl"):
                pass

    def test_upgrade_masking_and_jsonrpc_round_trip(self):
        with self.peer() as rpc:
            catalog = router.live_catalog(rpc)
            self.assertEqual(catalog[0]["model"], "gpt-6-luna")
            self.assertEqual(rpc.request("turn/settings/update", {"threadId": "fixture-thread", "turnId": "fixture-turn", "model": "gpt-6-luna", "effort": "medium"}), {"status": "applied"})
        self.assertIsNotNone(rpc.process.poll())

    def test_fragmentation_and_ping_between_fragments(self):
        with self.peer("fragmented") as rpc:
            self.assertEqual(router.live_catalog(rpc)[0]["model"], "gpt-6-luna")

    def test_short_extended_and_large_frames_preserve_unicode(self):
        with self.peer() as rpc:
            for text in ("hello", "résumé" * 200, "🦉" * 10000):
                self.assertEqual(rpc.request("echo", {"text": text}), {"text": text})

    def test_bad_upgrade_is_rejected(self):
        for mode, message in (("bad_accept", "Invalid WebSocket upgrade"), ("http_error", "HTTP/1.1 403")):
            with self.subTest(mode=mode), self.assertRaisesRegex(router.RouterError, message):
                with self.peer(mode):
                    pass

    def test_closed_websocket_identifies_failed_method(self):
        with self.peer("close") as rpc:
            with self.assertRaisesRegex(router.RouterError, "closed the WebSocket during model/list"):
                router.live_catalog(rpc)

    def test_timeout_identifies_handshake_or_rpc(self):
        with self.assertRaisesRegex(router.RouterError, "timed out during WebSocket handshake"):
            with self.peer("silent_upgrade", timeout=0.15):
                pass
        with self.peer("silent_model", timeout=0.3) as rpc:
            with self.assertRaisesRegex(router.RouterError, "timed out during model/list"):
                router.live_catalog(rpc)

    def test_masked_and_oversized_server_frames_are_rejected(self):
        for mode, message in (("masked", "masked server frame"), ("oversized", "exceeded the size limit")):
            with self.subTest(mode=mode), self.peer(mode) as rpc:
                with self.assertRaisesRegex(router.RouterError, message):
                    router.live_catalog(rpc)


class InstallationTests(unittest.TestCase):
    def test_install_preserves_other_hooks_and_is_reversible(self):
        original = {"description": "Existing hooks", "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "/path/to/orca-hook"}]}], "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "existing-handler"}]}]}}
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            path = home / "hooks.json"
            path.write_text(json.dumps(original))
            installer.install(home, legacy_hook=True)
            installed = json.loads(path.read_text())
            self.assertEqual(installed["hooks"]["PostToolUse"], original["hooks"]["PostToolUse"])
            self.assertEqual(installed["hooks"]["UserPromptSubmit"][0], original["hooks"]["UserPromptSubmit"][0])
            self.assertEqual(len(installed["hooks"]["UserPromptSubmit"]), 2)
            self.assertTrue((home / "skills" / "codex-model-router").is_symlink())
            self.assertEqual(len(list(home.glob("hooks.json.router-backup-*"))), 1)
            installer.install(home, legacy_hook=True)
            self.assertEqual(json.loads(path.read_text()), installed)
            self.assertEqual(len(list(home.glob("hooks.json.router-backup-*"))), 1)
            installer.install(home, uninstall=True)
            self.assertEqual(json.loads(path.read_text()), original)
            self.assertFalse((home / "skills" / "codex-model-router").exists())

    def test_dry_run_and_empty_uninstall_do_not_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            installer.install(home, dry_run=True)
            installer.install(home, uninstall=True)
            self.assertEqual(list(home.iterdir()), [])

    def test_existing_skill_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            target = home / "skills" / "codex-model-router"
            target.mkdir(parents=True)
            (target / "user-file").write_text("preserve me")
            with self.assertRaisesRegex(ValueError, "already exists"):
                installer.install(home, legacy_hook=True)
            self.assertEqual((target / "user-file").read_text(), "preserve me")
            self.assertFalse((home / "hooks.json").exists())

    def test_invalid_hooks_are_not_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / "hooks.json").write_text("not json")
            with self.assertRaises(ValueError):
                installer.install(home, legacy_hook=True)
            self.assertEqual((home / "hooks.json").read_text(), "not json")
            self.assertFalse((home / "skills").exists())


if __name__ == "__main__":
    unittest.main()

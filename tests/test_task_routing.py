"""Task retention, deliberate transitions, and rollback at turn admission."""

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/codex-model-router/scripts"))
import router
from session_proxy import TurnRouter, choice_from
from test_session_proxy import CATALOG, MemoryRun, prompt


class TaskRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = router.policy(include_local=False)
        self.config["routing_mode"] = "task"
        self.state = TurnRouter(settings=lambda: self.config, record=MemoryRun)
        self.calls = 0

    async def catalog(self):
        self.calls += 1
        return CATALOG

    async def accept(self, text, thread="one", mode="default"):
        message = prompt(text, thread=thread, mode=mode)
        changed, run = await self.state.prepare(message, self.catalog)
        self.state.observe_response("turn/start", changed["params"], {"result": {"turn": {"id": "accepted"}}}, run.record)
        return choice_from(changed["params"]), run

    async def test_task_mode_retains_selection_without_repeated_catalog_reads(self):
        self.assertEqual(self.config["routing_mode"], "task")
        router.validate_policy(self.config)
        await self.accept("Implement pagination")
        choice, run = await self.accept("Run existing tests")
        self.assertEqual(choice, {"model": "gpt-6.1-sol", "effort": "medium"})
        self.assertEqual(run.record["routing_mode"], "task")
        self.assertEqual(self.calls, 1)

    async def test_followups_keep_model_and_effort_without_classification_or_catalog(self):
        initial, _ = await self.accept("Plan the cache architecture")
        for text in ("Implement the approved plan", "Run tests", "Diagnose the failing test", "Review the changes", "List files", "continue"):
            with self.subTest(text=text), patch.object(router, "classify", side_effect=AssertionError("Follow-up was classified")):
                choice, run = await self.accept(text)
                self.assertEqual(choice, initial)
                self.assertEqual(run.record["reason"], "Retaining model and effort for current task")
        self.assertEqual(initial, {"model": "gpt-6.1-sol", "effort": "high"})
        self.assertEqual(self.calls, 1)

    async def test_new_task_markers_reselect_and_preserve_original_prompt(self):
        for marker in ("New task: ", "[route:new] ", "  NEW TASK:\n", "[ROUTE:NEW]\n"):
            with self.subTest(marker=marker):
                await self.accept("[route:coding] Implement pagination")
                original = prompt(marker + "List files")
                before = deepcopy(original)
                changed, run = await self.state.prepare(original, self.catalog)
                self.assertEqual(choice_from(changed["params"]), {"model": "gpt-6-luna", "effort": "medium"})
                self.assertEqual(changed["params"]["input"], before["params"]["input"])
                self.assertEqual(original, before)
                self.assertTrue(run.record["reason"].startswith("New task:"))
                self.state.observe_response("turn/start", changed["params"], {"result": {"turn": {"id": "new"}}})
                choice, _ = await self.accept("Review the changes")
                self.assertEqual(choice["model"], "gpt-6-luna")

    async def test_boundary_mentions_quotes_and_fences_do_not_reset_selection(self):
        initial, _ = await self.accept("Implement pagination")
        for text in ('The label says New task: List files', '> New task: List files', '```\nNew task: List files\n```', '"New task: List files"'):
            choice, _ = await self.accept(text)
            self.assertEqual(choice, initial)
        self.assertEqual(self.calls, 1)

    async def test_explicit_model_effort_and_profile_become_retained_choice(self):
        await self.accept("Implement pagination")
        for text, expected in (
            ("Use Terra to implement it", {"model": "gpt-5.6-terra", "effort": "medium"}),
            ("Use low effort for this step", {"model": "gpt-5.6-terra", "effort": "low"}),
            ("[route:deep-debug] Diagnose the deadlock", {"model": "gpt-6-astra", "effort": "xhigh"}),
            ("New task: [route:easy] List files", {"model": "gpt-6-luna", "effort": "medium"}),
            ("[route:new] Use Sol with high effort", {"model": "gpt-6.1-sol", "effort": "high"}),
        ):
            with self.subTest(text=text):
                choice, _ = await self.accept(text)
                self.assertEqual(choice, expected)
                choice, _ = await self.accept("Run tests")
                self.assertEqual(choice, expected)

    async def test_unknown_directive_or_unavailable_override_keeps_previous_selection(self):
        initial, _ = await self.accept("Implement pagination")
        for text in ("[route:typo] List files", "Use gpt-nonexistent to list files", "Use Sol with ultra effort"):
            with self.subTest(text=text), self.assertRaises(router.RouterError):
                await self.state.prepare(prompt(text), self.catalog)
            choice, _ = await self.accept("Run tests")
            self.assertEqual(choice, initial)

    async def test_mentioning_or_quoting_an_effort_is_not_a_switch_request(self):
        initial, _ = await self.accept("Implement pagination")
        for text in ("The previous run used low effort. Review the changes.", "Do not use low effort for this task.", "> Use low effort", "```\nUse low effort\n```", 'Explain the label "high reasoning".'):
            choice, _ = await self.accept(text)
            self.assertEqual(choice, initial)
        self.assertEqual(self.calls, 1)

    async def test_new_choice_is_retained_only_after_valid_acknowledgment(self):
        initial, _ = await self.accept("Implement pagination")
        for response in ({"error": {"message": "rejected"}}, {"result": {}}, {"result": {"turn": {"id": ""}}}, {"result": {"turn": {"id": 123}}}):
            with self.subTest(response=response):
                changed, _ = await self.state.prepare(prompt("New task: List files"), self.catalog)
                self.assertEqual(self.state.current["one"], initial)
                self.state.observe_response("turn/start", changed["params"], response)
                choice, _ = await self.accept("Run tests")
                self.assertEqual(choice, initial)

    async def test_rejected_initial_selection_does_not_pin_next_attempt(self):
        changed, _ = await self.state.prepare(prompt("List files"), self.catalog)
        self.state.observe_response("turn/start", changed["params"], {"error": {"message": "rejected"}})
        self.assertNotIn("one", self.state.task_selected)
        choice, _ = await self.accept("Implement pagination")
        self.assertEqual(choice["model"], "gpt-6.1-sol")

    async def test_manual_native_settings_override_and_persist_through_followups(self):
        await self.accept("List files")
        self.state.observe_response("thread/settings/update", {"threadId": "one", "model": "gpt-5.6-terra", "effort": "high"}, {"result": {}})
        for text in ("Run tests", "Review the changes"):
            choice, _ = await self.accept(text)
            self.assertEqual(choice, {"model": "gpt-5.6-terra", "effort": "high"})
        self.assertEqual(self.calls, 1)
        choice, _ = await self.accept("New task: List files")
        self.assertEqual(choice["model"], "gpt-6-luna")

    async def test_explicit_requests_override_pending_native_selection(self):
        for text in ("Use Luna to list files", "[route:easy] List files", "New task: List files"):
            self.state.observe_response("thread/settings/update", {"threadId": "one", "model": "gpt-5.6-terra", "effort": "high"}, {"result": {}})
            choice, _ = await self.accept(text)
            self.assertEqual(choice, {"model": "gpt-6-luna", "effort": "medium"})

    async def test_failed_native_setting_update_does_not_replace_task_choice(self):
        initial, _ = await self.accept("Implement pagination")
        self.state.observe_response("thread/settings/update", {"threadId": "one", "model": "gpt-5.6-terra"}, {"error": {"message": "rejected"}})
        choice, _ = await self.accept("Run tests")
        self.assertEqual(choice, initial)

    async def test_resume_and_fork_retain_reported_choice_but_new_thread_routes(self):
        for method in ("thread/start", "thread/resume", "thread/fork"):
            with self.subTest(method=method):
                thread = method
                self.state.observe_response(method, {}, {"result": {"thread": {"id": thread, "status": {"type": "idle"}}, "model": "gpt-5.6-terra", "reasoningEffort": "high"}})
                choice, _ = await self.accept("Run tests", thread=thread)
                expected = {"model": "gpt-6-luna", "effort": "low"} if method == "thread/start" else {"model": "gpt-5.6-terra", "effort": "high"}
                self.assertEqual(choice, expected)
        self.assertEqual(self.calls, 1)

    async def test_close_clears_task_state_and_threads_are_independent(self):
        await self.accept("Implement pagination", thread="one")
        await self.accept("List files", thread="two")
        self.state.observe_notification({"method": "thread/closed", "params": {"threadId": "one"}})
        self.assertNotIn("one", self.state.task_selected)
        choice, _ = await self.accept("Run tests", thread="one")
        self.assertEqual(choice, {"model": "gpt-6-luna", "effort": "low"})
        choice, _ = await self.accept("Implement pagination", thread="two")
        self.assertEqual(choice, {"model": "gpt-6-luna", "effort": "medium"})

    async def test_off_uses_native_choice_and_retains_it_after_acceptance(self):
        await self.accept("Implement pagination")
        message = prompt("[route:off] List files")
        changed, run = await self.state.prepare(message, self.catalog)
        self.assertIs(changed, message)
        self.assertEqual(run.record["status"], "skipped")
        self.state.observe_response("turn/start", changed["params"], {"result": {"turn": {"id": "native"}}})
        choice, _ = await self.accept("Run tests")
        self.assertEqual(choice, choice_from(message["params"]))
        self.assertEqual(self.calls, 1)

    async def test_disabled_policy_passes_through_and_reenable_retains_native_choice(self):
        await self.accept("Implement pagination")
        self.config["enabled"] = False
        choice, run = await self.accept("New task: [route:easy] List files")
        self.assertEqual(run.record["status"], "skipped")
        self.config["enabled"] = True
        resumed, _ = await self.accept("Run tests")
        self.assertEqual(resumed, choice)
        self.assertEqual(self.calls, 1)

    async def test_plan_mode_does_not_override_a_retained_choice(self):
        initial, _ = await self.accept("Implement pagination")
        choice, _ = await self.accept("How should this work?", mode="plan")
        self.assertEqual(choice, initial)
        choice, _ = await self.accept("New task: How should this work?", mode="plan")
        self.assertEqual(choice, {"model": "gpt-6.1-sol", "effort": "high"})

    async def test_unclassified_first_prompt_retains_native_choice(self):
        initial, _ = await self.accept("hello")
        choice, _ = await self.accept("Implement pagination")
        self.assertEqual(choice, initial)
        self.assertEqual(self.calls, 0)
        choice, _ = await self.accept("New task: Implement pagination")
        self.assertEqual(choice["model"], "gpt-6.1-sol")

    async def test_profile_edits_wait_for_boundary_and_mode_changes_apply_on_next_prompt(self):
        initial, _ = await self.accept("Implement pagination")
        self.config["profiles"]["coding"]["models"] = ["gpt-5.6-terra"]
        choice, _ = await self.accept("Implement the next change")
        self.assertEqual(choice, initial)
        choice, _ = await self.accept("New task: Implement pagination")
        self.assertEqual(choice["model"], "gpt-5.6-terra")
        self.config["routing_mode"] = "prompt"
        choice, _ = await self.accept("Run tests")
        self.assertEqual(choice, {"model": "gpt-6-luna", "effort": "low"})
        self.config["routing_mode"] = "task"
        retained, _ = await self.accept("Review the changes")
        self.assertEqual(retained, choice)

    async def test_catalog_failure_on_new_task_leaves_previous_task_usable(self):
        initial, _ = await self.accept("Implement pagination")

        async def unavailable():
            raise router.RouterError("Catalog unavailable")

        with self.assertRaisesRegex(router.RouterError, "Catalog unavailable"):
            await self.state.prepare(prompt("New task: List files"), unavailable)
        changed, _ = await self.state.prepare(prompt("Run tests"), unavailable)
        self.assertEqual(choice_from(changed["params"]), initial)

    async def test_task_and_prompt_comparison_measures_switches_not_token_savings(self):
        tasks = ("Plan the cache architecture", "Implement the approved plan", "Run existing tests", "Diagnose the failing test", "Run existing tests", "Review the implementation", "List files in the current directory", "continue")
        results = {}
        for mode in ("selective", "task", "prompt"):
            self.config["routing_mode"] = mode
            self.state = TurnRouter(settings=lambda: self.config, record=MemoryRun)
            self.calls = 0
            choices = [(await self.accept(text))[0] for text in tasks]
            results[mode] = {
                "model_changes": sum(a["model"] != b["model"] for a, b in zip(choices, choices[1:])),
                "settings_changes": sum(a != b for a, b in zip(choices, choices[1:])),
                "catalog_calls": self.calls,
            }
        self.assertEqual(results, {
            "selective": {"model_changes": 0, "settings_changes": 2, "catalog_calls": 3},
            "task": {"model_changes": 0, "settings_changes": 0, "catalog_calls": 1},
            "prompt": {"model_changes": 5, "settings_changes": 6, "catalog_calls": 7},
        })


class TaskPolicyTests(unittest.TestCase):
    def test_auto_validation_exits_cleanly_when_invoked_as_a_script(self):
        result = subprocess.run([sys.executable, router.__file__, "auto", "--phase", "coding"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("Model router: auto takes routing choices from prompts;"))
        self.assertNotIn("Traceback", result.stderr)

    def test_modes_validate_and_invalid_values_fail(self):
        for mode in ("selective", "task", "prompt"):
            router.validate_policy(dict(router.policy(include_local=False), routing_mode=mode))
        for mode in (None, True, 1, [], {}, "typo", "TASK"):
            with self.subTest(mode=mode), self.assertRaisesRegex(router.RouterError, "routing_mode"):
                router.validate_policy(dict(router.policy(include_local=False), routing_mode=mode))

    def test_preview_classifier_understands_explicit_boundaries(self):
        for text in ("New task: List files", "[route:new] List files"):
            self.assertEqual(router.classify(text)[0], "easy")
        self.assertEqual(router.classify("New task: [route:off] List files")[0], None)

    def test_legacy_hook_does_not_change_task_selection_or_connect(self):
        with tempfile.TemporaryDirectory() as directory:
            event = {"hook_event_name": "UserPromptSubmit", "session_id": "one", "turn_id": "two", "prompt": "[route:easy] List files"}
            with patch.object(router, "STATE_DIR", Path(directory)), patch.object(router, "Rpc") as rpc, patch.object(sys, "stdin", io.StringIO(json.dumps(event))), redirect_stdout(io.StringIO()):
                self.assertEqual(router.main(["hook"]), 0)
                rpc.assert_not_called()
                run = router.routing_status()["runs"][0]
                self.assertEqual(run["status"], "skipped")
                self.assertIn("router.py auto", run["reason"])


if __name__ == "__main__":
    unittest.main()

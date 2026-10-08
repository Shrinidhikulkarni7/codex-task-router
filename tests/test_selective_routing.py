"""Selective phase transitions, user control, and admission-time rollback."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/codex-model-router/scripts"))
import router
from session_proxy import TurnRouter, choice_from
from test_session_proxy import CATALOG, MemoryRun, prompt


class SelectiveRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = router.policy()
        self.state = TurnRouter(settings=lambda: self.config, record=MemoryRun)
        self.calls = 0

    async def catalog(self):
        self.calls += 1
        return CATALOG

    async def accept(self, text, thread="one"):
        original = prompt(text, thread=thread)
        before = deepcopy(original)
        changed, run = await self.state.prepare(original, self.catalog)
        self.assertEqual(original, before)
        expected = deepcopy(before)
        for key in ("model", "effort"):
            expected["params"][key] = changed["params"][key]
        for key in ("model", "reasoning_effort"):
            expected["params"]["collaborationMode"]["settings"][key] = changed["params"]["collaborationMode"]["settings"][key]
        self.assertEqual(changed, expected)
        self.state.observe_response("turn/start", changed["params"], {"result": {"turn": {"id": "ok"}}}, run.record)
        return choice_from(changed["params"]), run.record

    async def test_selective_is_default_in_shipped_and_older_policy(self):
        self.assertEqual(self.config["routing_mode"], "selective")
        del self.config["routing_mode"]
        router.validate_policy(self.config)
        await self.accept("List files")
        choice, run = await self.accept("Implement pagination")
        self.assertEqual(choice, {"model": "gpt-6.1-sol", "effort": "medium"})
        self.assertEqual(run["routing_mode"], "selective")
        self.assertEqual(run["selection"], {"kind": "phase", "profile": "coding", "pinned": False})

    async def test_typical_work_escalates_but_short_followups_do_not_bounce(self):
        cases = (
            ("List files", "gpt-6-luna", "medium", "initial"),
            ("Implement pagination", "gpt-6.1-sol", "medium", "phase"),
            ("Run tests", "gpt-6.1-sol", "medium", "retain"),
            ("Review the changes", "gpt-6.1-sol", "medium", "retain"),
            ("Diagnose the failing test", "gpt-6.1-sol", "high", "phase"),
            ("Run existing tests", "gpt-6.1-sol", "high", "retain"),
            ("Investigate the intermittent deadlock", "gpt-6-astra", "xhigh", "phase"),
            ("continue", "gpt-6-astra", "xhigh", "retain"),
            ("Fix the remaining issue", "gpt-6-astra", "xhigh", "retain"),
            ("Summarize the findings", "gpt-6-astra", "xhigh", "retain"),
        )
        for text, model, effort, kind in cases:
            with self.subTest(text=text):
                choice, run = await self.accept(text)
                self.assertEqual(choice, {"model": model, "effort": effort})
                self.assertEqual(run["selection"]["kind"], kind)
        self.assertEqual(self.calls, 4)

    async def test_approved_plan_moves_to_implementation_once(self):
        await self.accept("Plan the cache architecture")
        choice, run = await self.accept("Now implement the approved plan")
        self.assertEqual(choice, {"model": "gpt-6.1-sol", "effort": "medium"})
        self.assertEqual(run["selection"]["profile"], "coding")
        await self.accept("Implement the next change")
        await self.accept("Run tests")
        self.assertEqual(self.calls, 2)

    async def test_polite_work_requests_escalate_but_negated_requests_do_not(self):
        for request in ("Can you implement pagination?", "Could you please implement pagination?", "Let's implement pagination", "Next, implement pagination"):
            await self.accept("New task: List files")
            choice, _ = await self.accept(request)
            self.assertEqual(choice["model"], "gpt-6.1-sol")
        initial, _ = await self.accept("New task: List files")
        for request in ("Can you not implement it yet?", "Let's not implement it", "Would you explain the word implement?"):
            choice, _ = await self.accept(request)
            self.assertEqual(choice, initial)

    async def test_reported_repeated_failures_can_escalate_without_counting_tool_errors(self):
        for text in ("Two distinct fixes failed. Diagnose it.", "Still failing after 2 attempts. Investigate."):
            await self.accept("New task: Implement pagination")
            choice, run = await self.accept(text)
            self.assertEqual(choice, {"model": "gpt-6-astra", "effort": "xhigh"})
            self.assertIn("User reports", run["reason"])

    async def test_substantial_summary_batch_can_lower_selection_and_retain_it(self):
        for text in ("Now summarize these 30 release notes", "Extract the titles from 5 documents", "Summarize the articles as a batch"):
            await self.accept("New task: Plan the cache architecture")
            choice, run = await self.accept(text)
            self.assertEqual(choice, {"model": "gpt-6-luna", "effort": "medium"})
            self.assertEqual(run["selection"]["kind"], "phase")
            repeated, _ = await self.accept("Summarize the next one")
            self.assertEqual(repeated, choice)

    async def test_small_summaries_and_mixed_complex_batches_keep_capable_selection(self):
        initial, _ = await self.accept("Plan the cache architecture")
        for text in ("Summarize these 4 documents", "Summarize the results", "Summarize 30 security reports and design the remediation", "Run all 300 tests"):
            choice, _ = await self.accept(text)
            self.assertEqual(choice, initial)
        self.assertEqual(self.calls, 1)

    async def test_quotes_negations_and_status_reports_do_not_trigger_a_phase(self):
        initial, _ = await self.accept("List files")
        for text in ("> Investigate a deadlock", '"Investigate a deadlock"', "```\nInvestigate a deadlock\n```", "Do not implement it yet", "Don't diagnose the deadlock", "The log mentions a deadlock", "Can you explain the label 'Two fixes failed'?", "Run tests\nError: deadlock", "Use of two fixes failed in this example"):
            with self.subTest(text=text):
                choice, run = await self.accept(text)
                self.assertEqual(choice, initial)
                self.assertEqual(run["selection"]["kind"], "retain")
        self.assertEqual(self.calls, 1)

    async def test_explicit_choices_pin_until_new_task_or_another_override(self):
        for override in ("[route:easy] List files", "Use Luna to list files"):
            initial, _ = await self.accept(override)
            for text in ("Implement pagination", "Two fixes failed. Diagnose it", "Investigate the deadlock"):
                choice, run = await self.accept(text)
                self.assertEqual(choice, initial)
                self.assertTrue(run["selection"]["pinned"])
            choice, _ = await self.accept("New task: Implement pagination")
            self.assertEqual(choice["model"], "gpt-6.1-sol")
            self.assertNotIn("one", self.state.pinned)
        await self.accept("Use low effort")
        choice, _ = await self.accept("Plan the cache architecture")
        self.assertEqual(choice["effort"], "low")
        choice, _ = await self.accept("[route:deep-debug] Diagnose it")
        self.assertEqual(choice["model"], "gpt-6-astra")

    async def test_native_model_selection_and_resume_are_pinned(self):
        await self.accept("List files")
        self.state.observe_response("thread/settings/update", {"threadId": "one", "model": "gpt-5.6-terra", "effort": "high"}, {"result": {}})
        choice, _ = await self.accept("Investigate a deadlock")
        self.assertEqual(choice, {"model": "gpt-5.6-terra", "effort": "high"})
        self.assertEqual(self.calls, 1)
        for method in ("thread/resume", "thread/fork"):
            self.state.observe_response(method, {}, {"result": {"thread": {"id": "two"}, "model": "gpt-5.6-terra", "reasoningEffort": "high"}})
            selected, _ = await self.accept("Implement pagination", thread="two")
            self.assertEqual(selected, choice)
            selected, _ = await self.accept("[route:new] Implement pagination", thread="two")
            self.assertEqual(selected["model"], "gpt-6.1-sol")

    async def test_invalid_ack_does_not_commit_phase_or_pin_changes(self):
        await self.accept("[route:easy] List files")
        initial = deepcopy(self.state.current)
        for response in ({"error": {"message": "rejected"}}, {"result": {}}, {"result": {"turn": {"id": 1}}}):
            changed, run = await self.state.prepare(prompt("New task: Implement pagination"), self.catalog)
            self.state.observe_response("turn/start", changed["params"], response, run.record)
            self.assertEqual(self.state.current, initial)
            self.assertEqual(self.state.phase["one"], "easy")
            self.assertIn("one", self.state.pinned)
        await self.accept("New task: List files")
        changed, run = await self.state.prepare(prompt("Implement pagination"), self.catalog)
        self.state.observe_response("turn/start", changed["params"], {"error": {"message": "rejected"}}, run.record)
        self.assertEqual(self.state.phase["one"], "easy")

    async def test_catalog_failure_keeps_previous_selection_and_retention_usable(self):
        initial, _ = await self.accept("List files")

        async def unavailable():
            raise router.RouterError("Catalog unavailable")

        with self.assertRaisesRegex(router.RouterError, "Catalog unavailable"):
            await self.state.prepare(prompt("Implement pagination"), unavailable)
        self.assertEqual(self.state.phase["one"], "easy")
        changed, _ = await self.state.prepare(prompt("continue"), unavailable)
        self.assertEqual(choice_from(changed["params"]), initial)

    async def test_off_pins_accepted_native_choice_and_close_clears_state(self):
        await self.accept("List files")
        native, run = await self.accept("[route:off] Implement pagination")
        self.assertEqual(run["selection"]["kind"], "native")
        choice, _ = await self.accept("Plan the cache architecture")
        self.assertEqual(choice, native)
        self.state.observe_notification({"method": "thread/closed", "params": {"threadId": "one"}})
        self.assertNotIn("one", self.state.phase)
        self.assertNotIn("one", self.state.pinned)
        choice, _ = await self.accept("List files")
        self.assertEqual(choice["model"], "gpt-6-luna")

    async def test_policy_edits_do_not_reselect_same_phase_but_boundary_applies_them(self):
        initial, _ = await self.accept("Implement pagination")
        self.config["profiles"]["coding"]["models"] = ["gpt-5.6-terra"]
        choice, _ = await self.accept("Implement sorting")
        self.assertEqual(choice, initial)
        self.assertEqual(self.calls, 1)
        choice, _ = await self.accept("New task: Implement sorting")
        self.assertEqual(choice["model"], "gpt-5.6-terra")


if __name__ == "__main__":
    unittest.main()

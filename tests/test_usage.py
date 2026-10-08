"""Usage is optional observational data; it must never change routed traffic."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/codex-model-router/scripts"))
import router
from session_proxy import Bridge, TurnRouter, usage_snapshot
from test_session_proxy import CATALOG, MemoryRun, prompt, wire_pair


def usage(thread="one", turn="turn-a"):
    return {"method": "thread/tokenUsage/updated", "params": {
        "threadId": thread, "turnId": turn,
        "tokenUsage": {
            "last": {"inputTokens": 200, "cachedInputTokens": 128,
                     "cacheWriteInputTokens": 32, "outputTokens": 30,
                     "reasoningOutputTokens": 10, "totalTokens": 230},
            "total": {"inputTokens": 1000, "cachedInputTokens": 640,
                      "cacheWriteInputTokens": 160, "outputTokens": 150,
                      "reasoningOutputTokens": 50, "totalTokens": 1150},
            "modelContextWindow": 200000,
        },
    }}


class UsageReportingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client, downstream = wire_pair()
        upstream, self.server = wire_pair()
        self.records = []
        self.config = router.policy()

        def record():
            run = MemoryRun()
            self.records.append(run)
            return run

        state = TurnRouter(settings=lambda: self.config, record=record)
        self.bridge = Bridge(downstream, upstream, state, claim=lambda *_: None)
        self.job = asyncio.create_task(self.bridge.run())

    async def asyncTearDown(self):
        self.job.cancel()
        await asyncio.gather(self.job, return_exceptions=True)

    async def start(self, text="List files", thread="one"):
        original = prompt(text, request_id=len(self.records) + 1, thread=thread)
        await self.client.send(original)
        forwarded = await asyncio.wait_for(self.server.receive(), 2)
        if forwarded.get("method") == "model/list":
            await self.server.send({"id": forwarded["id"], "result": {"data": CATALOG}})
            forwarded = await asyncio.wait_for(self.server.receive(), 2)
        self.assertEqual(forwarded["method"], "turn/start")
        return original, self.records[-1]

    async def forward(self, message):
        await self.server.send(message)
        self.assertEqual(await asyncio.wait_for(self.client.receive(), 2), message)
        # Observing usage must not generate more upstream requests.
        self.assertTrue(self.server.incoming.empty())

    async def acknowledge(self, request, turn="turn-a"):
        await self.forward({"id": request["id"], "result": {
            "turn": {"id": turn, "status": "inProgress"}}})

    async def complete(self, thread="one", turn="turn-a"):
        await self.forward({"method": "turn/completed", "params": {
            "threadId": thread, "turn": {"id": turn, "status": "completed"}}})

    async def test_usage_and_completion_before_acknowledgment_are_attached(self):
        request, run = await self.start()
        await self.forward(usage())
        await self.complete()
        self.assertNotIn("token_usage", run.record)
        await self.acknowledge(request)
        self.assertEqual(run.record["status"], "accepted")
        self.assertEqual(run.record["turn_status"], "completed")
        self.assertEqual(run.record["token_usage"]["total"]["inputTokens"], 1000)

    async def test_repeated_snapshots_replace_instead_of_sum(self):
        request, run = await self.start()
        await self.acknowledge(request)
        event = usage()
        await self.forward(event)
        await self.forward(event)
        self.assertEqual(run.record["token_usage"]["total"]["totalTokens"], 1150)
        event["params"]["tokenUsage"]["total"].update(inputTokens=1200, totalTokens=1350)
        await self.forward(event)
        self.assertEqual(run.record["token_usage"]["total"]["totalTokens"], 1350)
        self.assertEqual(run.record["token_usage"]["last"]["totalTokens"], 230)

    async def test_usage_can_arrive_after_completion(self):
        request, run = await self.start()
        await self.acknowledge(request)
        await self.complete()
        await self.forward(usage())
        self.assertEqual(run.record["token_usage"]["total"]["cachedInputTokens"], 640)
        self.assertEqual(run.record["turn_status"], "completed")

    async def test_thread_and_turn_ids_prevent_cross_attribution(self):
        first, first_run = await self.start(thread="one")
        await self.acknowledge(first)
        second, second_run = await self.start(thread="two")
        await self.acknowledge(second)
        await self.forward(usage(thread="two"))
        await self.forward(usage(thread="one", turn="unrelated-child-turn"))
        self.assertNotIn("token_usage", first_run.record)
        self.assertIn("token_usage", second_run.record)

    async def test_off_and_disabled_routing_still_report_usage(self):
        for text, enabled in [("[route:off] Run tests", True), ("Run tests", False)]:
            with self.subTest(enabled=enabled):
                self.config["enabled"] = enabled
                request, run = await self.start(text)
                await self.acknowledge(request)
                await self.forward(usage())
                await self.complete()
                self.assertEqual(run.record["status"], "skipped")
                self.assertEqual(run.record["turn_id"], "turn-a")
                self.assertEqual(run.record["turn_status"], "completed")
                self.assertIn("token_usage", run.record)

    async def test_temporary_thread_is_forwarded_unchanged_and_usage_stays_separate(self):
        start = {"id": "temporary-start", "method": "thread/start", "params": {
            "ephemeral": True, "model": "gpt-5.6-luna", "baseInstructions": "Native title instructions"}}
        await self.client.send(start)
        self.assertEqual(await asyncio.wait_for(self.server.receive(), 2), start)
        # Exercise request metadata fallback as well as bridge association.
        await self.forward({"id": start["id"], "result": {
            "thread": {"id": "temporary"}, "model": "gpt-5.6-luna", "reasoningEffort": "low"}})
        task = {"id": "temporary-turn", "method": "turn/start", "params": {
            "threadId": "temporary", "input": [{"type": "text", "text": "Write a concise title for: list files"}],
            "model": "gpt-5.6-luna", "effort": "low", "outputSchema": {"type": "object"}}}
        await self.client.send(task)
        # There must be no model/list lookup or field mutation for this task.
        self.assertEqual(await asyncio.wait_for(self.server.receive(), 2), task)
        await self.acknowledge(task)
        await self.forward(usage(thread="temporary"))
        await self.complete(thread="temporary")
        run = self.records[-1]
        self.assertEqual(run.record["status"], "skipped")
        self.assertEqual(run.record["thread_kind"], "ephemeral")
        self.assertEqual(run.record["turn_status"], "completed")
        self.assertIn("token_usage", run.record)
        self.assertNotIn("profile", run.record)
        request, user_run = await self.start(thread="user-thread")
        await self.acknowledge(request)
        self.assertEqual(user_run.record["model"], "gpt-6-luna")
        self.assertNotIn("token_usage", user_run.record)

    async def test_bad_notifications_pass_through_and_preserve_last_valid_snapshot(self):
        request, run = await self.start()
        await self.acknowledge(request)
        await self.forward(usage())
        saved = deepcopy(run.record)
        malformed = [None, [], {"threadId": "one", "turnId": []}]
        for bad in (-1, True, "200", None, 2**63):
            params = usage()["params"]
            params["tokenUsage"]["last"]["inputTokens"] = bad
            malformed.append(params)
        for params in malformed:
            with self.subTest(params=params):
                await self.forward({"method": "thread/tokenUsage/updated", "params": params})
                self.assertEqual(run.record, saved)

    async def test_no_usage_notification_means_unknown_not_zero(self):
        request, run = await self.start()
        await self.acknowledge(request)
        await self.complete()
        self.assertNotIn("token_usage", run.record)

    async def test_rejected_turn_never_claims_buffered_usage(self):
        request, run = await self.start()
        await self.forward(usage())
        await self.forward({"id": request["id"], "error": {"code": -1, "message": "rejected"}})
        self.assertEqual(run.record["status"], "failed")
        self.assertNotIn("token_usage", run.record)

    async def test_observed_turn_history_is_bounded(self):
        for index in range(205):
            turn = str(index)
            request, _ = await self.start("[route:off] List files")
            await self.acknowledge(request, turn)
            await self.forward(usage(turn=turn))
            await self.complete(turn=turn)
        self.assertLessEqual(len(self.bridge.turns), 200)
        self.assertLessEqual(len(self.bridge.completed), 200)
        self.assertLessEqual(len(self.bridge.usage), 200)
        self.assertIn(("one", "204"), self.bridge.turns)
        self.assertNotIn(("one", "0"), self.bridge.turns)


class UsageDataTests(unittest.TestCase):
    def test_only_known_counters_are_retained_and_missing_optional_fields_stay_missing(self):
        value = usage()["params"]["tokenUsage"]
        value.update(prompt="sensitive prompt", model="not inference evidence", modelContextWindow=None)
        value["last"]["toolOutput"] = "sensitive tool output"
        del value["last"]["cacheWriteInputTokens"]
        snapshot = usage_snapshot(value)
        self.assertNotIn("cacheWriteInputTokens", snapshot["last"])
        self.assertNotIn("modelContextWindow", snapshot)
        self.assertEqual(snapshot["total"]["cacheWriteInputTokens"], 160)
        self.assertNotIn("sensitive", json.dumps(snapshot))
        self.assertNotIn("model", snapshot)

    def test_partial_or_invalid_counters_are_not_reported_as_valid_usage(self):
        for scope in ("last", "total"):
            value = usage()["params"]["tokenUsage"]
            del value[scope]["cachedInputTokens"]
            self.assertIsNone(usage_snapshot(value))
            value = usage()["params"]["tokenUsage"]
            value[scope]["cacheWriteInputTokens"] = False
            self.assertIsNone(usage_snapshot(value))

    def test_status_reads_persisted_snapshots_without_a_daemon(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(router, "STATE_DIR", Path(directory)):
            run = router.HookRun()
            snapshot = usage_snapshot(usage()["params"]["tokenUsage"])
            run.update(source="session-proxy", thread_id="one", turn_id="turn-a", token_usage=snapshot)
            rows = router.routing_status("one")["runs"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["token_usage"], snapshot)
            self.assertEqual(router.routing_status("two")["runs"], [])


if __name__ == "__main__":
    unittest.main()

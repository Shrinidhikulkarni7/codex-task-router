"""Local classifier contracts, transport limits, and actual turn-routing behavior."""

import asyncio
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/codex-model-router/scripts"))
import laya_classifier as laya
import router
from session_proxy import TurnRouter, choice_from
from test_session_proxy import CATALOG, MemoryRun, prompt


def answer(profile="coding", p=0.94):
    return {"model": "laya-rl-agent", "routing": {"model": "typed-decisions"}, "answers": {"profile": {
        "type": "choice", "choice": profile, "answer_confidence": p,
        "probabilities": {key: p if key == profile else (1-p)/7 for key in laya.CRITERIA}}},
        "usage": {"input_tokens": 90, "output_tokens": 0, "truncated": False,
                  "state_tokens_dropped": 0, "truncated_questions": []}}


class ConfigurationTests(unittest.TestCase):
    def test_defaults_and_older_policies_do_not_enable_inference(self):
        self.assertEqual(laya.config()["mode"], "rules")
        settings = router.policy()
        self.assertEqual(settings["classifier"]["mode"], "rules")
        del settings["classifier"]
        router.validate_policy(settings)
        for mode in ("rules", "shadow", "laya"):
            settings["classifier"] = {"mode": mode}
            router.validate_policy(settings)

    def test_bad_settings_are_rejected_before_any_network_request(self):
        cases = [None, [], {"backend": "magic"}, {"mode": "guess"}, {"mode": []},
                 {"model": "../../weights"}, {"model": "jev-latest\n"},
                 {"timeout_ms": True}, {"timeout_ms": 0}, {"timeout_ms": 10001},
                 {"max_input_chars": 9000}, {"api_key_env": "bad\nheader"},
                 {"min_probability": True}, {"min_probability": float("nan")},
                 {"min_probability": float("inf")}, {"min_probability": 10**500}]
        for value in cases:
            settings = router.policy()
            settings["classifier"] = value
            with self.subTest(value=value), self.assertRaises(router.RouterError):
                router.validate_policy(settings)

    def test_only_literal_loopback_endpoint_is_allowed(self):
        for endpoint in ("http://127.0.0.1:8000/v1/systemone", "http://[::1]:9010/v1/systemone"):
            laya.config({"endpoint": endpoint})
        for endpoint in ("https://example.com/v1/systemone", "http://localhost:8000/v1/systemone",
                         "http://127.0.0.1:0/v1/systemone", "http://127.0.0.1:8000/other",
                         "http://user:secret@127.0.0.1:8000/v1/systemone",
                         "http://127.0.0.1:8000/v1/systemone?prompt=private",
                         "http://127.0.0.1:8000/v1/systemone#fragment", "file:///tmp/laya", 12):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                laya.config({"endpoint": endpoint})


class AnswerTests(unittest.TestCase):
    def test_profile_and_probability_contract(self):
        cfg = laya.config()
        self.assertEqual(laya.recommendation(answer(), cfg)["profile"], "coding")
        self.assertIsNone(laya.recommendation(answer("retain"), cfg)["profile"])
        self.assertEqual(laya.recommendation(answer(p=0.6), cfg)["status"], "low_probability")
        value = answer()
        value["answers"]["profile"]["confidence"] = 0.001
        self.assertEqual(laya.recommendation(value, cfg)["status"], "recommended")
        value["answers"]["profile"]["abstention"] = "abstained"
        self.assertEqual(laya.recommendation(value, cfg)["status"], "abstained")

    def test_truncation_collapsed_choices_and_missing_metadata_are_rejected(self):
        for usage in ({}, {"truncated": True}, {"truncated": False, "state_tokens_dropped": True},
                      {"truncated": False, "state_tokens_dropped": 1},
                      {"truncated": False, "state_tokens_dropped": 0, "options": {"profile": {"distinct": 2}}}):
            value = answer()
            value["usage"] = usage
            with self.subTest(usage=usage), self.assertRaises(laya.ClassifierFailure):
                laya.recommendation(value, laya.config())

    def test_invalid_answers_never_become_profiles_or_diagnostics(self):
        wrong_checkpoint = answer()
        wrong_checkpoint["routing"]["model"] = "english"
        with self.assertRaisesRegex(laya.ClassifierFailure, "checkpoint"):
            laya.recommendation(wrong_checkpoint, laya.config())
        for change in ({"choice": "arbitrary-model"}, {"choice": []}, {"probabilities": []},
                       {"probabilities": {"coding": 1}}, {"answer_confidence": True},
                       {"answer_confidence": 0.1}, {"type": "text"}):
            value = answer()
            value["answers"]["profile"].update(change)
            with self.subTest(change=change), self.assertRaises(laya.ClassifierFailure):
                laya.recommendation(value, laya.config())
        for bad in (float("nan"), True, -1, 2, float("inf")):
            value = answer()
            value["answers"]["profile"]["probabilities"]["coding"] = bad
            with self.subTest(bad=bad), self.assertRaises(laya.ClassifierFailure):
                laya.recommendation(value, laya.config())


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_rules_and_oversized_requests_do_not_contact_service(self):
        async def forbidden(*args):
            self.fail("Unexpected inference")
        client = laya.LayaClient(request=forbidden)
        self.assertEqual((await client.assess("anything", {}))["reason"], "rules_mode")
        self.assertEqual((await client.assess("x" * 4001, {"mode": "shadow"}))["reason"], "input_too_large")

    async def test_prompt_stays_only_in_request_and_reports_allowlisted_fields(self):
        secret = "Make invoice downloads available PRIVATE_FIXTURE"
        async def request(settings, payload):
            self.assertEqual(payload["state"], {"request": secret, "previous_profile": "easy", "followup": True})
            self.assertEqual(set(payload["questions"]["profile"]["criteria"]), set(laya.CRITERIA))
            value = answer()
            value["private"] = secret
            value["answers"]["profile"]["explanation"] = secret
            return value
        report = await laya.LayaClient(request=request).assess(secret, {"mode": "shadow"}, "easy", True)
        self.assertEqual(report["status"], "recommended")
        self.assertNotIn(secret, json.dumps(report))

    async def test_total_timeout_and_cooldown_avoid_repeated_service_calls(self):
        calls = []
        async def silent(*args):
            calls.append(1)
            await asyncio.sleep(10)
        now = [100]
        client = laya.LayaClient(request=silent, clock=lambda: now[0])
        cfg = {"mode": "shadow", "timeout_ms": 100}
        report = await asyncio.wait_for(client.assess("some task", cfg), 1)
        self.assertEqual(report["reason"], "timeout")
        self.assertEqual((await client.assess("next task", cfg))["reason"], "service_cooldown")
        self.assertEqual(len(calls), 1)
        now[0] += 31
        self.assertEqual((await client.assess("next task", cfg))["reason"], "timeout")
        self.assertEqual(len(calls), 2)

    async def test_concurrent_request_is_not_queued_and_cancellation_releases_client(self):
        entered = asyncio.Event()
        async def wait(*args):
            entered.set()
            await asyncio.Event().wait()
        client = laya.LayaClient(request=wait)
        first = asyncio.create_task(client.assess("task", {"mode": "shadow"}))
        await entered.wait()
        self.assertEqual((await client.assess("task2", {"mode": "shadow"}))["reason"], "service_busy")
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        self.assertFalse(client.busy)


class BufferWriter:
    def __init__(self):
        self.buffer = b""
        self.transport = self
        self.closed = False
    def write(self, data):
        self.buffer += data
    async def drain(self):
        pass
    def close(self):
        self.closed = True
    def abort(self):
        self.closed = True


class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_loopback_http_round_trip_when_host_permits_binding(self):
        observed = []
        finished = asyncio.Event()
        async def peer(reader, writer):
            try:
                head = (await reader.readuntil(b"\r\n\r\n")).decode()
                size = next(int(line.split(":", 1)[1]) for line in head.split("\r\n") if line.startswith("Content-Length:"))
                observed.append(json.loads(await reader.readexactly(size)))
                body = json.dumps(answer()).encode()
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body[:20])
                await writer.drain()
                writer.write(body[20:])
                await writer.drain()
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass
                finished.set()
        try:
            server = await asyncio.start_server(peer, "127.0.0.1", 0)
        except OSError as error:
            if error.errno in (errno.EPERM, errno.EACCES):
                self.skipTest("Host sandbox denies loopback binding; buffered HTTP fixtures still run")
            raise
        async with server:
            port = server.sockets[0].getsockname()[1]
            cfg = laya.config({"mode": "shadow", "endpoint": f"http://127.0.0.1:{port}/v1/systemone"})
            with patch.dict(os.environ, {}, clear=True):
                report = await laya.LayaClient().assess("Make downloads possible", cfg)
            await asyncio.wait_for(finished.wait(), 2)
        self.assertEqual(report["status"], "recommended")
        self.assertEqual(observed[0]["state"]["request"], "Make downloads possible")

    async def exchange(self, response, env=None):
        reader = asyncio.StreamReader()
        reader.feed_data(response)
        reader.feed_eof()
        writer = BufferWriter()
        async def connect(host, port, **kwargs):
            self.assertEqual((host, port), ("127.0.0.1", 8000))
            return reader, writer
        with patch.object(laya.asyncio, "open_connection", connect), patch.dict(os.environ, env or {}, clear=True):
            try:
                result = await laya.exchange(laya.config(), {"state": "héllo"})
                return result, writer
            finally:
                self.assertTrue(writer.closed)

    async def test_http_post_has_literal_target_correct_lengths_and_optional_auth(self):
        body = json.dumps(answer()).encode()
        raw = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        result, writer = await self.exchange(raw, {"LAYA_API_KEY": "fixture-key", "HTTP_PROXY": "http://untrusted.invalid"})
        self.assertEqual(result, answer())
        headers, request = writer.buffer.split(b"\r\n\r\n", 1)
        self.assertIn(b"POST /v1/systemone HTTP/1.1", headers)
        self.assertIn(b"Authorization: Bearer fixture-key", headers)
        self.assertIn(f"Content-Length: {len(request)}".encode(), headers)
        self.assertEqual(json.loads(request), {"state": "héllo"})

    async def test_redirects_wrong_encoding_oversize_and_duplicate_json_fail(self):
        invalid = [b"HTTP/1.1 302 Found\r\nLocation: http://remote.invalid\r\n\r\n",
                   b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 999999\r\n\r\n",
                   b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n",
                   b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 13\r\n\r\n{"x":1,"x":2}']
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises((laya.ClassifierFailure, ValueError)):
                await self.exchange(raw)


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = router.policy()
        self.settings["classifier"] = {"mode": "shadow"}
        self.calls = []
        self.response = answer()
        async def request(settings, payload):
            self.calls.append(deepcopy(payload))
            return deepcopy(self.response)
        self.state = TurnRouter(settings=lambda: self.settings, record=MemoryRun)
        self.state.classifier = laya.LayaClient(request=request)

    async def accept(self, text, accept=True):
        async def catalog():
            return CATALOG
        original = prompt(text)
        saved = deepcopy(original)
        changed, run = await self.state.prepare(original, catalog)
        self.assertEqual(original, saved)
        expected = deepcopy(original)
        for field in ("model", "effort"):
            expected["params"][field] = changed["params"][field]
        for field in ("model", "reasoning_effort"):
            expected["params"]["collaborationMode"]["settings"][field] = changed["params"]["collaborationMode"]["settings"][field]
        self.assertEqual(changed, expected)
        if accept:
            self.state.observe_response("turn/start", changed["params"], {"result": {"turn": {"id": "accepted"}}}, run.record)
        return choice_from(changed["params"]), run.record

    async def test_shadow_disagreement_does_not_change_initial_or_followup_selection(self):
        choice, record = await self.accept("List files")
        self.assertEqual(choice["model"], "gpt-6-luna")
        self.assertEqual(record["classifier"]["proposed_profile"], "coding")
        self.assertFalse(record["classifier"]["used"])
        self.assertFalse(record["classifier"]["agrees_with_rules"])
        choice, record = await self.accept("Make invoice downloads available to customers")
        self.assertEqual(choice["model"], "gpt-6-luna")
        self.assertEqual(record["classifier"]["proposed_profile"], "coding")

    async def test_active_classification_handles_unmatched_and_wrongly_matched_tasks(self):
        self.settings["classifier"]["mode"] = "laya"
        choice, record = await self.accept("Make invoice downloads available to customers")
        self.assertEqual(choice, {"model": "gpt-6.1-sol", "effort": "medium"})
        self.assertTrue(record["classifier"]["used"])
        self.response = answer("planning")
        choice, record = await self.accept("Implement a compiler optimization pass")
        self.assertEqual(choice["effort"], "high")
        self.assertEqual(record["selection"]["kind"], "phase")

    async def test_low_probability_preserves_followup_and_uses_initial_rules(self):
        self.settings["classifier"]["mode"] = "laya"
        self.response = answer(p=0.6)
        choice, record = await self.accept("List files")
        self.assertEqual(choice["model"], "gpt-6-luna")
        choice, record = await self.accept("Implement pagination")
        self.assertEqual(choice["model"], "gpt-6-luna")
        self.assertEqual(record["classifier"]["status"], "low_probability")
        self.assertFalse(record["classifier"]["used"])

    async def test_laya_cannot_bypass_retention_or_trigger_arbitrary_downgrades(self):
        self.settings["classifier"]["mode"] = "laya"
        self.response = answer("deep-debug")
        initial, _ = await self.accept("Investigate the deadlock")
        self.response = answer("easy")
        choice, record = await self.accept("Explain the findings in plain language")
        self.assertEqual(choice, initial)
        self.assertEqual(record["selection"]["kind"], "retain")
        choice, record = await self.accept("Summarize these 30 release notes")
        self.assertEqual(choice["model"], "gpt-6-luna")
        self.assertEqual(record["selection"]["kind"], "phase")

    async def test_pins_disabled_task_mode_and_explicit_overrides_bypass_laya(self):
        await self.accept("[route:easy] List files")
        await self.accept("Investigate a deadlock")
        await self.accept("Use Sol with high effort")
        await self.accept("[route:off] Implement it")
        self.settings["enabled"] = False
        await self.accept("New task: Implement it")
        self.assertEqual(self.calls, [])
        self.settings["enabled"] = True
        self.settings["routing_mode"] = "task"
        await self.accept("New task: List files")
        await self.accept("Investigate a deadlock")
        self.assertEqual(len(self.calls), 1)

    async def test_resumed_and_native_choices_bypass_laya_and_unknown_models_still_fail(self):
        for method in ("thread/resume", "thread/fork"):
            self.state.observe_response(method, {}, {"result": {"thread": {"id": "one"}, "model": "gpt-5.6-terra", "reasoningEffort": "high"}})
            choice, _ = await self.accept("Investigate a deadlock")
            self.assertEqual(choice["model"], "gpt-5.6-terra")
        self.state.observe_response("thread/settings/update", {"threadId": "one", "model": "gpt-6-luna", "effort": "low"}, {"result": {}})
        choice, _ = await self.accept("Make downloads possible")
        self.assertEqual(choice, {"model": "gpt-6-luna", "effort": "low"})
        self.assertEqual(self.calls, [])
        self.settings["classifier"]["mode"] = "laya"
        self.settings["profiles"]["coding"]["models"] = ["unavailable-model"]
        previous = deepcopy(self.state.current)
        with self.assertRaisesRegex(router.RouterError, "No configured model"):
            await self.accept("New task: Make downloads possible")
        self.assertEqual(self.state.current, previous)
        self.assertIn("one", self.state.pinned)

    async def test_checks_and_acknowledgments_skip_model_calls(self):
        await self.accept("Implement pagination")
        for text in ("ok", "continue", "thanks", "Run existing tests", "Check git status"):
            _, record = await self.accept(text)
            self.assertEqual(record["classifier"]["status"], "skipped")
        self.assertEqual(len(self.calls), 1)

    async def test_service_errors_do_not_log_echoed_prompt_or_break_followups(self):
        self.settings["classifier"]["mode"] = "laya"
        initial, _ = await self.accept("Implement pagination")
        async def unavailable(*args):
            raise OSError("PRIVATE_REQUEST_TEXT")
        self.state.classifier.request = unavailable
        choice, record = await self.accept("Investigate a deadlock PRIVATE_REQUEST_TEXT")
        self.assertEqual(choice, initial)
        self.assertEqual(record["classifier"]["status"], "error")
        self.assertNotIn("PRIVATE_REQUEST_TEXT", json.dumps(record))

    async def test_rejected_or_missing_ack_never_commits_a_semantic_phase(self):
        self.settings["classifier"]["mode"] = "laya"
        self.response = answer("easy")
        await self.accept("List files")
        initial = deepcopy(self.state.current)
        self.response = answer("deep-debug")
        choice, record = await self.accept("Workers wait forever on each other", accept=False)
        self.assertEqual(choice["model"], "gpt-6-astra")
        self.assertEqual(self.state.current, initial)
        self.assertEqual(self.state.phase["one"], "easy")

    async def test_active_or_ephemeral_turns_never_reach_classifier(self):
        self.state.active.add("one")
        changed, run = await self.state.prepare(prompt("Implement anything"), None)
        self.assertIsNone(run)
        self.state.active.clear()
        self.state.ephemeral.add("one")
        changed, run = await self.state.prepare(prompt("Generate a title"), None)
        self.assertEqual(run.record["thread_kind"], "ephemeral")
        self.assertEqual(self.calls, [])

    async def test_turn_becoming_active_during_classification_is_preserved(self):
        async def request(*args):
            self.state.active.add("one")
            return answer()
        self.state.classifier.request = request
        original = prompt("Make downloads possible")
        async def catalog():
            return CATALOG
        changed, record = await self.state.prepare(original, catalog)
        self.assertIs(changed, original)
        self.assertEqual(record.record["status"], "skipped")

    async def test_native_selection_acknowledged_during_classifier_wait_takes_priority(self):
        self.settings["classifier"]["mode"] = "laya"
        async def request(*args):
            self.state.observe_response("thread/settings/update", {"threadId": "one", "model": "gpt-5.6-terra", "effort": "high"}, {"result": {}})
            return answer("coding")
        self.state.classifier.request = request
        choice, record = await self.accept("Make downloads possible")
        self.assertEqual(choice, {"model": "gpt-5.6-terra", "effort": "high"})
        self.assertEqual(record["selection"]["kind"], "native")
        self.assertTrue(record["selection"]["pinned"])
        self.assertFalse(record["classifier"]["used"])


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "evals/laya_compare.py"
        spec = importlib.util.spec_from_file_location("laya_evaluation", path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_listing_is_offline_and_corpus_has_expected_scope(self):
        with patch.object(self.module.laya, "LayaClient", side_effect=AssertionError("No inference")), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(self.module.main([]), 0)
        self.assertIn("Offline listing only", output.getvalue())
        cases = self.module.read_cases(self.module.CASES)
        self.assertEqual(len(cases), 24)
        self.assertTrue(any("previous" in case for case in cases))

    def test_comparison_saves_private_report_without_prompts_and_refuses_overwrite(self):
        async def request(*args):
            return answer("coding")
        client = laya.LayaClient(request=request)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            args = ["--run", "--case", "invoice-download", "--output", str(path)]
            with patch.object(self.module.laya, "LayaClient", return_value=client), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(self.module.main(args), 0)
                record = json.loads(path.read_text())
                self.assertEqual(record["summary"]["usable_recommendations"], 1)
                self.assertEqual(record["summary"]["effective_matches_including_fallbacks"], 1)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertNotIn("customers", path.read_text())
                original = path.read_bytes()
                self.assertEqual(self.module.main(args), 2)
                self.assertEqual(path.read_bytes(), original)

    def test_comparison_stops_on_service_error_instead_of_scoring_fallbacks_as_model_success(self):
        calls = []
        async def unavailable(*args):
            calls.append(1)
            raise OSError("private error")
        client = laya.LayaClient(request=unavailable)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            with patch.object(self.module.laya, "LayaClient", return_value=client), redirect_stdout(io.StringIO()):
                self.assertEqual(self.module.main(["--run", "--output", str(path)]), 2)
            self.assertEqual(len(calls), 1)
            report = json.loads(path.read_text())
            self.assertEqual(report["summary"]["usable_recommendations"], 0)
            self.assertEqual(report["summary"]["evaluated"], 1)
            self.assertNotIn("private error", path.read_text())


if __name__ == "__main__":
    unittest.main()

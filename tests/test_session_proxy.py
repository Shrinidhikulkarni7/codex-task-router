import asyncio
from copy import deepcopy
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/codex-model-router/scripts"))
import router
from session_proxy import Bridge, TurnRouter, WebSocket, choice_from, serve_connection


CATALOG = [
    {"model": name, "defaultReasoningEffort": "medium", "supportedReasoningEfforts": [{"reasoningEffort": e} for e in ("low", "medium", "high", "xhigh")]}
    for name in ("gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna", "gpt-5.6-terra")
]

# Both transports exercise the independent native_peer conversation. Keep its
# expected outcomes shared so a locally skipped socket test cannot drift.
CONVERSATION_SELECTIONS = [
    ["gpt-6.1-sol", "high"], ["gpt-6.1-sol", "high"], ["gpt-6.1-sol", "medium"],
    ["gpt-5.6-terra", "medium"], ["gpt-5.6-terra", "medium"],
    ["gpt-6-astra", "xhigh"], ["gpt-6-astra", "xhigh"],
    ["gpt-6-luna", "medium"], ["gpt-6.1-sol", "medium"], ["gpt-6.1-sol", "medium"],
    ["gpt-6-astra", "xhigh"], ["gpt-6-astra", "xhigh"],
    ["gpt-6-luna", "medium"], ["gpt-6-luna", "medium"],
]


class MemoryRun:
    def __init__(self):
        self.record = {"status": "started"}

    def update(self, **fields):
        self.record.update(fields)


def prompt(text, request_id=1, thread="one", mode="default"):
    return {"id": request_id, "method": "turn/start", "params": {
        "threadId": thread, "input": [{"type": "text", "text": text}],
        "model": "gpt-6-astra", "effort": "high",
        "collaborationMode": {"mode": mode, "settings": {"model": "gpt-6-astra", "reasoning_effort": "high", "developer_instructions": "Preserve these instructions"}},
        "approvalPolicy": {"granular": {"sandbox_approval": False, "mcp_elicitations": True}},
        "approvalsReviewer": "auto_review", "permissions": "workspace", "serviceTier": "default",
    }}


class TurnRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = router.policy()
        self.runs = []

        def record():
            run = MemoryRun()
            self.runs.append(run)
            return run

        self.state = TurnRouter(settings=lambda: self.config, record=record)
        self.calls = 0

    async def catalog(self):
        self.calls += 1
        return CATALOG

    async def test_prompt_mode_routes_each_prompt_in_one_thread(self):
        self.config["routing_mode"] = "prompt"
        tasks = [
            ("Plan the cache architecture", "gpt-6.1-sol", "high"),
            ("Run pwd and list the first five entries", "gpt-6-luna", "medium"),
            ("Implement the approved plan", "gpt-6.1-sol", "medium"),
            ("Use Terra to implement the approved plan", "gpt-5.6-terra", "medium"),
            ("Run the existing unit tests", "gpt-6-luna", "low"),
            ("Investigate the intermittent deadlock", "gpt-6-astra", "xhigh"),
            ("continue", "gpt-6-astra", "xhigh"),
        ]
        for index, (text, model, effort) in enumerate(tasks):
            with self.subTest(text=text):
                original = prompt(text, index)
                before = deepcopy(original)
                changed, run = await self.state.prepare(original, self.catalog)
                self.assertEqual(choice_from(changed["params"]), {"model": model, "effort": effort})
                self.assertEqual(changed["params"]["threadId"], "one")
                self.assertEqual(original, before)
                self.state.observe_response("turn/start", changed["params"], {"result": {"turn": {"id": str(index)}}})
                self.assertEqual(run.record["status"], "submitted")
        self.assertNotIn("Plan the cache architecture", json.dumps([r.record for r in self.runs]))

    async def test_only_model_and_effort_change_in_both_override_locations(self):
        original = prompt("List files in the current directory")
        changed, _ = await self.state.prepare(original, self.catalog)
        expected = deepcopy(original)
        expected["params"].update(model="gpt-6-luna", effort="medium")
        expected["params"]["collaborationMode"]["settings"].update(model="gpt-6-luna", reasoning_effort="medium")
        self.assertEqual(changed, expected)

    async def test_plan_mode_routes_an_ambiguous_task(self):
        changed, _ = await self.state.prepare(prompt("How should this work?", mode="plan"), self.catalog)
        self.assertEqual(choice_from(changed["params"]), {"model": "gpt-6.1-sol", "effort": "high"})

    async def test_off_and_disabled_policy_pass_through_exactly(self):
        for text, enabled in [("[route:off] Run tests", True), ("Run tests", False)]:
            self.config["enabled"] = enabled
            original = prompt(text)
            changed, run = await self.state.prepare(original, self.catalog)
            self.assertIs(changed, original)
            self.assertEqual(run.record["status"], "skipped")
        self.assertEqual(self.calls, 0)

    async def test_explicit_model_effort_and_directive_priority(self):
        cases = [
            ("Use Luna with high effort to review this", "gpt-6-luna", "high"),
            ("Use gpt-5.6-terra to implement pagination", "gpt-5.6-terra", "medium"),
            ("[route:planning] Use Luna for this", "gpt-6.1-sol", "high"),
            ("Use low effort for this step", "gpt-6-astra", "low"),
        ]
        for text, model, effort in cases:
            changed, _ = await self.state.prepare(prompt(text), self.catalog)
            self.assertEqual(choice_from(changed["params"]), {"model": model, "effort": effort})

    async def test_manual_settings_take_priority_for_one_prompt(self):
        self.config["routing_mode"] = "prompt"
        self.state.observe_response("thread/settings/update", {"threadId": "one", "model": "gpt-6-astra", "effort": "high"}, {"result": {}})
        original = prompt("Run tests")
        changed, run = await self.state.prepare(original, self.catalog)
        self.assertIs(changed, original)
        self.assertEqual(run.record["status"], "skipped")
        self.state.observe_response("turn/start", changed["params"], {"result": {"turn": {"id": "manual"}}})
        changed, _ = await self.state.prepare(original, self.catalog)
        self.assertEqual(changed["params"]["model"], "gpt-6-luna")

    async def test_active_turn_steering_and_tool_output_are_not_rerouted(self):
        original = prompt("Run tests")
        self.state.observe_notification({"method": "turn/started", "params": {"threadId": "one"}})
        changed, run = await self.state.prepare(original, self.catalog)
        self.assertIs(changed, original)
        self.assertIsNone(run)
        self.state.observe_notification({"method": "turn/completed", "params": {"threadId": "one"}})
        for method in ("turn/steer", "thread/read", "item/tool/call"):
            request = dict(original, method=method)
            changed, run = await self.state.prepare(request, self.catalog)
            self.assertIs(changed, request)
            self.assertIsNone(run)
        original["params"]["toolOutput"] = {"name": "check", "output": "Plan a task"}
        changed, _ = await self.state.prepare(original, self.catalog)
        self.assertIs(changed, original)
        self.assertEqual(self.calls, 0)

    async def test_unavailable_model_does_not_silently_substitute(self):
        self.config["profiles"]["easy"]["models"] = ["missing-model"]
        with self.assertRaisesRegex(router.RouterError, "No configured model"):
            await self.state.prepare(prompt("List files"), self.catalog)
        self.assertEqual(self.runs[-1].record["status"], "failed")

    async def test_turn_started_during_catalog_lookup_keeps_its_admitted_model(self):
        async def catalog():
            self.state.active.add("one")
            return CATALOG

        original = prompt("List files")
        changed, run = await self.state.prepare(original, catalog)
        self.assertIs(changed, original)
        self.assertEqual(run.record["status"], "skipped")

    async def test_resume_preserves_thread_selection_for_continuations(self):
        self.state.observe_response("thread/resume", {}, {"result": {"thread": {"id": "one", "status": {"type": "idle"}}, "model": "gpt-5.6-terra", "reasoningEffort": "medium"}})
        changed, _ = await self.state.prepare(prompt("go ahead"), self.catalog)
        self.assertEqual(choice_from(changed["params"]), {"model": "gpt-5.6-terra", "effort": "medium"})
        self.assertEqual(self.calls, 0)

    async def test_ephemeral_title_tasks_keep_native_settings_without_policy_or_catalog(self):
        # This models the native title task seen in the 0.160.1 trace. "Write"
        # previously caused the title instructions to be classified as coding.
        title = "Generate a concise task title. Write in the user's language.\n\nUser prompt:\nlist files"
        for method in ("thread/start", "thread/resume", "thread/fork"):
            for metadata_source in ("response", "request"):
                with self.subTest(method=method, metadata_source=metadata_source):
                    thread = "temporary-" + method + metadata_source
                    metadata = {"id": thread}
                    params = {}
                    if metadata_source == "response":
                        metadata["ephemeral"] = True
                    else:
                        params["ephemeral"] = True
                    self.state.observe_response(method, params, {"result": {"thread": metadata, "model": "gpt-5.6-luna"}})
                    original = prompt(title, thread=thread)
                    original["params"]["model"] = "gpt-5.6-luna"
                    with patch.object(self.state, "settings", side_effect=AssertionError("Temporary tasks must not load routing policy")):
                        changed, run = await self.state.prepare(original, self.catalog)
                    self.assertIs(changed, original)
                    self.assertEqual(run.record["status"], "skipped")
                    self.assertEqual(run.record["thread_kind"], "ephemeral")
                    self.assertNotIn("profile", run.record)
        self.assertEqual(self.calls, 0)
        # The adjacent user-facing conversation must still be routed normally.
        changed, _ = await self.state.prepare(prompt("List files"), self.catalog)
        self.assertEqual(changed["params"]["model"], "gpt-6-luna")

    async def test_started_notification_can_identify_ephemeral_thread_before_response(self):
        self.state.observe_notification({"method": "thread/started", "params": {
            "thread": {"id": "one", "ephemeral": True}}})
        # Partial lifecycle metadata must not erase the known thread kind.
        self.state.observe_response("thread/start", {}, {"result": {"thread": {"id": "one"}}})
        original = prompt("[route:coding] Write a title")
        changed, run = await self.state.prepare(original, self.catalog)
        self.assertIs(changed, original)
        self.assertEqual(run.record["thread_kind"], "ephemeral")
        self.assertEqual(self.calls, 0)

    async def test_closing_a_temporary_thread_releases_only_its_state(self):
        self.state.current["user-thread"] = {"model": "gpt-6-luna", "effort": "medium"}
        self.state.observe_response("thread/start", {}, {"result": {"thread": {
            "id": "one", "ephemeral": True, "status": {"type": "active"}}}})
        self.state.manual_next.add("one")
        self.state.active_turns["one"] = "turn-one"
        self.state.observe_notification({"method": "thread/closed", "params": {"threadId": "one"}})
        self.assertNotIn("one", self.state.ephemeral)
        self.assertNotIn("one", self.state.current)
        self.assertNotIn("one", self.state.active)
        self.assertNotIn("one", self.state.active_turns)
        self.assertNotIn("one", self.state.manual_next)
        self.assertIn("user-thread", self.state.current)

    async def test_failed_thread_start_does_not_mark_an_unrelated_thread_ephemeral(self):
        self.state.observe_response("thread/start", {"ephemeral": True}, {
            "error": {"message": "failed"}, "result": {"thread": {"id": "one", "ephemeral": True}}})
        changed, run = await self.state.prepare(prompt("List files"), self.catalog)
        self.assertEqual(changed["params"]["model"], "gpt-6-luna")
        self.assertEqual(run.record["status"], "submitted")


class QueueWire:
    def __init__(self, incoming, outgoing):
        self.incoming, self.outgoing = incoming, outgoing

    async def receive(self):
        return await self.incoming.get()

    async def send(self, message):
        await self.outgoing.put(deepcopy(message))


def wire_pair():
    first, second = asyncio.Queue(), asyncio.Queue()
    return QueueWire(first, second), QueueWire(second, first)


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_conversation_forwards_approvals_and_routes_before_admission(self):
        client, downstream = wire_pair()
        upstream, server = wire_pair()
        records = []

        def record():
            run = MemoryRun()
            records.append(run)
            return run

        bridge = Bridge(downstream, upstream, TurnRouter(record=record), claim=lambda *_: None)
        observed = []
        approval = {"id": 101, "method": "item/commandExecution/requestApproval", "params": {"threadId": "one", "command": "test-command", "availableDecisions": ["decline", "accept"]}}
        decision = {"id": 101, "result": {"decision": "decline"}}

        async def serve():
            while True:
                message = await server.receive()
                method = message.get("method")
                if method == "model/list":
                    await server.send({"id": message["id"], "result": {"data": CATALOG}})
                elif method == "initialize":
                    await server.send({"id": message["id"], "result": {"userAgent": "fixture"}})
                elif method == "turn/start":
                    params = message["params"]
                    observed.append(deepcopy(params))
                    turn = {"id": str(len(observed)), "status": "inProgress"}
                    await server.send({"method": "turn/started", "params": {"threadId": "one", "turn": turn}})
                    await server.send(approval)
                    self.assertEqual(await server.receive(), decision)
                    await server.send({"id": message["id"], "result": {"turn": turn}})
                    await server.send({"method": "turn/completed", "params": {"threadId": "one", "turn": dict(turn, status="completed")}})
                else:
                    self.fail("Unexpected request: " + str(method))

        jobs = [asyncio.create_task(bridge.run()), asyncio.create_task(serve())]
        try:
            await client.send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "native-cli"}}})
            self.assertEqual(await asyncio.wait_for(client.receive(), 2), {"id": 1, "result": {"userAgent": "fixture"}})
            for text in ["Plan the cache architecture", "New task: List files in the current directory", "Use Terra to implement pagination", "[route:deep-debug] Investigate a deadlock"]:
                # Client and server request IDs may collide; their directions differ.
                await client.send(prompt(text, 101))
                received_result = False
                while True:
                    message = await asyncio.wait_for(client.receive(), 2)
                    if message.get("method") == approval["method"]:
                        self.assertEqual(message, approval)
                        await client.send(decision)
                    elif message.get("id") == 101:
                        self.assertIn("result", message)
                        received_result = True
                    elif message.get("method") == "turn/completed":
                        self.assertTrue(received_result)
                        break
            self.assertEqual([choice_from(p) for p in observed], [
                {"model": "gpt-6.1-sol", "effort": "high"},
                {"model": "gpt-6-luna", "effort": "medium"},
                {"model": "gpt-5.6-terra", "effort": "medium"},
                {"model": "gpt-6-astra", "effort": "xhigh"},
            ])
            self.assertEqual({p["threadId"] for p in observed}, {"one"})
            self.assertTrue(all(r.record["status"] == "accepted" and r.record["turn_status"] == "completed" for r in records))
        finally:
            for job in jobs:
                job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)

    async def test_catalog_failure_is_returned_without_starting_a_task(self):
        client, downstream = wire_pair()
        upstream, server = wire_pair()
        bridge = Bridge(downstream, upstream, TurnRouter(record=MemoryRun), claim=lambda *_: None)
        task = asyncio.create_task(bridge.run())
        try:
            await client.send(prompt("List files", 5))
            query = await asyncio.wait_for(server.receive(), 2)
            self.assertEqual(query["method"], "model/list")
            await server.send({"id": query["id"], "error": {"message": "catalog unavailable", "code": -1}})
            result = await asyncio.wait_for(client.receive(), 2)
            self.assertEqual(result["id"], 5)
            self.assertIn("catalog unavailable", result["error"]["message"])
            self.assertTrue(server.incoming.empty())
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


class BufferWriter:
    def __init__(self):
        self.data = bytearray()

    def write(self, value):
        self.data.extend(value)

    async def drain(self):
        pass


def raw_frame(payload, opcode=1, masked=True, final=True):
    length = len(payload)
    size = length if length < 126 else (126 if length <= 65535 else 127)
    data = bytes(((128 if final else 0) | opcode, (128 if masked else 0) | size))
    if size == 126:
        data += struct.pack("!H", length)
    elif size == 127:
        data += struct.pack("!Q", length)
    if masked:
        mask = b"test"
        data += mask
        payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
    return data + payload


class WireTests(unittest.IsolatedAsyncioTestCase):
    async def test_masked_fragments_and_ping_are_handled(self):
        reader, writer = asyncio.StreamReader(), BufferWriter()
        reader.feed_data(raw_frame(b'{"text":', final=False) + raw_frame(b"ping", opcode=9) + raw_frame(b'"hello"}', opcode=0))
        wire = WebSocket(reader, writer, client=False)
        self.assertEqual(await wire.receive(), {"text": "hello"})
        self.assertEqual(bytes(writer.data), raw_frame(b"ping", opcode=10, masked=False))

    async def test_large_unicode_message_and_both_masking_directions(self):
        message = {"text": "\u2605" * 30000}
        for client in (True, False):
            reader, writer = asyncio.StreamReader(), BufferWriter()
            reader.feed_data(raw_frame(json.dumps(message, ensure_ascii=False).encode(), masked=not client))
            wire = WebSocket(reader, writer, client=client)
            self.assertEqual(await wire.receive(), message)
            await wire.send(message)
            self.assertEqual(bool(writer.data[1] & 128), client)

    async def test_bad_masking_and_oversized_frames_are_rejected(self):
        for raw in (raw_frame(b"{}", masked=False), b"\x81\xff" + (2**40).to_bytes(8, "big")):
            reader = asyncio.StreamReader()
            reader.feed_data(raw)
            with self.assertRaises(router.RouterError):
                await WebSocket(reader, BufferWriter(), client=False).receive()

    async def test_independent_websocket_peer_accepts_client_handshake_and_frames(self):
        process = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).with_name("ws_peer.py")), "fragmented", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            wire = WebSocket(process.stdout, process.stdin, client=True)
            await wire.handshake()
            self.assertEqual((await wire.receive())["method"], "notice")
            await wire.send({"id": 1, "method": "initialize", "params": {"capabilities": {"experimentalApi": True}}})
            self.assertEqual((await wire.receive())["id"], 1)
            await wire.send({"method": "initialized", "params": {}})
            await wire.send({"id": 2, "method": "model/list", "params": {}})
            self.assertEqual((await wire.receive())["result"]["data"][0]["model"], "gpt-6-luna")
        finally:
            process.terminate()
            await process.wait()


class NativeLauncherTests(unittest.TestCase):
    def test_native_style_session_routes_tasks_over_real_unix_websockets(self):
        with tempfile.TemporaryDirectory(prefix="router-smoke-", dir="/tmp") as directory:
            root = Path(directory)
            peer = Path(__file__).with_name("native_peer.py").resolve()
            executable = root / "codex-fixture"
            executable.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(peer)!r}, run_name='__main__')\n")
            executable.chmod(0o700)
            scripts = str(Path(router.__file__).parent)
            # Configure only router diagnostics, never HOME or Codex's user config.
            program = f"import sys; sys.path.insert(0, {scripts!r}); import router; from pathlib import Path; router.STATE_DIR = Path({str(root / 'state')!r}); sys.exit(router.main(sys.argv[1:]))"
            result = subprocess.run([sys.executable, "-c", program, "auto", "--codex", str(executable)], capture_output=True, text=True, timeout=20)
            if result.returncode == 1 and "Cannot create the local routing socket: [Errno 1] Operation not permitted" in result.stderr:
                self.skipTest("Host sandbox denies binding Unix sockets; the full wire conversation is tested through pipes")
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output, {"thread": "one", "selections": CONVERSATION_SELECTIONS})
            records = [json.loads(p.read_text()) for p in (root / "state").glob("run-*.json")]
            self.assertEqual(len(records), len(CONVERSATION_SELECTIONS))
            self.assertTrue(all(r["source"] == "session-proxy" and r["status"] == "accepted" and r["turn_status"] == "completed" for r in records))
            self.assertNotIn("Plan the cache architecture", json.dumps(records))


class FullWireConversationTests(unittest.IsolatedAsyncioTestCase):
    async def test_independent_native_client_and_daemon_route_tasks_over_pipes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            peer = Path(__file__).with_name("native_peer.py").resolve()
            executable = root / "codex-fixture"
            executable.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(peer)!r}, run_name='__main__')\n")
            executable.chmod(0o700)
            process = await asyncio.create_subprocess_exec(sys.executable, str(peer), "--fixture-stdio-client", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            records = []

            def record():
                run = MemoryRun()
                records.append(run)
                return run

            try:
                with patch.object(router, "STATE_DIR", root / "state"):
                    await asyncio.wait_for(serve_connection(process.stdout, process.stdin, SimpleNamespace(codex=str(executable), sock=None), TurnRouter(record=record)), 10)
                await asyncio.wait_for(process.wait(), 2)
                stderr = (await process.stderr.read()).decode()
                self.assertEqual(process.returncode, 0, stderr)
                output = json.loads(stderr)
                self.assertEqual(output["thread"], "one")
                self.assertEqual(output["selections"], CONVERSATION_SELECTIONS)
                self.assertEqual(len(records), len(CONVERSATION_SELECTIONS))
                self.assertTrue(all(r.record["status"] == "accepted" and r.record["turn_status"] == "completed" for r in records))
                self.assertEqual(list((root / "state").glob("*")), [], "Unexpected diagnostics or uncleaned prompt claims")
            finally:
                if process.returncode is None:
                    process.terminate()
                    await process.wait()

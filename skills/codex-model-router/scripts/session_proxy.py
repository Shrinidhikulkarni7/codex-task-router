"""Route native Codex TUI prompts before turn/start admits their model."""

import asyncio
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import struct
import sys
import tempfile
import uuid

import router


class WebSocket:
    """Minimal text WebSocket with bounded messages and no extensions."""

    MAX_MESSAGE = 16 * 1024 * 1024
    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self, reader, writer, client):
        self.reader, self.writer, self.client = reader, writer, client

    async def headers(self):
        try:
            raw = await asyncio.wait_for(self.reader.readuntil(b"\r\n\r\n"), 8)
        except asyncio.LimitOverrunError as error:
            raise router.RouterError("WebSocket handshake headers exceeded the size limit") from error
        if len(raw) > 16384:
            raise router.RouterError("WebSocket handshake headers exceeded the size limit")
        lines = raw.decode("iso-8859-1").split("\r\n")
        headers = {}
        for line in lines[1:]:
            if not line:
                continue
            name, sep, value = line.partition(":")
            if not sep:
                raise router.RouterError("Invalid WebSocket handshake header")
            key = name.lower().strip()
            headers[key] = headers.get(key, "") + ("," if key in headers else "") + value.strip()
        if (headers.get("upgrade", "").lower() != "websocket"
                or "upgrade" not in {v.strip().lower() for v in headers.get("connection", "").split(",")}):
            raise router.RouterError("Invalid WebSocket upgrade")
        return lines[0], headers

    @classmethod
    def accept_key(cls, key):
        return base64.b64encode(hashlib.sha1((key + cls.GUID).encode("ascii")).digest()).decode("ascii")

    async def handshake(self):
        if self.client:
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            self.writer.write(("GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
                               "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
                               f"Sec-WebSocket-Key: {key}\r\n\r\n").encode("ascii"))
            await self.writer.drain()
            line, headers = await self.headers()
            if line.split()[:2] != ["HTTP/1.1", "101"] or headers.get("sec-websocket-accept") != self.accept_key(key):
                raise router.RouterError("Codex rejected the WebSocket handshake")
            if headers.get("sec-websocket-extensions") or headers.get("sec-websocket-protocol"):
                raise router.RouterError("Codex selected an unrequested WebSocket extension")
        else:
            line, headers = await self.headers()
            key = headers.get("sec-websocket-key", "")
            try:
                valid_key = len(base64.b64decode(key, validate=True)) == 16
            except ValueError:
                valid_key = False
            if (line.split()[:1] != ["GET"] or not line.endswith(" HTTP/1.1")
                    or headers.get("sec-websocket-version") != "13"
                    or not valid_key):
                raise router.RouterError("Invalid client WebSocket handshake")
            self.writer.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                               "Connection: Upgrade\r\n"
                               f"Sec-WebSocket-Accept: {self.accept_key(key)}\r\n\r\n").encode("ascii"))
            await self.writer.drain()

    async def frame(self, opcode, payload):
        size = len(payload)
        if size > self.MAX_MESSAGE:
            raise router.RouterError("WebSocket message exceeded the size limit")
        mask_bit = 128 if self.client else 0
        if size < 126:
            header = bytes((128 | opcode, mask_bit | size))
        elif size <= 65535:
            header = bytes((128 | opcode, mask_bit | 126)) + struct.pack("!H", size)
        else:
            header = bytes((128 | opcode, mask_bit | 127)) + struct.pack("!Q", size)
        if self.client:
            mask = os.urandom(4)
            payload = mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.writer.write(header + payload)
        await self.writer.drain()

    async def send(self, message):
        await self.frame(1, json.dumps(message, ensure_ascii=False).encode("utf-8"))

    async def receive(self):
        pieces = bytearray()
        fragmented = False
        while True:
            first, second = await self.reader.readexactly(2)
            final, opcode, masked, size = bool(first & 128), first & 15, bool(second & 128), second & 127
            if first & 112 or masked == self.client:
                raise router.RouterError("Invalid WebSocket extension or masking")
            if opcode >= 8 and (not final or size > 125):
                raise router.RouterError("Invalid WebSocket control frame")
            if size == 126:
                size = struct.unpack("!H", await self.reader.readexactly(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", await self.reader.readexactly(8))[0]
            if size + len(pieces) > self.MAX_MESSAGE:
                raise router.RouterError("WebSocket message exceeded the size limit")
            mask = await self.reader.readexactly(4) if masked else None
            payload = await self.reader.readexactly(size)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 8:
                if len(payload) == 1:
                    raise router.RouterError("Invalid WebSocket close frame")
                await self.frame(8, payload)
                raise EOFError("WebSocket closed")
            if opcode == 9:
                await self.frame(10, payload)
                continue
            if opcode == 10:
                continue
            if opcode == 1 and not fragmented:
                fragmented = True
            elif opcode != 0 or not fragmented:
                raise router.RouterError("Unsupported WebSocket message type")
            pieces.extend(payload)
            if final:
                value = json.loads(pieces.decode("utf-8"))
                if not isinstance(value, dict):
                    raise router.RouterError("Expected a JSON-RPC object")
                return value


def choice_from(params):
    if not isinstance(params, dict):
        return {}
    choice = {key: params[key] for key in ("model", "effort") if params.get(key) is not None}
    mode = params.get("collaborationMode") or {}
    if not isinstance(mode, dict):
        raise router.RouterError("collaborationMode must be an object")
    settings = mode.get("settings") or {}
    if not isinstance(settings, dict):
        raise router.RouterError("collaborationMode.settings must be an object")
    if settings.get("model"):
        choice["model"] = settings["model"]
        if settings.get("reasoning_effort") is not None:
            choice["effort"] = settings["reasoning_effort"]
    return choice


def set_choice(params, choice):
    for key in ("model", "effort"):
        if choice.get(key) is not None:
            params[key] = choice[key]
    # This preset overrides top-level model/effort in Codex's API.
    if isinstance(params.get("collaborationMode"), dict):
        settings = params["collaborationMode"].get("settings")
        if settings is None:
            settings = params["collaborationMode"]["settings"] = {}
        if not isinstance(settings, dict):
            raise router.RouterError("collaborationMode.settings must be an object")
        if choice.get("model"):
            settings["model"] = choice["model"]
        if choice.get("effort") is not None:
            settings["reasoning_effort"] = choice["effort"]


def prompt_text(params):
    if not isinstance(params, dict):
        raise router.RouterError("turn/start params must be an object")
    items = params.get("input", [])
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise router.RouterError("turn/start input must be an array of objects")
    texts = [item.get("text", "") for item in items if item.get("type") == "text"]
    if not all(isinstance(text, str) for text in texts):
        raise router.RouterError("Text input must be a string")
    return "\n".join(texts).strip()


def explicit_selection(task, catalog, policy, current):
    prose = re.split(r"```|\n\s*>", task, maxsplit=1)[0]
    match = re.match(r"\s*(?:please\s+)?(?:use|switch to|stay on|keep using)\s+(?:the\s+)?(gpt-[\w.-]+|sol|terra|luna|astra)\b", prose, re.I)
    effort_match = re.search(r"\b(none|minimal|low|medium|high|xhigh|extra[ -]high|max|ultra)\s+(?:reasoning|effort)\b", prose, re.I)
    if not match and not effort_match:
        return None
    effort = effort_match.group(1).lower().replace("extra-high", "xhigh").replace("extra high", "xhigh") if effort_match else None
    aliases = {"sol": "coding", "terra": "terra", "luna": "easy", "astra": "deep-debug"}
    model = match.group(1).lower() if match else current.get("model")
    if not model:
        raise router.RouterError("Cannot honor an effort request without knowing the selected model")
    if model in aliases:
        return router.select_model(aliases[model], catalog, policy, effort=effort)
    if effort is None:
        entry = next((m for m in catalog if m["model"] == model), {})
        effort = entry.get("defaultReasoningEffort") or "medium"
    return router.select_model(None, catalog, policy, model=model, effort=effort)


class TurnRouter:
    """Keep routing state per thread; never retain prompt contents in diagnostics."""

    def __init__(self, settings=router.policy, record=router.HookRun):
        self.settings, self.record = settings, record
        self.current = {}
        self.active = set()
        self.active_turns = {}
        self.manual_next = set()

    async def prepare(self, message, catalog):
        if message.get("method") != "turn/start" or "id" not in message:
            return message, None
        params = message.get("params") or {}
        if not isinstance(params, dict):
            raise router.RouterError("turn/start params must be an object")
        thread = params.get("threadId")
        if thread is not None and not isinstance(thread, str):
            raise router.RouterError("turn/start threadId must be a string")
        if not thread or thread in self.active or params.get("toolOutput") is not None:
            return message, None
        text = prompt_text(params)
        if not text:
            return message, None
        run = self.record()
        run.update(source="session-proxy", event="turn/start", thread_id=thread)
        try:
            policy = self.settings()
            directive = re.match(r"^\[route:([a-z-]+)\](?:\s|$)", text, re.I)
            if not policy["enabled"] or (directive and directive.group(1).lower() == "off"):
                run.update(status="skipped", reason="Automatic routing disabled for this prompt")
                return message, run
            if thread in self.manual_next and not directive:
                self.manual_next.discard(thread)
                run.update(status="skipped", reason="Manual model selection takes priority for this prompt")
                return message, run
            self.manual_next.discard(thread)
            profile, reason = router.classify(text)
            current = self.current.get(thread, choice_from(params))
            explicit = None
            if not directive and reason.startswith("Explicit model or effort request"):
                explicit = explicit_selection(text, await catalog(), policy, current)
            if explicit:
                choice, reason = explicit, "Explicit model or effort request"
            elif profile:
                choice = router.select_model(profile, await catalog(), policy)
            elif (params.get("collaborationMode") or {}).get("mode") == "plan":
                choice = router.select_model("planning", await catalog(), policy)
                reason = "Codex Plan mode"
            else:
                choice = current
            if thread in self.active:
                run.update(status="skipped", reason="The thread became active during selection; preserve the running turn")
                return message, run
            if not choice.get("model"):
                run.update(status="skipped", reason=reason)
                return message, run
            updated = deepcopy(message)
            set_choice(updated["params"], choice)
            run.update(status="submitted", reason=reason, **{k: choice[k] for k in ("profile", "model", "effort") if k in choice})
            return updated, run
        except Exception as error:
            run.update(status="failed", error=str(error)[:1200])
            raise

    def observe_response(self, method, params, response):
        if "error" in response:
            return
        result = response.get("result") or {}
        if not isinstance(result, dict):
            return
        if method in ("thread/start", "thread/resume", "thread/fork"):
            thread = result.get("thread") or {}
            if not isinstance(thread, dict):
                return
            thread_id = thread.get("id")
            if thread_id:
                self.current[thread_id] = choice_from(dict(result, effort=result.get("reasoningEffort")))
                status = thread.get("status") or {}
                if isinstance(status, dict) and status.get("type") == "active":
                    self.active.add(thread_id)
                elif isinstance(status, dict) and status.get("type") == "idle":
                    self.active.discard(thread_id)
                    self.active_turns.pop(thread_id, None)
        elif method == "thread/settings/update":
            thread_id = params.get("threadId")
            if thread_id and choice_from(params):
                self.current[thread_id] = dict(self.current.get(thread_id, {}), **choice_from(params))
                self.manual_next.add(thread_id)
        elif method == "turn/start" and params.get("threadId"):
            self.current[params["threadId"]] = dict(self.current.get(params["threadId"], {}), **choice_from(params))

    def observe_notification(self, message):
        params = message.get("params") or {}
        if not isinstance(params, dict):
            return
        thread = params.get("threadId")
        if not isinstance(thread, str):
            return
        turn = params.get("turn") or {}
        if not isinstance(turn, dict):
            return
        if message.get("method") == "turn/started":
            self.active.add(thread)
            self.active_turns[thread] = turn.get("id")
        elif message.get("method") == "turn/completed":
            if not self.active_turns.get(thread) or self.active_turns[thread] == turn.get("id"):
                self.active.discard(thread)
                self.active_turns.pop(thread, None)


class Bridge:
    def __init__(self, downstream, upstream, state, claim=router.claim_prompt):
        self.downstream, self.upstream, self.state = downstream, upstream, state
        self.claim = claim
        self.claim_paths = set()
        self.internal = {}
        self.pending = {}
        self.turns = {}
        self.completed = {}
        self.prefix = "codex-router-" + uuid.uuid4().hex + "-"
        self.sequence = 0

    async def request(self, method, params):
        self.sequence += 1
        request_id = self.prefix + str(self.sequence)
        future = asyncio.get_running_loop().create_future()
        self.internal[request_id] = future
        try:
            await self.upstream.send({"id": request_id, "method": method, "params": params})
            response = await asyncio.wait_for(future, 8)
            return router.rpc_result(response, method)
        finally:
            self.internal.pop(request_id, None)

    async def catalog(self):
        models, seen, params = [], set(), {"limit": 100, "includeHidden": False}
        for _ in range(20):
            page, cursor = router.catalog_page(await self.request("model/list", params))
            models.extend(page)
            if not cursor:
                return models
            if cursor in seen:
                raise router.RouterError("Model catalog repeated a pagination cursor")
            seen.add(cursor)
            params["cursor"] = cursor
        raise router.RouterError("Model catalog exceeded pagination limit")

    async def from_client(self):
        while True:
            original = await self.downstream.receive()
            run = None
            path = None
            try:
                message, run = await self.state.prepare(original, self.catalog)
                if message.get("method") == "turn/start" and "id" in message:
                    params = message.get("params") or {}
                    text = prompt_text(params)
                    if text and params.get("threadId"):
                        path = self.claim(params["threadId"], text)
                        if path is not None:
                            self.claim_paths = {p for p in self.claim_paths if p.exists()}
                            self.claim_paths.add(path)
            except (router.RouterError, OSError, ValueError, KeyError, TypeError, asyncio.TimeoutError) as error:
                if run is not None:
                    run.update(status="failed", error=str(error)[:1200])
                await self.downstream.send({"id": original["id"], "error": {"code": -32602, "message": "Model router could not select this turn's model: " + (str(error) or "catalog request timed out")}})
                continue
            if "id" in message and "method" in message:
                # Only these methods need state; never retain the submitted prompt.
                method = message["method"]
                if method in ("thread/start", "thread/resume", "thread/fork", "thread/settings/update", "turn/start"):
                    params = message.get("params") or {}
                    if not isinstance(params, dict):
                        params = {}
                    try:
                        metadata = choice_from(params)
                    except router.RouterError:
                        metadata = {}  # Let Codex validate malformed non-routing requests.
                    metadata["threadId"] = params.get("threadId")
                    self.pending[json.dumps(message["id"])] = (method, metadata, run, path)
            await self.upstream.send(message)

    async def from_server(self):
        while True:
            message = await self.upstream.receive()
            request_id = message.get("id")
            if "method" not in message and isinstance(request_id, str) and request_id.startswith(self.prefix):
                future = self.internal.get(request_id)
                if future is not None and not future.done():
                    future.set_result(message)
                continue
            if "method" not in message and "id" in message:
                pending = self.pending.pop(json.dumps(request_id), None)
                if pending:
                    method, params, run, claim_path = pending
                    self.state.observe_response(method, params, message)
                    if "error" in message and claim_path is not None:
                        try:
                            claim_path.unlink(missing_ok=True)
                        except OSError:
                            pass
                        self.claim_paths.discard(claim_path)
                    if run and run.record["status"] == "submitted":
                        if "error" in message:
                            error = message["error"]
                            detail = error.get("message") if isinstance(error, dict) else None
                            run.update(status="failed", error=(detail if isinstance(detail, str) else "Codex rejected turn/start")[:1200])
                        else:
                            result = message.get("result")
                            turn = result.get("turn") if isinstance(result, dict) else None
                            if isinstance(turn, dict) and isinstance(turn.get("id"), str) and turn["id"]:
                                key = (params["threadId"], turn["id"])
                                run.update(status="accepted", turn_id=turn["id"], scope="model selected before turn admission")
                                if key in self.completed:
                                    run.update(turn_status=self.completed[key])
                                else:
                                    self.turns[key] = run
                            else:
                                run.update(status="unconfirmed", reason="Codex response did not include a turn ID")
            self.state.observe_notification(message)
            if message.get("method") == "turn/completed" and isinstance(message.get("params"), dict):
                params = message["params"]
                turn = params.get("turn") or {}
                if isinstance(turn, dict) and isinstance(params.get("threadId"), str) and isinstance(turn.get("id"), str):
                    key = (params["threadId"], turn["id"])
                    self.completed[key] = turn.get("status")
                    if len(self.completed) > 200:
                        self.completed.pop(next(iter(self.completed)))
                    run = self.turns.pop(key, None)
                    if run:
                        run.update(turn_status=turn.get("status"))
            # Approval requests, tool output, and every other message pass through.
            await self.downstream.send(message)

    async def run(self):
        tasks = [asyncio.create_task(self.from_client()), asyncio.create_task(self.from_server())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for future in self.internal.values():
                if not future.done():
                    future.cancel()
            for _, _, run, _ in self.pending.values():
                if run and run.record["status"] == "submitted":
                    run.update(status="unconfirmed", reason="Connection closed before Codex acknowledged turn/start")
            for path in self.claim_paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass


async def serve_connection(reader, writer, args, state):
    process = None
    drain_stderr = None
    try:
        argv = [args.codex, "app-server", "proxy"] + (["--sock", args.sock] if args.sock else [])
        process = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

        async def discard_stderr():
            while await process.stderr.read(4096):
                pass

        drain_stderr = asyncio.create_task(discard_stderr())
        upstream = WebSocket(process.stdout, process.stdin, client=True)
        downstream = WebSocket(reader, writer, client=False)
        await upstream.handshake()
        await downstream.handshake()
        await Bridge(downstream, upstream, state).run()
    except (EOFError, asyncio.IncompleteReadError, ConnectionError):
        pass
    except asyncio.CancelledError:
        raise
    except Exception as error:
        run = router.HookRun()
        run.update(source="session-proxy", event="connection", status="failed", error=str(error)[:1200])
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, ConnectionError):
            pass
        if process is not None and process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 2)
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
        if drain_stderr is not None:
            drain_stderr.cancel()
            await asyncio.gather(drain_stderr, return_exceptions=True)


async def native_session(args):
    state = TurnRouter()
    connections = set()
    child = None

    def accept(reader, writer):
        task = asyncio.create_task(serve_connection(reader, writer, args, state))
        connections.add(task)
        task.add_done_callback(connections.discard)

    # A short path fits macOS's Unix-socket limit; the directory is owner-only.
    with tempfile.TemporaryDirectory(prefix="codex-router-", dir="/tmp") as directory:
        path = str(Path(directory) / "session.sock")
        try:
            server = await asyncio.start_unix_server(accept, path=path, limit=16384)
        except OSError as error:
            raise router.RouterError("Cannot create the local routing socket: " + str(error)) from error
        try:
            os.chmod(path, 0o600)
            argv = [args.codex, "--remote", "unix://" + path, "--cd", args.cwd]
            if args.thread:
                argv.extend(["resume", args.thread])
            if args.task:
                argv.extend(["--", args.task])
            print("Automatic model routing enabled for each new prompt. Use router.py status to inspect selections.", file=sys.stderr, flush=True)
            child = await asyncio.create_subprocess_exec(*argv)
            return await child.wait()
        finally:
            server.close()
            await server.wait_closed()
            if child is not None and child.returncode is None:
                try:
                    child.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(child.wait(), 2)
                except asyncio.TimeoutError:
                    try:
                        child.kill()
                    except ProcessLookupError:
                        pass
                    await child.wait()
            remaining = list(connections)
            for task in remaining:
                task.cancel()
            await asyncio.gather(*remaining, return_exceptions=True)


def run_auto(args):
    if args.phase or args.model or args.effort or args.failed_attempts:
        raise router.RouterError("auto selects each prompt separately; use plain prompts or [route:PROFILE] inside Codex")
    # Diagnose access before opening the TUI; never start or replace the daemon.
    with router.Rpc(args.codex, args.sock) as rpc:
        router.live_catalog(rpc)
    previous = signal.getsignal(signal.SIGINT)
    # Let the native foreground TUI handle Ctrl-C. A callable resets on child exec.
    signal.signal(signal.SIGINT, lambda *_: None)
    try:
        return asyncio.run(native_session(args))
    finally:
        signal.signal(signal.SIGINT, previous)

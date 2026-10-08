#!/usr/bin/env python3
"""Dependency-free task routing over Codex's experimental local app-server API."""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import struct
import subprocess
import sys
import tempfile
import time
import uuid


SKILL = Path(__file__).resolve().parents[1]
STATE_DIR = SKILL / ".router-state"
PROFILES = ("precheck", "easy", "coding", "review", "planning", "debugging", "deep-debug", "terra")
EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
LIVE_SWITCH_FEATURE = "step_model_switching"
ENABLE_LIVE_SWITCHING = "Run `codex features enable step_model_switching` in your terminal, then start a new Codex session to load the setting."


class RouterError(Exception):
    pass


def ensure_state_dir():
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = STATE_DIR.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise OSError("Router state must be an owned directory, not a symlink")
    if info.st_mode & 0o077:
        STATE_DIR.chmod(0o700)


def prompt_claim_path(thread_id, prompt):
    fingerprint = hashlib.sha256((thread_id + "\0" + prompt.strip()).encode()).hexdigest()
    return STATE_DIR / ("prompt-" + fingerprint + ".json")


def claim_prompt(thread_id, prompt):
    """Let the legacy hook recognize a prompt already handled before admission."""
    ensure_state_dir()
    # A bridge may only clean up its own claims, including for repeated prompts.
    prefix = prompt_claim_path(thread_id, prompt).stem
    path = STATE_DIR / (prefix + "-" + uuid.uuid4().hex + ".json")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=STATE_DIR, prefix=".prompt-", delete=False) as file:
            temporary = Path(file.name)
            json.dump({"created_at": time.time(), "pid": os.getpid()}, file)
        os.replace(temporary, path)
        temporary = None
        for old in STATE_DIR.glob("prompt-*.json"):
            try:
                if old.stat().st_mtime < time.time() - 60:
                    old.unlink(missing_ok=True)
            except OSError:
                pass
        return path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def consume_prompt_claim(thread_id, prompt):
    if not isinstance(thread_id, str) or not isinstance(prompt, str):
        return False
    try:
        info = STATE_DIR.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            return False
    except OSError:
        return False
    base = prompt_claim_path(thread_id, prompt)
    # Include the previous claim filename so an already-running proxy can finish.
    for path in [base, *STATE_DIR.glob(base.stem + "-*.json")]:
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                continue
            claim = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(claim, dict):
                continue
            if not 0 <= time.time() - claim["created_at"] <= 60 or type(claim["pid"]) is not int or claim["pid"] <= 0:
                continue
            os.kill(claim["pid"], 0)  # A stopped proxy must not disable routing.
            path.unlink()
            return True
        except (OSError, ValueError, KeyError, TypeError, OverflowError):
            continue
    return False


def failure_details(error):
    if "the destination changes the admitted node REPL review requirement" in error:
        return {
            "failure_kind": "incompatible_live_switch",
            "next_step": "Use `router.py auto` in a normal terminal for task selection before turn admission, or the `run` command for one initial task. This hook cannot change the admitted review requirement within the active turn; selection must happen before Codex starts that turn.",
        }
    return {}


class HookRun:
    """Keep a bounded local record of routing, without prompt or tool contents."""

    def __init__(self):
        self.path = STATE_DIR / ("run-" + str(uuid.uuid4()) + ".json")
        self.record = {"started_at": datetime.now(timezone.utc).isoformat(), "status": "started"}
        self.error = None
        self.update()

    def update(self, **fields):
        self.record.update(fields, updated_at=datetime.now(timezone.utc).isoformat())
        temporary = None
        try:
            ensure_state_dir()
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=STATE_DIR, prefix=".run-", delete=False) as file:
                temporary = Path(file.name)
                json.dump(self.record, file)
                file.write("\n")
            os.replace(temporary, self.path)
            self.error = None
        except OSError as error:
            self.error = "Could not save router diagnostics: " + str(error)
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        if self.error:
            return
        # Keep recent records; never remove source files or unrelated paths.
        try:
            rows = sorted(STATE_DIR.glob("run-*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
            for old in rows[200:]:
                old.unlink(missing_ok=True)
        except OSError:
            pass


def routing_status(thread_id=None):
    rows = []
    unreadable = 0
    if STATE_DIR.is_symlink():
        raise RouterError("Refusing to read a symlinked router state directory")
    for path in STATE_DIR.glob("run-*.json"):
        try:
            if path.is_symlink():
                raise ValueError("Run record is a symlink")
            record = json.loads(path.read_text())
            if not isinstance(record, dict):
                raise ValueError("Run record is not an object")
        except (OSError, ValueError):
            unreadable += 1
            continue
        if not thread_id or record.get("thread_id") == thread_id:
            if record.get("status") == "failed" and isinstance(record.get("error"), str):
                # Explain older failures without rewriting their recorded history.
                record = dict(record, **failure_details(record["error"]))
            rows.append(record)
    rows.sort(key=lambda r: r.get("started_at") if isinstance(r.get("started_at"), str) else "", reverse=True)
    return {"history_path": str(STATE_DIR), "thread_filter": thread_id, "runs": rows[:10], "unreadable_records": unreadable,
            "note": "No routing records found for this selection." if not rows else "accepted means turn/start acknowledged the selected model; applied means a live update was accepted. Neither alone proves inference usage. token_usage, when present, is the latest server-reported snapshot: total is cumulative for the thread, not additive across records or attributed to the selected model. Missing usage is unknown; these counters are not a bill."}


def validate_policy(value):
    if not isinstance(value, dict):
        raise RouterError("policy.json must contain an object")
    unknown = set(value) - {"enabled", "routing_mode", "profiles"}
    if unknown:
        raise RouterError("Unknown policy fields: " + ", ".join(sorted(unknown)))
    if not isinstance(value.get("enabled"), bool):
        raise RouterError("policy.enabled must be true or false")
    if value.get("routing_mode", "selective") not in ("selective", "task", "prompt"):
        raise RouterError('policy.routing_mode must be "selective", "task", or "prompt"')
    profiles = value.get("profiles")
    if not isinstance(profiles, dict):
        raise RouterError("policy.profiles must be an object")
    missing, unknown = set(PROFILES) - set(profiles), set(profiles) - set(PROFILES)
    if missing:
        raise RouterError("Missing route profiles: " + ", ".join(sorted(missing)))
    if unknown:
        raise RouterError("Unknown route profiles: " + ", ".join(sorted(unknown)))
    for name in PROFILES:
        profile = profiles[name]
        label = "policy.profiles." + name
        if not isinstance(profile, dict) or set(profile) != {"models", "effort"}:
            raise RouterError(label + " must contain exactly models and effort")
        models = profile["models"]
        if (not isinstance(models, list) or not models
                or not all(isinstance(model, str) and model and not any(c.isspace() for c in model) for model in models)):
            raise RouterError(label + ".models must be a nonempty array of model IDs without whitespace")
        if len(set(models)) != len(models):
            raise RouterError(label + ".models must not contain duplicate model IDs")
        if profile["effort"] not in EFFORTS:
            raise RouterError(label + ".effort must be one of: " + ", ".join(EFFORTS))
    return value


def policy():
    path = SKILL / "policy.json"
    try:
        return validate_policy(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        raise RouterError(f"Cannot read {path}: {error}") from error


def task_prompt(task):
    """Recognize an explicit task boundary without changing the forwarded input."""
    text = task.strip()
    boundary = re.match(r"^(?:\[route:new\](?:\s|$)|new task:\s*)", text, re.I)
    return (text[boundary.end():].strip(), True) if boundary else (text, False)


def classify(task, phase=None, failed_attempts=0):
    """Conservative heuristics. Ambiguous follow-ups preserve the existing model."""
    task, _ = task_prompt(task)
    directive = re.match(r"^\[route:([a-z-]+)\](?:\s|$)", task, re.I)
    if directive:
        chosen = directive.group(1).lower()
        if chosen == "off":
            return None, "Routing disabled for this turn"
        if chosen not in PROFILES:
            raise RouterError("Unknown route profile: " + chosen)
        return chosen, "Explicit route directive"
    if phase:
        if phase not in PROFILES:
            raise RouterError("Unknown route profile: " + phase)
        if failed_attempts >= 2 and phase in ("coding", "debugging"):
            return "deep-debug", "Two distinct unsuccessful fixes"
        return phase, "Task phase selected explicitly"
    if failed_attempts >= 2:
        return "deep-debug", "Two distinct unsuccessful fixes"
    # Model requests need semantic interpretation by the skill; do not override them.
    if re.search(r"\b(?:use|switch to|stay on|keep using)\s+(?:(?:gpt[- ]\d[^\s]*|the)\s+)?(?:sol|terra|luna|astra|gpt[- ]\d)|\b(?:none|minimal|low|medium|high|xhigh|extra.high|max|ultra)\s+(?:reasoning|effort)\b", task, re.I):
        return None, "Explicit model or effort request; retain selection for the skill to resolve"
    if not task or task.startswith("/"):
        return None, "No routable task"
    # Do not treat a pasted log, quotation, or source file as a fresh routing instruction.
    prose = re.split(r"```|\n\s*>|\n\s*(?:traceback|error:|stack trace)", task, maxsplit=1, flags=re.I)[0]
    prose = prose.lower()
    if re.search(r"\b(?:race condition|deadlock|data corruption|memory corruption|distributed consensus)\b", prose):
        return "deep-debug", "A difficult failure mode is named"
    if re.search(r"\b(?:debug|diagnose|root cause|investigate|flaky|crash|failing|broken|regression)\b", prose):
        return "debugging", "Root-cause investigation or failure analysis"
    if re.search(r"\b(?:security|authentication|authorization|oauth|payment|production|migration|cryptograph\w*)\b", prose):
        return "planning", "Consequences justify deeper reasoning"
    if re.match(r"(?:please\s+)?(?:implement|execute|carry out|build)\b.*\bplan\b", prose):
        return "coding", "Implementing an existing plan"
    if re.search(r"\b(?:plan|architecture|tradeoffs|trade-offs|design a system|design the system)\b", prose):
        return "planning", "Planning or design tradeoffs"
    if re.search(r"\b(?:implement|build|refactor|develop|create|add|update|change|write|fix)\b", prose):
        if re.search(r"\b(?:typo|spelling|formatting)\b", prose) and len(prose.split()) <= 35:
            return "easy", "A narrowly scoped mechanical change"
        return "coding", "Implementation work"
    if re.search(r"\b(?:review|audit|check (?:my|the|this) (?:code|changes|implementation))\b", prose):
        return "review", "Review or check interpretation"
    if re.search(r"\b(?:run|rerun)\b.*\b(?:tests?|lint|linter|typecheck|type check|checks)\b|\b(?:git status|preflight|pretest)\b", prose):
        return "precheck", "Run existing checks"
    if re.search(r"\b(?:summarize|summarise|extract|typo|spelling|formatting)\b", prose):
        return "easy", "Focused summary, extraction, or mechanical edit"
    if re.search(r"\blist\b.*\b(?:files|directories|entries|directory contents)\b|\brun\s+pwd\b", prose):
        return "easy", "Simple directory inspection"
    return None, "Uncertain task or continuation; keep the current choice"


def selective_phase(task, previous):
    """Recognize a few strong phase signals, without predicting price or quality.

    Levels order the shipped routing profiles, not the capability of arbitrary
    model IDs. A short check never lowers the selection of an ongoing task.
    """
    prose = re.split(r"```|\n\s*>|\n\s*(?:traceback|error:|stack trace)", task.strip(), maxsplit=1, flags=re.I)[0].lower()
    prose = re.sub(r"^(?:(?:now|next)[,:]?\s+)?(?:(?:can|could|would) you\s+|let(?:'s| us)\s+)?(?:please\s+)?", "", prose)
    repeated = re.match(
        r"(?:(?:two|2|three|3|multiple) (?:distinct )?(?:fixes|attempts) (?:have )?(?:failed|did not work)"
        r"|(?:it is |it's )?still failing after (?:two|2|three|3|multiple) (?:fixes|attempts))\b", prose)
    if repeated:
        profile, reason = "deep-debug", "User reports repeated unsuccessful fixes"
    else:
        # Descriptions, explanatory questions, negations, and quoted examples do not
        # count as an instruction to change phases. Explicit boundaries still
        # use the broader first-task classifier.
        if not re.match(r"(?:plan|design|implement|execute|carry out|build|refactor|develop|create|add|update|change|write|fix|debug|diagnose|investigate|trace|review|audit|summarize|summarise|extract)\b", prose):
            return None, "No clear work-phase instruction"
        profile, reason = classify(prose)
    if profile is None or profile == previous:
        return None, "Continuing the selected work phase"
    if profile == "easy" and re.match(r"(?:summarize|summarise|extract)\b", prose):
        quantities = re.findall(r"\b(\d{1,6})\s+(?:files|documents|reports|articles|release notes|records|pages)\b", prose)
        if any(int(count) >= 5 for count in quantities) or re.search(r"\b(?:as a batch|in bulk)\b", prose):
            return profile, "A substantial summary or extraction batch is requested"
    if previous == "planning" and profile == "coding" and re.match(r"(?:implement|execute|carry out|build)\b.*\bapproved plan\b", prose):
        return profile, "Moving from planning to implementation of the approved plan"
    levels = {"precheck": 0, "easy": 0, "coding": 1, "review": 1, "terra": 1,
              "planning": 2, "debugging": 2, "deep-debug": 3}
    if profile in levels and levels[profile] > levels.get(previous, -1) and levels[profile] > 0:
        return profile, reason
    return None, "Retaining selection through a brief or lower-demand follow-up"


def select_model(profile, catalog, settings, model=None, effort=None):
    validate_catalog(catalog)
    entry = settings["profiles"][profile or "coding"]
    candidates = [model] if model else entry["models"]
    by_id = {m["model"]: m for m in catalog if not m.get("hidden", False)}
    selected = next((m for m in candidates if m in by_id), None)
    if not selected:
        raise RouterError("No configured model is available: " + ", ".join(candidates))
    chosen_effort = effort or entry["effort"]
    allowed = {e["reasoningEffort"] for e in by_id[selected].get("supportedReasoningEfforts", [])}
    if chosen_effort not in allowed:
        raise RouterError(f"{selected} does not advertise effort {chosen_effort}")
    return {"profile": profile, "model": selected, "effort": chosen_effort}


def validate_catalog(catalog):
    if not isinstance(catalog, list):
        raise RouterError("Model catalog data must be an array")
    for entry in catalog:
        if not isinstance(entry, dict) or not isinstance(entry.get("model"), str) or not entry["model"]:
            raise RouterError("Model catalog contains an invalid model ID")
        efforts = entry.get("supportedReasoningEfforts", [])
        if not isinstance(efforts, list) or any(
            not isinstance(effort, dict) or not isinstance(effort.get("reasoningEffort"), str) for effort in efforts
        ):
            raise RouterError("Model catalog contains invalid reasoning efforts")
    return catalog


def rpc_result(message, method):
    if not isinstance(message, dict):
        raise RouterError("Codex returned a non-object JSON-RPC response")
    if "error" in message:
        error = message["error"]
        detail = error.get("message") if isinstance(error, dict) else None
        raise RouterError(f"{method}: " + (detail if isinstance(detail, str) else "Malformed RPC error"))
    if "result" not in message:
        raise RouterError(f"{method}: Codex response omitted result")
    return message["result"]


def catalog_page(result):
    if not isinstance(result, dict):
        raise RouterError("Model catalog response must be an object")
    models = validate_catalog(result.get("data"))
    cursor = result.get("nextCursor")
    if cursor is not None and not isinstance(cursor, str):
        raise RouterError("Model catalog pagination cursor must be a string")
    return models, cursor


class Rpc:
    """JSON-RPC over WebSocket frames passed through the raw Unix-socket proxy."""

    MAX_MESSAGE = 16 * 1024 * 1024

    def __init__(self, codex="codex", sock=None, timeout=8, command=None, protocol="websocket"):
        if protocol not in ("websocket", "jsonl"):
            raise ValueError("Unknown transport protocol")
        argv = command or [codex, "app-server", "proxy"] + (["--sock", sock] if sock else [])
        self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ, "out")
        self.selector.register(self.process.stderr, selectors.EVENT_READ, "err")
        self.buffer = b""
        self.errors = b""
        self.counter = 0
        self.protocol = protocol
        self.deadline = time.monotonic() + timeout

    def __enter__(self):
        try:
            if self.protocol == "websocket":
                self.upgrade()
            self.request("initialize", {"clientInfo": {"name": "codex_model_router", "version": "0.1.0"}, "capabilities": {"experimentalApi": True}})
            self.send({"method": "initialized", "params": {}})
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.selector.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()

    def write(self, data):
        try:
            self.process.stdin.write(data)
            self.process.stdin.flush()
        except BrokenPipeError as error:
            raise RouterError("Codex control connection closed") from error

    def read_more(self, stage):
        while time.monotonic() < self.deadline:
            if not self.selector.get_map():
                detail = self.errors.decode(errors="replace").strip()[-700:]
                raise RouterError(f"Cannot connect to Codex control socket during {stage}. " + detail)
            for key, _ in self.selector.select(max(0, self.deadline - time.monotonic())):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    self.selector.unregister(key.fileobj)
                elif key.data == "out":
                    self.buffer += chunk
                    return
                else:
                    self.errors = (self.errors + chunk)[-2000:]
        raise RouterError(f"Codex control request timed out during {stage}; no success confirmed")

    def read_exact(self, size, stage):
        while len(self.buffer) < size:
            self.read_more(stage)
        result, self.buffer = self.buffer[:size], self.buffer[size:]
        return result

    def upgrade(self):
        # app-server proxy copies bytes; it does not turn JSONL into WebSocket.
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        self.write(("GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
                    "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
                    f"Sec-WebSocket-Key: {key}\r\n\r\n").encode("ascii"))
        while b"\r\n\r\n" not in self.buffer:
            if len(self.buffer) > 16384:
                raise RouterError("WebSocket handshake headers exceeded the size limit")
            self.read_more("WebSocket handshake")
        header, self.buffer = self.buffer.split(b"\r\n\r\n", 1)
        if len(header) > 16384:
            raise RouterError("WebSocket handshake headers exceeded the size limit")
        lines = header.decode("iso-8859-1").split("\r\n")
        status = lines[0].split()
        if len(status) < 2 or status[:2] != ["HTTP/1.1", "101"]:
            raise RouterError("Codex control socket rejected the WebSocket handshake: " + lines[0][:120])
        headers = {}
        for line in lines[1:]:
            name, sep, value = line.partition(":")
            if not sep:
                raise RouterError("Malformed WebSocket handshake header")
            name = name.lower().strip()
            headers[name] = headers.get(name, "") + ("," if name in headers else "") + value.strip()
        expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()).decode("ascii")
        if (headers.get("sec-websocket-accept") != expected
                or headers.get("upgrade", "").lower() != "websocket"
                or "upgrade" not in {s.strip().lower() for s in headers.get("connection", "").split(",")}):
            raise RouterError("Invalid WebSocket upgrade response from Codex control socket")
        if headers.get("sec-websocket-extensions") or headers.get("sec-websocket-protocol"):
            raise RouterError("Server selected an unrequested WebSocket extension or subprotocol")

    def send_frame(self, opcode, payload):
        size = len(payload)
        if size > self.MAX_MESSAGE:
            raise RouterError("WebSocket message exceeded the size limit")
        if size < 126:
            header = bytes((0x80 | opcode, 0x80 | size))
        elif size <= 65535:
            header = bytes((0x80 | opcode, 0xFE)) + struct.pack("!H", size)
        else:
            header = bytes((0x80 | opcode, 0xFF)) + struct.pack("!Q", size)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.write(header + mask + masked)

    def receive_frame_message(self, stage):
        pieces = bytearray()
        fragmented = False
        while True:
            first, second = self.read_exact(2, stage)
            final, opcode = bool(first & 0x80), first & 0x0F
            if first & 0x70 or second & 0x80:
                raise RouterError("Unexpected WebSocket extension or masked server frame")
            size = second & 0x7F
            if opcode >= 8 and (not final or size > 125):
                raise RouterError("Invalid WebSocket control frame")
            if size == 126:
                size = struct.unpack("!H", self.read_exact(2, stage))[0]
            elif size == 127:
                size = struct.unpack("!Q", self.read_exact(8, stage))[0]
            if size + len(pieces) > self.MAX_MESSAGE:
                raise RouterError("WebSocket message exceeded the size limit")
            payload = self.read_exact(size, stage)
            if opcode == 8:
                if len(payload) == 1:
                    raise RouterError("Malformed WebSocket close frame")
                code = struct.unpack("!H", payload[:2])[0] if payload else "unspecified"
                raise RouterError(f"Codex closed the WebSocket during {stage} (code {code})")
            if opcode == 9:
                self.send_frame(10, payload)
                continue
            if opcode == 10:
                continue
            if opcode == 1 and not fragmented:
                fragmented = True
            elif opcode != 0 or not fragmented:
                raise RouterError("Unexpected WebSocket message type or continuation")
            pieces.extend(payload)
            if final:
                return bytes(pieces).decode("utf-8")

    def receive(self, stage):
        if self.protocol == "websocket":
            return json.loads(self.receive_frame_message(stage))
        while True:
            end = self.buffer.find(b"\n")
            if (end if end >= 0 else len(self.buffer)) > self.MAX_MESSAGE:
                raise RouterError("JSON-RPC message exceeded the size limit")
            if b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                if line.strip():
                    return json.loads(line)
            else:
                self.read_more(stage)

    def send(self, payload):
        data = json.dumps(payload).encode("utf-8")
        if self.protocol == "websocket":
            self.send_frame(1, data)
        else:
            self.write(data + b"\n")

    def request(self, method, params):
        self.counter += 1
        request_id = self.counter
        self.send({"id": request_id, "method": method, "params": params})
        while time.monotonic() < self.deadline:
            message = self.receive(method)
            if not isinstance(message, dict):
                raise RouterError("Codex returned a non-object JSON-RPC message")
            if message.get("id") == request_id and "method" not in message:
                return rpc_result(message, method)
            if "method" in message and "id" in message:
                self.send({"id": message["id"], "error": {"code": -32601, "message": "Router does not handle server requests"}})
        raise RouterError(f"Codex control request timed out during {method}; no success confirmed")


def live_catalog(rpc):
    models, seen = [], set()
    params = {"limit": 100, "includeHidden": False}
    for _ in range(20):
        page, cursor = catalog_page(rpc.request("model/list", params))
        models.extend(page)
        if not cursor:
            return models
        if cursor in seen:
            raise RouterError("Model catalog repeated a pagination cursor")
        seen.add(cursor)
        params["cursor"] = cursor
    raise RouterError("Model catalog exceeded pagination limit")


def inspect_router_hook(rpc, cwd):
    result = rpc.request("hooks/list", {"cwds": [str(Path(cwd).resolve())]})
    hooks = []
    issues = []
    for entry in result["data"]:
        issues.extend(entry.get("errors", []))
        issues.extend(entry.get("warnings", []))
        for handler in entry["hooks"]:
            if "codex-model-router/scripts/router.py" in handler.get("command", ""):
                hooks.append({key: handler.get(key) for key in ("eventName", "enabled", "trustStatus", "async", "sourcePath")})
    ready = any(h.get("eventName") == "userPromptSubmit" and h.get("enabled") is True and h.get("trustStatus") in ("trusted", "managed") for h in hooks)
    return {"cwd": str(Path(cwd).resolve()), "found": bool(hooks), "ready": ready, "hooks": hooks, "load_issues": issues}


def thread_is_loaded(rpc, thread_id):
    params, seen = {"limit": 100}, set()
    for _ in range(20):
        result = rpc.request("thread/loaded/list", params)
        if thread_id in result["data"]:
            return True
        cursor = result.get("nextCursor")
        if not cursor:
            return False
        if cursor in seen:
            raise RouterError("Loaded-thread list repeated a pagination cursor")
        seen.add(cursor)
        params["cursor"] = cursor
    raise RouterError("Loaded-thread list exceeded pagination limit")


def inspect_live_switching(rpc, thread_id=None):
    params, seen = {"limit": 100}, set()
    if thread_id:
        params["threadId"] = thread_id
    details = {"feature": LIVE_SWITCH_FEATURE, "thread_id": thread_id,
               "note": "Enabling this feature does not guarantee compatibility between models. Codex also checks the active turn's admitted runtime and review requirements."}
    for _ in range(20):
        result = rpc.request("experimentalFeature/list", params)
        for feature in result["data"]:
            if feature.get("name") == LIVE_SWITCH_FEATURE:
                enabled = feature["enabled"]
                if not isinstance(enabled, bool):
                    raise RouterError("Codex returned an invalid feature enablement state")
                details.update(listed=True, enabled=enabled, stage=feature.get("stage"))
                if not enabled:
                    details["next_step"] = ENABLE_LIVE_SWITCHING
                return details
        cursor = result.get("nextCursor")
        if not cursor:
            return dict(details, listed=False, enabled=None, note="The connected server did not list this feature; live switching could not be verified.")
        if cursor in seen:
            raise RouterError("Feature list repeated a pagination cursor")
        seen.add(cursor)
        params["cursor"] = cursor
    raise RouterError("Feature list exceeded pagination limit")


def cached_catalog(codex_home):
    path = Path(codex_home).expanduser() / "models_cache.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise RouterError("models_cache.json must contain a models array")
    result = []
    for model in data["models"]:
        if not isinstance(model, dict):
            raise RouterError("Model cache entries must be objects")
        levels = model.get("supported_reasoning_levels", [])
        if not isinstance(levels, list) or any(not isinstance(level, dict) for level in levels):
            raise RouterError("Model cache contains invalid reasoning levels")
        result.append({"model": model.get("slug"), "hidden": model.get("visibility") == "hide",
                       "supportedReasoningEfforts": [{"reasoningEffort": level.get("effort")} for level in levels]})
    return validate_catalog(result)


def apply_route(rpc, route, thread_id, turn_id=None, retry=False):
    if not thread_id:
        raise RouterError("No thread ID; run inside Codex or provide --thread")
    if not turn_id:
        response = rpc.request("thread/turns/list", {"threadId": thread_id, "limit": 1})
        active = [t for t in response["data"] if t.get("status") == "inProgress"]
        if len(active) != 1:
            raise RouterError("No active turn; no settings changed")
        turn_id = active[0]["id"]
    params = {"threadId": thread_id, "turnId": turn_id, "model": route["model"], "effort": route["effort"]}
    # An async prompt hook can arrive just before the live turn is registered.
    for attempt in range(5 if retry else 1):
        try:
            response = rpc.request("turn/settings/update", params)
        except RouterError as error:
            if "require the step_model_switching feature" in str(error):
                raise RouterError(str(error) + ". " + ENABLE_LIVE_SWITCHING) from error
            raise
        if response.get("status") == "applied":
            return dict(route, status="applied", scope="later inference calls in this turn", thread_id=thread_id, turn_id=turn_id)
        if response.get("status") != "targetUnavailable":
            raise RouterError("Unexpected update response; no success confirmed")
        if retry and attempt < 4:
            time.sleep(0.15)
    raise RouterError("Target turn is no longer active; no settings changed")


def hook(args, settings, run):
    event = json.load(sys.stdin)
    if not isinstance(event, dict):
        raise RouterError("Hook input must be an object")
    run.update(event=event.get("hook_event_name"), thread_id=event.get("session_id"), turn_id=event.get("turn_id"))
    if event.get("hook_event_name") != "UserPromptSubmit":
        run.update(status="skipped", reason="Unsupported hook event")
        return {}
    if consume_prompt_claim(event.get("session_id"), event.get("prompt")):
        run.update(status="skipped", reason="Handled by the automatic session router before turn/start")
        return {}
    if not settings["enabled"]:
        run.update(status="skipped", reason="Routing is disabled in policy.json")
        return {}
    mode = settings.get("routing_mode", "selective")
    if mode != "prompt":
        run.update(status="skipped", routing_mode=mode, reason="Task and selective routing require router.py auto; the legacy hook does not change task selections")
        return {}
    profile, reason = classify(event.get("prompt", ""))
    if not profile:
        run.update(status="skipped", reason=reason)
        return {}
    run.update(profile=profile, reason=reason)
    thread_id, turn_id = event.get("session_id"), event.get("turn_id")
    if not thread_id or not turn_id:
        raise RouterError("Hook omitted the session or turn ID; no settings changed")
    with Rpc(args.codex, args.sock) as rpc:
        route = select_model(profile, live_catalog(rpc), settings)
        run.update(model=route["model"], effort=route["effort"])
        result = apply_route(rpc, route, thread_id, turn_id, retry=True)
    run.update(status="applied", scope=result["scope"])
    context = (f"Model router published {result['model']} / {result['effort']} for later inference calls in this turn ({reason}). "
               f"For a user-requested live change, consult the codex-model-router skill at {SKILL / 'SKILL.md'}. "
               "Do not switch again for a single test command inside a harder task.")
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("auto", "preview", "apply", "doctor", "status", "hook", "run"))
    parser.add_argument("task", nargs="?", default="")
    parser.add_argument("--phase", choices=PROFILES)
    parser.add_argument("--failed-attempts", type=int, default=0)
    parser.add_argument("--model")
    parser.add_argument("--effort")
    parser.add_argument("--thread", help="Thread to inspect or resume with auto; apply also defaults to CODEX_THREAD_ID")
    parser.add_argument("--turn")
    parser.add_argument("--cwd", default=str(Path.cwd()), help="Project for auto/run, or hook discovery with doctor")
    parser.add_argument("--sock", help="Explicit socket for the daemon hosting the target thread")
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")), help="Model cache directory for preview/run; set CODEX_HOME to configure Codex itself")
    args = parser.parse_intermixed_args(argv)
    run = HookRun() if args.command == "hook" else None
    try:
        if args.command == "status":
            print(json.dumps(routing_status(args.thread), indent=2))
            return 0
        settings = policy()
        if args.failed_attempts < 0:
            raise RouterError("Failed attempts cannot be negative")
        if args.command == "auto":
            from session_proxy import run_auto
            return run_auto(args)
        if args.command == "hook":
            output = hook(args, settings, run)
            if run.error:
                output["systemMessage"] = run.error
        elif args.command == "doctor":
            with Rpc(args.codex, args.sock) as rpc:
                models = live_catalog(rpc)
                output = {"control_socket": "reachable", "transport": "websocket-over-unix-proxy", "models": [m["model"] for m in models], "live_update": "Not tested: doctor never changes settings"}
                try:
                    output["router_hook"] = inspect_router_hook(rpc, args.cwd)
                except (RouterError, KeyError, TypeError) as error:
                    output["router_hook"] = {"error": str(error)}
                if args.thread:
                    try:
                        loaded = thread_is_loaded(rpc, args.thread)
                        output["target_thread"] = {"id": args.thread, "loaded_on_this_server": loaded}
                    except (RouterError, KeyError, TypeError) as error:
                        output["target_thread"] = {"id": args.thread, "error": str(error)}
                try:
                    output["live_switching"] = inspect_live_switching(rpc, args.thread)
                except (RouterError, KeyError, TypeError) as error:
                    output["live_switching"] = {"feature": LIVE_SWITCH_FEATURE, "enabled": None, "error": str(error)}
            output["recent_routing"] = routing_status(args.thread)
        else:
            profile, reason = classify(args.task, args.phase, args.failed_attempts)
            off = bool(re.match(r"^\[route:off\](?:\s|$)", task_prompt(args.task)[0], re.I))
            if off or not settings["enabled"] or (not profile and not args.model):
                output = {"status": "unchanged", "reason": "Routing disabled" if off or not settings["enabled"] else reason}
                if args.command == "run":
                    if not args.task:
                        raise RouterError("run requires a task")
                    print(json.dumps(output), file=sys.stderr, flush=True)
                    return subprocess.call([args.codex, "--cd", args.cwd, "--", args.task])
            elif args.command in ("preview", "run"):
                route = select_model(profile, cached_catalog(args.codex_home), settings, args.model, args.effort)
                output = dict(route, status="preview", reason=reason, catalog="local cache; availability can change")
                if args.command == "run":
                    if not args.task:
                        raise RouterError("run requires a task")
                    output.update(status="launching", scope="initial model for a new Codex session")
                    print(json.dumps(output), file=sys.stderr, flush=True)
                    # argv preserves literal shell characters in the task.
                    return subprocess.call([args.codex, "--cd", args.cwd, "--model", route["model"], "-c", "model_reasoning_effort=" + json.dumps(route["effort"]), "--", args.task])
            else:
                with Rpc(args.codex, args.sock) as rpc:
                    route = select_model(profile, live_catalog(rpc), settings, args.model, args.effort)
                    output = apply_route(rpc, route, args.thread or os.environ.get("CODEX_THREAD_ID"), args.turn)
        print(json.dumps(output, indent=2))
        return 0
    except (RouterError, OSError, ValueError, KeyError, TypeError) as error:
        details = failure_details(str(error))
        message = str(error) + (". " + details["next_step"] if details else "")
        if args.command == "hook":
            run.update(status="failed", error=str(error)[:1200], **details)
            print(json.dumps({"systemMessage": "Model router did not confirm a switch: " + message}))
            return 0  # Routing failure must not block the user's work.
        print("Model router: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    # The lazily imported proxy must share this module's RouterError and state.
    # Otherwise `import router` creates a second copy when this is a script.
    sys.modules["router"] = sys.modules[__name__]
    sys.exit(main())

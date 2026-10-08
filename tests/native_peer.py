"""Independent fake Codex binary: CLI Unix client and app-server byte proxy.

Exercises the complete auto launcher without inference or the real daemon.
"""

import base64
import hashlib
import json
import os
import socket
import sys


GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MODELS = ["gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna", "gpt-5.6-terra"]
CATALOG = [{"model": m, "defaultReasoningEffort": "medium", "supportedReasoningEfforts": [{"reasoningEffort": e} for e in ("low", "medium", "high", "xhigh")]} for m in MODELS]


def take(stream, length):
    value = bytearray()
    while len(value) < length:
        chunk = stream.read(length - len(value))
        if not chunk:
            raise EOFError()
        value.extend(chunk)
    return bytes(value)


def headers(stream):
    raw = bytearray()
    while not raw.endswith(b"\r\n\r\n"):
        raw.extend(take(stream, 1))
    lines = bytes(raw).split(b"\r\n")
    return lines[0], {k.lower(): v.strip() for line in lines[1:] if b":" in line for k, v in [line.split(b":", 1)]}


def send(sink, message, masked):
    data = json.dumps(message).encode()
    size = len(data)
    prefix = bytes((129, (128 if masked else 0) | (size if size < 126 else 126)))
    if size >= 126:
        prefix += size.to_bytes(2, "big")
    if masked:
        mask = os.urandom(4)
        prefix += mask
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    sink.write(prefix + data)
    sink.flush()


def receive(source, masked):
    first, second = take(source, 2)
    assert first == 129
    assert bool(second & 128) == masked
    size = second & 127
    if size == 126:
        size = int.from_bytes(take(source, 2), "big")
    elif size == 127:
        size = int.from_bytes(take(source, 8), "big")
    mask = take(source, 4) if masked else None
    data = take(source, size)
    if mask:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return json.loads(data)


def server():
    source, sink = sys.stdin.buffer, sys.stdout.buffer
    line, header = headers(source)
    assert line == b"GET / HTTP/1.1"
    accept = base64.b64encode(hashlib.sha1(header[b"sec-websocket-key"] + GUID).digest())
    sink.write(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n")
    sink.flush()
    initialized = False
    count = 0
    while True:
        request = receive(source, masked=True)
        method = request.get("method")
        if method == "initialized":
            initialized = True
            continue
        if method == "initialize":
            result = {"userAgent": "independent-fixture"}
        else:
            assert initialized
            if method == "model/list":
                result = {"data": CATALOG}
            elif method == "thread/start":
                result = {"thread": {"id": "one", "status": {"type": "idle"}}, "model": "gpt-6-astra", "reasoningEffort": "high"}
            elif method == "turn/start":
                params = request["params"]
                assert params["threadId"] == "one"
                assert params["approvalPolicy"] == "on-request"
                assert params["sandboxPolicy"] == {"type": "readOnly"}
                assert params["collaborationMode"]["settings"]["developer_instructions"] == "native client instructions"
                assert params["model"] == params["collaborationMode"]["settings"]["model"]
                assert params["effort"] == params["collaborationMode"]["settings"]["reasoning_effort"]
                count += 1
                turn = {"id": f"turn-{count}", "status": "inProgress"}
                send(sink, {"method": "turn/started", "params": {"threadId": "one", "turn": turn}}, masked=False)
                send(sink, {"id": "approval", "method": "item/commandExecution/requestApproval", "params": {"threadId": "one", "command": "fixture", "availableDecisions": ["decline"]}}, masked=False)
                assert receive(source, masked=True) == {"id": "approval", "result": {"decision": "decline"}}
                result = {"turn": turn, "fixture_model": params["model"], "fixture_effort": params["effort"]}
                send(sink, {"id": request["id"], "result": result}, masked=False)
                send(sink, {"method": "turn/completed", "params": {"threadId": "one", "turn": dict(turn, status="completed")}}, masked=False)
                continue
            else:
                raise AssertionError("Unexpected method " + str(method))
        send(sink, {"id": request["id"], "result": result}, masked=False)


def conversation(source, sink):
    key = base64.b64encode(os.urandom(16))
    sink.write(b"GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: " + key + b"\r\nSec-WebSocket-Version: 13\r\n\r\n")
    sink.flush()
    line, header = headers(source)
    assert line.startswith(b"HTTP/1.1 101")
    assert header[b"sec-websocket-accept"] == base64.b64encode(hashlib.sha1(key + GUID).digest())
    send(sink, {"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "fixture-native-tui"}}}, masked=True)
    assert receive(source, masked=False)["id"] == 1
    send(sink, {"method": "initialized", "params": {}}, masked=True)
    send(sink, {"id": 2, "method": "thread/start", "params": {}}, masked=True)
    assert receive(source, masked=False)["result"]["thread"]["id"] == "one"
    selections = []
    for index, task in enumerate([
        "Plan the cache architecture",
        "Run pwd and list the first five entries",
        "Implement the approved plan",
        "Use Terra to implement pagination",
        "Run the existing tests",
        "[route:deep-debug] Investigate a deadlock",
        "continue",
        "New task: List files in the current directory",
        "Review the changes",
        "[route:new] Implement pagination",
        "Investigate the intermittent deadlock",
        "Run tests",
        "Summarize these 30 release notes",
        "Run tests",
    ]):
        params = {"threadId": "one", "input": [{"type": "text", "text": task}], "model": "gpt-6-astra", "effort": "high", "approvalPolicy": "on-request", "sandboxPolicy": {"type": "readOnly"}, "collaborationMode": {"mode": "default", "settings": {"model": "gpt-6-astra", "reasoning_effort": "high", "developer_instructions": "native client instructions"}}}
        send(sink, {"id": index + 10, "method": "turn/start", "params": params}, masked=True)
        while True:
            message = receive(source, masked=False)
            if message.get("method") == "item/commandExecution/requestApproval":
                send(sink, {"id": message["id"], "result": {"decision": "decline"}}, masked=True)
            elif message.get("id") == index + 10:
                assert "error" not in message, message
                selections.append([message["result"]["fixture_model"], message["result"]["fixture_effort"]])
            elif message.get("method") == "turn/completed":
                break
    return {"thread": "one", "selections": selections}


def client():
    if "--fixture-stdio-client" in sys.argv:
        print(json.dumps(conversation(sys.stdin.buffer, sys.stdout.buffer)), file=sys.stderr)
        return
    path = sys.argv[sys.argv.index("--remote") + 1].removeprefix("unix://")
    assert sys.argv[sys.argv.index("--cd") + 1]
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(8)
        sock.connect(path)
        stream = sock.makefile("rwb", buffering=0)
        print(json.dumps(conversation(stream, stream)))
        stream.close()


if __name__ == "__main__":
    try:
        if sys.argv[1:3] == ["app-server", "proxy"]:
            server()
        else:
            client()
    except EOFError:
        pass

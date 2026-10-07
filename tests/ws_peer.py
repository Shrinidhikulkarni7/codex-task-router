"""Independent raw-byte WebSocket test peer; does not call Codex or use sockets."""

import base64
import hashlib
import json
import sys


source, sink = sys.stdin.buffer, sys.stdout.buffer
mode = sys.argv[1]


def take(count):
    value = source.read(count)
    if len(value) != count:
        raise SystemExit(0)
    return value


def read_client_frame():
    flags, length = take(2)
    assert flags & 0x80, "Client must send complete frames"
    assert length & 0x80, "Every client frame must be masked"
    length &= 0x7F
    if length == 126:
        length = int.from_bytes(take(2), "big")
    elif length == 127:
        length = int.from_bytes(take(8), "big")
    mask = take(4)
    data = bytearray(take(length))
    for offset in range(len(data)):
        data[offset] ^= mask[offset % 4]
    return flags & 0x0F, bytes(data)


def frame(data, opcode=1, final=True):
    size = len(data)
    prefix = bytes([(0x80 if final else 0) | opcode])
    if size < 126:
        prefix += bytes([size])
    elif size <= 65535:
        prefix += b"\x7e" + size.to_bytes(2, "big")
    else:
        prefix += b"\x7f" + size.to_bytes(8, "big")
    return prefix + data


header = bytearray()
while not header.endswith(b"\r\n\r\n"):
    header.extend(take(1))
assert header.startswith(b"GET / HTTP/1.1\r\n")
headers = {}
for line in bytes(header).split(b"\r\n")[1:]:
    if b":" in line:
        name, value = line.split(b":", 1)
        headers[name.lower()] = value.strip()
assert headers[b"upgrade"].lower() == b"websocket"
assert headers[b"sec-websocket-version"] == b"13"
key = headers[b"sec-websocket-key"]
assert len(base64.b64decode(key)) == 16

if mode == "silent_upgrade":
    source.read()
    raise SystemExit(0)
if mode == "http_error":
    sink.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
    sink.flush()
    raise SystemExit(0)
accepted = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
if mode == "bad_accept":
    accepted = b"invalid"
reply = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: keep-alive, Upgrade\r\nSec-WebSocket-Accept: " + accepted + b"\r\n\r\n"
# Split the upgrade response and coalesce its end with the first notification.
sink.write(reply[:11])
sink.flush()
sink.write(reply[11:] + frame(b'{"method":"notice","params":{}}'))
sink.flush()

initialized = False
while True:
    opcode, raw = read_client_frame()
    assert opcode == 1
    request = json.loads(raw)
    method = request["method"]
    if method == "initialized":
        initialized = True
        continue
    if method == "initialize":
        assert not initialized
        assert request["params"]["capabilities"]["experimentalApi"]
        result = {"userAgent": "fixture"}
    else:
        assert initialized, "initialize response and initialized notification must precede RPC"
        if mode == "close":
            sink.write(frame((1000).to_bytes(2, "big"), opcode=8))
            sink.flush()
            raise SystemExit(0)
        if mode == "masked":
            sink.write(b"\x81\x80\x00\x00\x00\x00")
            sink.flush()
            raise SystemExit(0)
        if mode == "oversized":
            sink.write(b"\x81\x7f" + (2**40).to_bytes(8, "big"))
            sink.flush()
            raise SystemExit(0)
        if mode == "silent_model":
            source.read()
            raise SystemExit(0)
        if method == "echo":
            result = request["params"]
        elif method == "model/list":
            result = {"data": [{"model": "gpt-6-luna", "supportedReasoningEfforts": [{"reasoningEffort": "medium"}]}], "nextCursor": None}
        elif method == "turn/settings/update":
            assert request["params"]["threadId"] == "fixture-thread"
            result = {"status": "applied"}
        else:
            raise AssertionError("Unexpected method " + method)
    body = json.dumps({"id": request["id"], "result": result}, ensure_ascii=False).encode("utf-8")
    if mode == "fragmented":
        midpoint = len(body) // 2
        sink.write(frame(body[:midpoint], final=False) + frame(b"ping-test", opcode=9))
        sink.flush()
        assert read_client_frame() == (10, b"ping-test")
        sink.write(frame(body[midpoint:], opcode=0))
    else:
        sink.write(frame(body))
    sink.flush()

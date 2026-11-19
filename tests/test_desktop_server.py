import json
import os
import threading
import urllib.error
import urllib.request
from contextlib import closing
from http.server import ThreadingHTTPServer
from socket import socket

from omnix.desktop_server import DesktopServer, Handler


def test_desktop_server_requires_loopback_token(monkeypatch):
    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    with closing(socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/health", timeout=2)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("unauthenticated desktop request was accepted")
        request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/health", headers={"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost"})
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        assert payload["status"] == "ok"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_desktop_chat_uses_existing_runtime_and_returns_session(monkeypatch):
    class FakeRuntime:
        def __init__(self, *_args, **_kwargs):
            pass

        def run(self, prompt, session_id=None):
            assert prompt == "hello"
            return "real-runtime-result", session_id or "session-1"

    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setattr("omnix.desktop_server.AgentRuntime", FakeRuntime)
    with closing(socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.state = type("State", (), {"lock": threading.Lock(), "cancel_event": None})()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat", data=json.dumps({"prompt": "hello"}).encode(), headers={"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost", "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        assert payload["answer"] == "real-runtime-result"
        assert payload["session_id"] == "session-1"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_desktop_approval_is_explicit_scoped_and_time_limited():
    server = DesktopServer(("127.0.0.1", 0), Handler)
    result = []
    worker = threading.Thread(target=lambda: result.append(server.approvals.request("write workspace/file.txt", timeout=1)), daemon=True)
    worker.start()
    for _ in range(20):
        pending = server.approvals.list()
        if pending:
            break
        worker.join(0.01)
    assert pending and pending[0]["action"] == "write workspace/file.txt"
    assert server.approvals.decide(pending[0]["id"], True)
    worker.join(timeout=1)
    assert result == [True]
    server.server_close()


def test_desktop_content_preference_is_backend_owned(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path))
    server = DesktopServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        headers = {"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost", "Content-Type": "application/json"}
        request = urllib.request.Request(base + "/v1/settings", data=json.dumps({"content_preference": "standard"}).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            assert json.loads(response.read())["content_preference"] == "standard"
        request = urllib.request.Request(base + "/v1/settings", headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            assert json.loads(response.read())["content_preference"] == "standard"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

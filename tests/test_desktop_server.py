import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socket import socket
from types import SimpleNamespace

from omnix.desktop_server import DesktopServer, Handler
from omnix.config import Settings, save_settings
from omnix.store import Store


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

        missing_origin = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/health",
            headers={"Authorization": "Bearer unit-test-token"},
        )
        try:
            urllib.request.urlopen(missing_origin, timeout=2)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("authenticated request without an allowed origin was accepted")
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_desktop_request_closes_its_owned_store(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path))
    opened = []

    class TrackedStore(Store):
        def __init__(self):
            super().__init__()
            opened.append(self)

    monkeypatch.setattr("omnix.desktop_server.Store", TrackedStore)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/sessions/example", headers={"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost"})
        with urllib.request.urlopen(request, timeout=2) as response:
            assert json.loads(response.read())["messages"] == []
        assert len(opened) == 1
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                opened[0].db.execute("SELECT 1")
            except sqlite3.ProgrammingError:
                break
            time.sleep(.01)
        else:
            raise AssertionError("request-owned database connection remained open")
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()


def test_desktop_chat_uses_existing_runtime_and_returns_session(monkeypatch, tmp_path):
    class FakeRuntime:
        def __init__(self, *_args, **_kwargs):
            pass

        def run(self, prompt, session_id=None):
            assert prompt == "hello"
            return "real-runtime-result", session_id or "session-1"

    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path))
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
        server.server_close()


def test_desktop_stream_is_incremental_scoped_and_cleared(monkeypatch, tmp_path):
    from omnix.desktop_server import DesktopState
    sent, release = threading.Event(), threading.Event()

    class FakeRuntime:
        def __init__(self, *_args, **_kwargs):
            pass

        def run(self, prompt, session_id=None, on_delta=None, on_event=None):
            on_event("Thinking")
            on_delta("first ")
            sent.set()
            assert release.wait(3)
            on_delta("second")
            return "first second", "session-1"

    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("omnix.desktop_server.AgentRuntime", FakeRuntime)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.state = DesktopState()
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost", "Content-Type": "application/json"}
    result = []
    def chat():
        request = urllib.request.Request(base + "/v1/chat", data=json.dumps({"prompt": "hello", "stream_id": "abc-123"}).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            result.append(json.loads(response.read()))
    worker = threading.Thread(target=chat)
    worker.start()
    try:
        assert sent.wait(3)
        def poll(stream_id):
            with urllib.request.urlopen(urllib.request.Request(base + "/v1/chat/stream?id=" + stream_id, headers=headers), timeout=2) as response:
                return json.loads(response.read())["text"]
        assert poll("abc-123") == "first "
        assert poll("other") == ""
        request = urllib.request.Request(base + "/v1/chat/stream?id=abc-123", headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            assert json.loads(response.read())["status"] == "Thinking"
        release.set()
        worker.join(3)
        assert result[0]["answer"] == "first second"
        assert poll("abc-123") == ""
    finally:
        release.set()
        worker.join(3)
        server.shutdown()
        server_thread.join(3)
        server.server_close()


def test_desktop_streams_provider_response_and_persists_final(monkeypatch, tmp_path):
    from omnix.desktop_server import DesktopState
    first_sent, release = threading.Event(), threading.Event()

    class ProviderHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["stream"] is True
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b'data: {"choices":[{"delta":{"content":"Hello "}}]}\n\n')
            self.wfile.flush()
            first_sent.set()
            assert release.wait(5)
            self.wfile.write(b'data: {"choices":[{"delta":{"content":"there."}}]}\n\ndata: [DONE]\n\n')
            self.wfile.flush()
        def log_message(self, *_args):
            pass

    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("omnix.providers.get_secret", lambda _: None)
    provider = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHandler)
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    save_settings(Settings(provider="omniroute", model="local-free", mode="FREE", free_models=["local-free"], base_url=f"http://127.0.0.1:{provider.server_port}/v1"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.state = DesktopState()
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost", "Content-Type": "application/json"}
    result = []
    def chat():
        request = urllib.request.Request(base + "/v1/chat", data=json.dumps({"prompt": "Greet me", "stream_id": "local-test"}).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=8) as response:
            result.append(json.loads(response.read()))
    worker = threading.Thread(target=chat)
    worker.start()
    try:
        assert first_sent.wait(5)
        deadline = time.monotonic() + 3
        streamed = ""
        while not streamed and time.monotonic() < deadline:
            request = urllib.request.Request(base + "/v1/chat/stream?id=local-test", headers=headers)
            with urllib.request.urlopen(request, timeout=2) as response:
                streamed = json.loads(response.read())["text"]
            if not streamed:
                time.sleep(0.02)
        assert streamed == "Hello "
        release.set()
        worker.join(5)
        assert result[0]["answer"] == "Hello there."
        request = urllib.request.Request(base + "/v1/sessions/" + result[0]["session_id"], headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            messages = json.loads(response.read())["messages"]
        assert messages[-1]["content"] == "Hello there."
    finally:
        release.set()
        worker.join(5)
        server.shutdown()
        provider.shutdown()
        server_thread.join(3)
        provider_thread.join(3)
        server.server_close()
        provider.server_close()


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


def test_desktop_skills_endpoint_exposes_reviewed_state_and_toggle(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path))
    server = DesktopServer(("127.0.0.1", 0), Handler)
    record = SimpleNamespace(name="review", path=str(tmp_path / "SKILL.md"), source="omnix-custom",
                             description="Review code", permissions=("filesystem.read",), credentials=(),
                             dependencies=(), enabled=False, installed=True)
    class FakeSkills:
        def browse(self):
            return [record]
        def set_enabled(self, name, enabled):
            assert name == "review"
            record.enabled = enabled
            return record
    server.skills = FakeSkills()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        headers = {"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost"}
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/skills", headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        assert payload["skills"][0]["enabled"] is False
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/skills/review", data=json.dumps({"action": "enable"}).encode(), headers={**headers, "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        assert payload["skill"]["enabled"] is True
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_desktop_integrations_are_catalogued_disabled_and_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path / "data"))
    server = DesktopServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        headers = {"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost", "Content-Type": "application/json"}
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/integrations", headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            integrations = json.loads(response.read())["integrations"]
        openwhispr = next(item for item in integrations if item["name"] == "openwhispr")
        assert openwhispr["enabled"] is False
        assert openwhispr["health"]["status"] == "disabled"
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/integrations/openwhispr", data=json.dumps({"action": "enable"}).encode(), headers=headers, method="POST")
        try:
            urllib.request.urlopen(request, timeout=2)
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
        else:
            raise AssertionError("uninstalled integration was enabled")
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/integrations/openwhispr", data=json.dumps({"action": "install"}).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            assert json.loads(response.read())["integration"]["installed"] is True
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_legacy_hermes_setting_migrates_to_native_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path))
    save_settings(Settings(runtime="hermes", provider="omniroute", model="auto/best-free",
                            base_url="http://127.0.0.1:20128/v1", mode="FREE",
                            allow_paid=False, max_cost_usd=0.0))
    monkeypatch.setattr("omnix.desktop_server.AgentRuntime.run", lambda self, prompt, session_id=None: ("native desktop result", session_id or "native-session"))
    server = DesktopServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        headers = {"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost", "Content-Type": "application/json"}
        request = urllib.request.Request(base + "/v1/chat", data=json.dumps({"prompt": "hello"}).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        assert payload["answer"] == "native desktop result"
        assert payload["runtime"] == "omnix"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_desktop_session_messages_are_available_after_restart(monkeypatch, tmp_path):
    from omnix.store import Store

    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path))
    session_id = Store().new_session("persisted")
    Store().add_message(session_id, "user", "remember this")
    server = DesktopServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/sessions/{session_id}", headers={"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost"})
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        assert payload["messages"] == [{"role": "user", "content": "remember this"}]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_desktop_council_persists_candidates_and_enforces_free_mode(monkeypatch, tmp_path):
    from omnix.council import Candidate, CouncilResult
    from omnix.store import Store

    class FakeCouncil:
        def __init__(self, *_args, **_kwargs):
            pass

        def run(self, messages, config):
            assert config.free_only is True and config.max_cost_usd == 0.0
            return CouncilResult("council answer", [Candidate("omniroute", "free-a", "answer", 80.0, 2, 3, 4.0)], config.mode, 2, 3, 5.0, [])

    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("omnix.desktop_server.CouncilService", FakeCouncil)
    server = DesktopServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        headers = {"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost", "Content-Type": "application/json"}
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/council", data=json.dumps({"prompt": "compare", "mode": "council", "models": ["free-a", "free-b", "free-c"]}).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        assert payload["answer"] == "council answer"
        assert payload["candidates"][0]["model"] == "free-a"
        row = Store().job(payload["task_id"])
        assert row is None  # Council uses the existing task ledger, not durable worker jobs.
        task = Store().db.execute("SELECT state FROM tasks WHERE id=?", (payload["task_id"],)).fetchone()
        assert task["state"] == "completed"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_desktop_models_discovery_and_free_selection(monkeypatch, tmp_path):
    from omnix.discovery import Discovery

    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("omnix.desktop_server.discover_omniroute", lambda settings: Discovery(
        "http://127.0.0.1:20128/v1", True, False,
        [{"id": "free-a", "owned_by": "test", "free": True, "context_length": 8000, "capabilities": {"tool_calling": True}}],
        [{"id": "free-a", "owned_by": "test", "free": True, "context_length": 8000, "capabilities": {"tool_calling": True}}], 2.0))
    server = DesktopServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        headers = {"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost", "Content-Type": "application/json"}
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/models", headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            assert json.loads(response.read())["models"][0]["free"] is True
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/settings", data=json.dumps({"model": "paid-model"}).encode(), headers=headers, method="POST")
        try:
            urllib.request.urlopen(request, timeout=2)
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
        else:
            raise AssertionError("FREE mode accepted an undiscovered paid model")
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_desktop_brain_vault_endpoint_is_contained_and_persistent(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OMNIX_VAULT_DIR", str(tmp_path / "vault"))
    server = DesktopServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        headers = {"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost", "Content-Type": "application/json"}
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/brain/notes", data=json.dumps({"path": "alpha.md", "content": "# Alpha\nlocal evidence"}).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            assert json.loads(response.read())["path"] == "alpha.md"
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/brain/note?path=alpha.md", headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            assert json.loads(response.read())["content"] == "# Alpha\nlocal evidence"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_desktop_tasks_use_existing_task_service_and_cancel(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path / "data"))
    server = DesktopServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        headers = {"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost", "Content-Type": "application/json"}
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/tasks", data=json.dumps({"action": "enqueue", "prompt": "queued task"}).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            task_id = json.loads(response.read())["task_id"]
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/tasks/{task_id}", data=json.dumps({"action": "cancel"}).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            assert json.loads(response.read())["cancelled"] is True
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/tasks", headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            tasks = json.loads(response.read())["tasks"]
        assert any(item["id"] == task_id and item["state"] == "cancelled" for item in tasks)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_desktop_workflow_definition_persists_in_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path / "data"))
    server = DesktopServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        headers = {"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost", "Content-Type": "application/json"}
        definition = {"nodes": [{"id": "step-1", "action": "approval", "depends_on": []}]}
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/workflows", data=json.dumps({"name": "Approval flow", "definition": definition}).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            workflow_id = json.loads(response.read())["workflow_id"]
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/workflows", headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            workflows = json.loads(response.read())["workflows"]
        assert any(item["id"] == workflow_id and item["definition"] == definition for item in workflows)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

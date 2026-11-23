import json
import os
import threading
import urllib.error
import urllib.request
from contextlib import closing
from http.server import ThreadingHTTPServer
from socket import socket
from types import SimpleNamespace

from omnix.desktop_server import DesktopServer, Handler
from omnix.config import Settings, save_settings


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


def test_desktop_runtime_selection_uses_hermes_boundary(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path))
    save_settings(Settings(runtime="hermes", provider="omniroute", model="auto/best-free",
                            base_url="http://127.0.0.1:20128/v1", mode="FREE",
                            allow_paid=False, max_cost_usd=0.0))
    monkeypatch.setattr("omnix.desktop_server.run_hermes_primary_probe", lambda *args, **kwargs: {
        "answer": "hermes desktop result", "model": "auto/best-free",
        "omnix_session_id": "hermes-session", "usage": {
            "provider": "omniroute", "input_tokens": 2, "output_tokens": 3,
            "estimated_cost_usd": 0.0,
        },
    })
    server = DesktopServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        headers = {"Authorization": "Bearer unit-test-token", "Origin": "tauri://localhost", "Content-Type": "application/json"}
        request = urllib.request.Request(base + "/v1/chat", data=json.dumps({"prompt": "hello"}).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        assert payload["answer"] == "hermes desktop result"
        assert payload["runtime"] == "hermes"
        assert payload["usage"][0]["estimated_cost"] == 0.0
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

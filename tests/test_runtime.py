from pathlib import Path
import threading

import pytest

from omnix.config import Settings
from omnix.runtime import AgentRuntime
from omnix.store import Store
from omnix.skills_manager import SkillsManager


def test_legacy_backend_import_remains_compatible():
    from omnix.agent_backend import AgentExecutionBackend
    from omnix.hermes_backend import HermesExecutionBackend
    assert HermesExecutionBackend is AgentExecutionBackend


def test_runtime_only_loads_enabled_skills(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path / "data"))
    skill = tmp_path / "skills" / "specialist-review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("description: specialist review\nUnique reviewed instructions.", encoding="utf-8")

    class FakeRouter:
        def __init__(self, *_args):
            pass

        def complete(self, messages, *_args, **_kwargs):
            return {"choices": [{"message": {"content": "Done."}}]}, type("Route", (), {"provider": "test", "model": "test"})()

    monkeypatch.setattr("omnix.runtime.Router", FakeRouter)
    store = Store(tmp_path / "db.sqlite3")
    runtime = AgentRuntime(Settings(), store, tmp_path)
    _, first = runtime.run("Perform a specialist review")
    assert "Unique reviewed instructions" not in store.messages(first)[0]["content"]
    SkillsManager(tmp_path).set_enabled("specialist-review", True)
    _, second = runtime.run("Perform a specialist review")
    assert "Unique reviewed instructions" in store.messages(second)[0]["content"]


def test_cancel_during_provider_request_prevents_tool_execution(monkeypatch, tmp_path: Path):
    cancelled = threading.Event()

    class FakeRouter:
        def __init__(self, *_args):
            pass

        def complete(self, *_args, **_kwargs):
            cancelled.set()
            call = {"id": "1", "function": {"name": "write_file", "arguments": '{"path":"result.txt","content":"unexpected"}'}}
            return {"choices": [{"message": {"content": "", "tool_calls": [call]}}]}, type("Route", (), {"provider": "test", "model": "test"})()

    monkeypatch.setattr("omnix.runtime.Router", FakeRouter)
    store = Store(tmp_path / "db.sqlite3")
    runtime = AgentRuntime(Settings(), store, tmp_path, approver=lambda _: True, cancel_event=cancelled)
    with pytest.raises(RuntimeError, match="Task cancelled"):
        runtime.run("Write a file")
    assert not (tmp_path / "result.txt").exists()
    assert store.db.execute("SELECT state FROM tasks WHERE id=?", (runtime.last_task_id,)).fetchone()[0] == "cancelled"


def test_cancel_between_tool_calls_prevents_next_call(monkeypatch, tmp_path: Path):
    cancelled = threading.Event()

    class FakeRouter:
        def __init__(self, *_args):
            pass

        def complete(self, *_args, **_kwargs):
            calls = [{"id": str(i), "function": {"name": "read_file", "arguments": '{"path":"note.txt"}'}} for i in range(2)]
            return {"choices": [{"message": {"content": "", "tool_calls": calls}}]}, type("Route", (), {"provider": "test", "model": "test"})()

    monkeypatch.setattr("omnix.runtime.Router", FakeRouter)
    runtime = AgentRuntime(Settings(), Store(tmp_path / "db.sqlite3"), tmp_path, cancel_event=cancelled)
    calls = []

    def call(name, args):
        calls.append((name, args))
        cancelled.set()
        return "first result"

    monkeypatch.setattr(runtime.tools, "call", call)
    with pytest.raises(RuntimeError, match="Task cancelled"):
        runtime.run("Read the file")
    assert len(calls) == 1


def test_runtime_executes_a_read_tool(monkeypatch, tmp_path: Path):
    (tmp_path / "note.txt").write_text("runtime works", encoding="utf-8")

    class FakeRouter:
        def __init__(self, _settings):
            self.calls = 0

        def complete(self, messages, tools, record=None):
            self.calls += 1
            route = type("Route", (), {"provider": "test", "model": "test"})()
            if self.calls == 1:
                response = {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "read_file", "arguments": '{"path":"note.txt"}'}}]}}]}
            else:
                response = {"choices": [{"message": {"role": "assistant", "content": "The file says runtime works.", "tool_calls": []}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if record:
                record(route, response.get("usage", {}), 1.0)
            return response, route

    monkeypatch.setattr("omnix.runtime.Router", FakeRouter)
    runtime = AgentRuntime(Settings(), Store(tmp_path / "db.sqlite3"), tmp_path)
    answer, _ = runtime.run("Read note.txt")
    assert answer == "The file says runtime works."


def test_integrated_backend_executes_unseen_directory_task(monkeypatch, tmp_path: Path):
    (tmp_path / "alpha.txt").write_text("alpha", encoding="utf-8")

    class FakeRouter:
        def __init__(self, _settings):
            self.calls = 0

        def complete(self, messages, tools, record=None):
            self.calls += 1
            route = type("Route", (), {"provider": "test", "model": "test"})()
            if self.calls == 1:
                message = {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "list_directory", "arguments": "{}"}}]}
            else:
                message = {"role": "assistant", "content": "I verified alpha.txt is present.", "tool_calls": []}
            response = {"choices": [{"message": message}], "usage": {"prompt_tokens": 2, "completion_tokens": 1}}
            if record:
                record(route, response["usage"], 1.0)
            return response, route

    monkeypatch.setattr("omnix.runtime.Router", FakeRouter)
    runtime = AgentRuntime(Settings(), Store(tmp_path / "db.sqlite3"), tmp_path)
    answer, _ = runtime.run("Inspect the workspace and report the files you verify.")
    assert answer == "I verified alpha.txt is present."


def test_integrated_backend_executes_gateway_textual_tool_list(monkeypatch, tmp_path: Path):
    (tmp_path / "gateway.txt").write_text("gateway", encoding="utf-8")

    class FakeRouter:
        def __init__(self, _settings):
            self.calls = 0

        def complete(self, messages, tools, record=None):
            self.calls += 1
            route = type("Route", (), {"provider": "omniroute", "model": "test"})()
            if self.calls == 2:
                assert any("OMNI-X tool result (list_directory)" in item.get("content", "") and "gateway.txt" in item.get("content", "") for item in messages)
            content = 'tool_calls: [{"name":"list_directory","arguments":"{}"}]' if self.calls == 1 else "The actual listing contained gateway.txt."
            response = {"choices": [{"message": {"role": "assistant", "content": content}}], "usage": {"prompt_tokens": 2, "completion_tokens": 1}}
            if record:
                record(route, response["usage"], 1.0)
            return response, route

    monkeypatch.setattr("omnix.runtime.Router", FakeRouter)
    runtime = AgentRuntime(Settings(), Store(tmp_path / "db.sqlite3"), tmp_path)
    answer, _ = runtime.run("List the workspace and report the actual result.")
    assert answer == "The actual listing contained gateway.txt."
    assert Store(tmp_path / "db.sqlite3").db.execute("SELECT COUNT(*) FROM events WHERE kind='tool_result'").fetchone()[0] == 1


def test_integrated_backend_executes_unseen_write_and_read_task(monkeypatch, tmp_path: Path):
    class FakeRouter:
        def __init__(self, _settings):
            self.calls = 0

        def complete(self, messages, tools, record=None):
            self.calls += 1
            route = type("Route", (), {"provider": "test", "model": "test"})()
            if self.calls == 1:
                call = {"id": "1", "function": {"name": "write_file", "arguments": '{"path":"result.txt","content":"verified"}'}}
                message = {"role": "assistant", "content": "", "tool_calls": [call]}
            elif self.calls == 2:
                call = {"id": "2", "function": {"name": "read_file", "arguments": '{"path":"result.txt"}'}}
                message = {"role": "assistant", "content": "", "tool_calls": [call]}
            else:
                message = {"role": "assistant", "content": "The result was written and read back as verified.", "tool_calls": []}
            response = {"choices": [{"message": message}], "usage": {"prompt_tokens": 2, "completion_tokens": 1}}
            if record:
                record(route, response["usage"], 1.0)
            return response, route

    monkeypatch.setattr("omnix.runtime.Router", FakeRouter)
    runtime = AgentRuntime(Settings(tool_policy="allow"), Store(tmp_path / "db.sqlite3"), tmp_path, approver=lambda _: True)
    answer, _ = runtime.run("Create result.txt, read it back, and report the observed content.")
    assert (tmp_path / "result.txt").read_text(encoding="utf-8") == "verified"
    assert answer == "The result was written and read back as verified."

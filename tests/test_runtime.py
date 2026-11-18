from pathlib import Path

from omnix.config import Settings
from omnix.runtime import AgentRuntime
from omnix.store import Store


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

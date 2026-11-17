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

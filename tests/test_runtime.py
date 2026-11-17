from pathlib import Path

from omnix.config import Settings
from omnix.runtime import AgentRuntime
from omnix.store import Store


def test_runtime_executes_a_read_tool(monkeypatch, tmp_path: Path):
    (tmp_path / "note.txt").write_text("runtime works", encoding="utf-8")

    class FakeClient:
        def __init__(self, _settings):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "read_file", "arguments": '{"path":"note.txt"}'}}]}}]}
            return {"choices": [{"message": {"role": "assistant", "content": "The file says runtime works.", "tool_calls": []}}]}

    monkeypatch.setattr("omnix.runtime.ModelClient", FakeClient)
    runtime = AgentRuntime(Settings(), Store(tmp_path / "db.sqlite3"), tmp_path)
    answer, _ = runtime.run("Read note.txt")
    assert answer == "The file says runtime works."

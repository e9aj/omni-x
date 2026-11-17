from pathlib import Path

from omnix.store import Store
from omnix.tools import ToolRegistry


def test_file_operation_scenario_is_real(tmp_path: Path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    tools = ToolRegistry(workspace, approver=lambda _: True)
    for name, content in {"one.txt": "one", "two.txt": "two", "three.txt": "three"}.items():
        tools.call("write_file", {"path": name, "content": content})
    summary = [tools.call("read_file", {"path": name}) for name in ("one.txt", "two.txt", "three.txt")]
    assert summary == ["one", "two", "three"]


def test_memory_survives_new_store_session(tmp_path: Path):
    db = tmp_path / "memory.sqlite3"
    first = Store(db)
    first.remember("preference", "Use pytest for OMNI-X")
    second = Store(db)
    assert second.recall("preference") == [{"key": "preference", "value": "Use pytest for OMNI-X"}]


def test_recovery_keeps_failed_operation_state(tmp_path: Path):
    store = Store(tmp_path / "state.sqlite3")
    session = store.new_session("recovery")
    task = store.start_task(session)
    store.update_task(task, "failed", "simulated command failure")
    row = store.db.execute("SELECT state,error FROM tasks WHERE id=?", (task,)).fetchone()
    assert tuple(row) == ("failed", "simulated command failure")

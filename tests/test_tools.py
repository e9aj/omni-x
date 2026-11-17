from pathlib import Path

from omnix.tools import PermissionDenied, ToolRegistry


def test_tools_are_workspace_scoped_and_writes_need_approval(tmp_path: Path):
    registry = ToolRegistry(tmp_path)
    (tmp_path / "note.txt").write_text("hello OMNI-X", encoding="utf-8")
    assert "OMNI-X" in registry.read_file("note.txt")
    assert "note.txt" in registry.search_text("omni")
    assert "requires explicit approval" in registry.call("write_file", {"path": "new.txt", "content": "x"})
    assert "outside" in registry.call("read_file", {"path": ".."})


def test_approved_write(tmp_path: Path):
    registry = ToolRegistry(tmp_path, approver=lambda _: True)
    assert registry.write_file("new.txt", "content") == "Wrote new.txt"
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "content"


def test_dangerous_command_is_rejected(tmp_path: Path):
    registry = ToolRegistry(tmp_path, approver=lambda _: True)
    assert "dangerous command rejected" in registry.call("run_command", {"command": "git reset --hard HEAD"})

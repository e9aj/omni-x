from pathlib import Path
import threading
import time
import sys

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


def test_hanging_command_is_gracefully_then_hard_cancelled(tmp_path: Path):
    cancel = threading.Event()
    registry = ToolRegistry(tmp_path, approver=lambda _: True, cancel_event=cancel)
    result = []

    def run():
        try:
            result.append(registry.run_command(f'"{sys.executable}" -c "import time; time.sleep(30)"'))
        except RuntimeError as exc:
            result.append(str(exc))

    thread = threading.Thread(target=run)
    thread.start(); time.sleep(.3); cancel.set(); thread.join(8)
    assert not thread.is_alive()
    assert "terminated" in result[0]

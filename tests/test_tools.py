from pathlib import Path
import threading
import time
import sys
import pytest

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


@pytest.mark.parametrize("name,arguments", [
    ("write_file", {"path": "new.txt", "content": "content"}),
    ("run_command", {"command": "echo unexpected"}),
])
def test_cancel_during_approval_prevents_action(tmp_path: Path, monkeypatch, name, arguments):
    cancel = threading.Event()

    def approve(_action):
        cancel.set()
        return True

    registry = ToolRegistry(tmp_path, approver=approve, cancel_event=cancel)
    monkeypatch.setattr("omnix.tools.subprocess.Popen", lambda *args, **kwargs: pytest.fail("command started after cancellation"))
    with pytest.raises(RuntimeError, match="Task cancelled"):
        registry.call(name, arguments)
    assert not (tmp_path / "new.txt").exists()


def test_dangerous_command_is_rejected(tmp_path: Path):
    registry = ToolRegistry(tmp_path, approver=lambda _: True)
    assert "dangerous command rejected" in registry.call("run_command", {"command": "git reset --hard HEAD"})


def test_verbose_command_output_is_bounded(tmp_path: Path):
    registry = ToolRegistry(tmp_path, approver=lambda _: True)
    result = registry.run_command(f'"{sys.executable}" -c "import sys; sys.stdout.write(\'x\' * 2000000); sys.stderr.write(\'done\')"')
    assert len(result) <= 20_000
    assert result.endswith("done")


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

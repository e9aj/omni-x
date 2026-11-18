import subprocess
import sys

from omnix.process_control import terminate_process_tree


def test_owned_process_tree_termination_does_not_touch_unrelated_process():
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    owned = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], creationflags=flags, start_new_session=(__import__("os").name != "nt"))
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], creationflags=flags, start_new_session=(__import__("os").name != "nt"))
    try:
        assert "stopped" in terminate_process_tree(owned)
        assert owned.poll() is not None
        assert unrelated.poll() is None
    finally:
        if unrelated.poll() is None:
            unrelated.terminate(); unrelated.wait(timeout=5)

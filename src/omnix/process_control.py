"""Owned-process cancellation for OMNI-X's Windows worker boundary."""
from __future__ import annotations

import os
import signal
import subprocess
import time


def terminate_process_tree(process: subprocess.Popen, graceful_seconds: float = 2.0) -> str:
    """Stop only *process* and descendants; never use a global process match."""
    if process.poll() is not None:
        return "already stopped"
    try:
        if os.name == "nt":
            # CTRL_BREAK gives console-aware children a graceful first chance.
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
            except (OSError, ValueError):
                process.terminate()
            try:
                process.wait(timeout=graceful_seconds)
                return "gracefully stopped"
            except subprocess.TimeoutExpired:
                # /PID + /T scopes termination to this owned root and its tree.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False, timeout=10)
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                process.wait(timeout=graceful_seconds)
                return "gracefully stopped"
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        return "termination timed out"
    return "force stopped"


def wait_owned_process(process: subprocess.Popen, cancel_event, timeout: float) -> tuple[str, bool]:
    """Poll an owned process so cancellation remains responsive."""
    deadline = time.monotonic() + timeout
    while process.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            return terminate_process_tree(process), True
        if time.monotonic() >= deadline:
            return terminate_process_tree(process), True
        time.sleep(0.05)
    return "completed", False

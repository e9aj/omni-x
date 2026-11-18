"""Opt-in bridge to Hermes' real browser_exec implementation.

Hermes browser automation lives in ``tools/browser_use_cli.py`` and depends on
Hermes' browser-harness/CDP lifecycle.  OMNI-X does not recreate that engine:
when the installer-managed Hermes source is present (or
``OMNIX_HERMES_SOURCE`` explicitly points at one), this adapter invokes the
official implementation in a subprocess with the same source checkout on
``PYTHONPATH``. The call remains behind OMNI-X's normal approval gate.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .hermes_runtime import hermes_python, installed_hermes_source


class HermesBrowserAdapter:
    def __init__(self, source: Path | None = None, approver=None):
        self.source = Path(source).expanduser().resolve() if source else installed_hermes_source()
        self.approver = approver or (lambda _: False)

    @property
    def available(self) -> bool:
        return bool(self.source and (self.source / "tools" / "browser_use_cli.py").exists())

    def execute(self, code: str, timeout_s: int = 120) -> str:
        if not self.available:
            return "Browser unavailable: configure OMNIX_HERMES_SOURCE to an inspected Hermes checkout."
        if not self.approver("browser automation: execute approved Hermes browser task"):
            return "Browser denied: explicit approval required"
        if not isinstance(code, str) or not code.strip():
            return "Browser error: code is required"
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(self.source), env.get("PYTHONPATH", "")]))
        python = hermes_python() or Path(sys.executable)
        env.setdefault("HERMES_HOME", str(self.source.parent))
        launcher = (
            "from tools.browser_use_cli import browser_exec; "
            "import sys; "
            "print(browser_exec(sys.argv[1], timeout_s=int(sys.argv[2])))"
        )
        try:
            result = subprocess.run(
                [str(python), "-c", launcher, code, str(max(1, min(int(timeout_s), 600)))],
                capture_output=True, text=True, timeout=max(5, min(int(timeout_s) + 15, 615)),
                env=env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return f"Browser error: {exc}"
        output = (result.stdout + result.stderr).strip()
        return output[-20_000:] or "Browser completed without output"

    def shutdown(self) -> str:
        """Use Hermes' lifecycle cleanup to close managed browser sessions."""
        if not self.available:
            return "Browser unavailable: configure the managed Hermes backend first"
        if not self.approver("browser shutdown: close managed browser sessions"):
            return "Browser shutdown denied: explicit approval required"
        python = hermes_python() or Path(sys.executable)
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(self.source), env.get("PYTHONPATH", "")]))
        env.setdefault("HERMES_HOME", str(self.source.parent))
        code = "from tools.browser_session_lifecycle import cleanup_all_browsers; cleanup_all_browsers(); print('Browser sessions shut down')"
        try:
            result = subprocess.run([str(python), "-c", code], capture_output=True, text=True, timeout=30, env=env)
        except (OSError, subprocess.SubprocessError) as exc:
            return f"Browser shutdown error: {exc}"
        return (result.stdout + result.stderr).strip()[-20_000:] or "Browser sessions shut down"

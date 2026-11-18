"""Opt-in bridge to Hermes' real browser_exec implementation.

Hermes browser automation lives in ``tools/browser_use_cli.py`` and depends on
Hermes' browser-harness/CDP lifecycle.  OMNI-X does not recreate that engine:
when ``OMNIX_HERMES_SOURCE`` is explicitly configured, this adapter invokes the
official implementation in a subprocess with the same source checkout on
``PYTHONPATH``.  The call remains behind OMNI-X's normal approval gate.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class HermesBrowserAdapter:
    def __init__(self, source: Path | None = None, approver=None):
        raw = source or os.environ.get("OMNIX_HERMES_SOURCE")
        self.source = Path(raw).expanduser().resolve() if raw else None
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
        launcher = (
            "from tools.browser_use_cli import browser_exec; "
            "import sys; "
            "print(browser_exec(sys.argv[1], timeout_s=int(sys.argv[2])))"
        )
        try:
            result = subprocess.run(
                [sys.executable, "-c", launcher, code, str(max(1, min(int(timeout_s), 600)))],
                capture_output=True, text=True, timeout=max(5, min(int(timeout_s) + 15, 615)),
                env=env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return f"Browser error: {exc}"
        output = (result.stdout + result.stderr).strip()
        return output[-20_000:] or "Browser completed without output"

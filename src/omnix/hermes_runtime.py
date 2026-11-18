"""Locate the installer-managed Hermes source without manual environment setup."""

from __future__ import annotations

import os
from pathlib import Path


def installed_hermes_source() -> Path | None:
    candidates: list[Path] = []
    explicit = os.environ.get("OMNIX_HERMES_SOURCE")
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "hermes" / "hermes-agent")
    candidates.append(Path.home() / ".hermes" / "hermes-agent")
    for candidate in candidates:
        source = candidate.resolve()
        if (source / "tools" / "browser_use_cli.py").exists() and (source / "skills").exists():
            return source
    return None


def hermes_python() -> Path | None:
    """Return the Python from Hermes' installer-managed, locked environment."""
    source = installed_hermes_source()
    if not source:
        return None
    root = source.parent
    for candidate in root.glob("installs/*/environments/*/venv/Scripts/python.exe"):
        if candidate.exists():
            return candidate
    for candidate in root.glob("installs/*/environments/*/venv/bin/python"):
        if candidate.exists():
            return candidate
    return None

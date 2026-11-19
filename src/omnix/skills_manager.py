"""Safe, unified management of Hermes and OMNI-X SKILL.md sources.

Discovery is read-only. Installation is explicit and requires a reviewed local
source; this module never downloads or executes skill code.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import data_dir
from .skills import Skill, skill_roots


@dataclass(frozen=True)
class SkillRecord:
    name: str
    path: str
    source: str
    description: str = ""
    permissions: tuple[str, ...] = ()
    credentials: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    enabled: bool = False
    installed: bool = False


def _metadata(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    values: dict[str, Any] = {}
    for line in text.splitlines()[:80]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        if key in {"description", "permissions", "credentials", "api_keys", "dependencies", "requires"}:
            values[key] = value.strip()
    def items(key: str) -> tuple[str, ...]:
        raw = values.get(key, "")
        return tuple(item.strip() for item in raw.replace(";", ",").split(",") if item.strip())
    return {"description": values.get("description", ""),
            "permissions": items("permissions"),
            "credentials": items("credentials") + items("api_keys"),
            "dependencies": items("dependencies") + items("requires")}


class SkillsManager:
    def __init__(self, workspace: Path | None = None, audit: Any | None = None):
        self.workspace = (workspace or Path.cwd()).resolve()
        self.install_root = self.workspace / ".omnix" / "skills"
        self.state_path = data_dir() / "skills.json"
        self.state = self._load_state()
        self.audit = audit

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if os.name != "nt":
            self.state_path.chmod(0o600)

    def browse(self) -> list[SkillRecord]:
        records: dict[str, SkillRecord] = {}
        for root in skill_roots(self.workspace):
            if not root.exists():
                continue
            source = "hermes-optional" if "optional-skills" in root.parts else ("hermes-bundled" if "hermes" in str(root).lower() else "omnix-custom")
            for marker in root.rglob("SKILL.md"):
                name = marker.parent.name
                if name in records:
                    continue
                meta = _metadata(marker)
                state = self.state.get(name, {})
                records[name] = SkillRecord(name, str(marker), source, meta["description"], meta["permissions"], meta["credentials"], meta["dependencies"], bool(state.get("enabled", False)), bool(state.get("installed", source == "omnix-custom")))
        return sorted(records.values(), key=lambda item: item.name.lower())

    def install(self, source: Path, *, reviewed: bool = False) -> SkillRecord:
        source = source.resolve()
        marker = source / "SKILL.md" if source.is_dir() else source
        if marker.name != "SKILL.md" or not marker.is_file():
            raise ValueError("skill source must contain SKILL.md")
        if not reviewed:
            raise PermissionError("skill installation requires explicit review confirmation")
        destination = self.install_root / marker.parent.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise FileExistsError(f"skill already installed: {marker.parent.name}")
        shutil.copytree(marker.parent, destination)
        self.state[marker.parent.name] = {"installed": True, "enabled": False, "source": str(source)}
        self._save_state()
        return next(item for item in self.browse() if item.name == marker.parent.name)

    def set_enabled(self, name: str, enabled: bool) -> SkillRecord:
        record = next((item for item in self.browse() if item.name == name), None)
        if record is None:
            raise KeyError(f"unknown skill: {name}")
        self.state.setdefault(name, {}).update({"enabled": enabled})
        self._save_state()
        return next(item for item in self.browse() if item.name == name)

    def active(self) -> list[Skill]:
        active_names = {item.name for item in self.browse() if item.enabled}
        return [Skill(item.name, Path(item.path), item.description, Path(item.path).read_text(encoding="utf-8")[:20_000]) for item in self.browse() if item.name in active_names]

    def relevant_context(self, prompt: str, *, allowed_permissions: set[str] | None = None,
                         credentials: Any | None = None) -> tuple[str, list[str], list[dict[str, str]]]:
        """Return enabled, relevant and dependency-satisfied instructions.

        The returned text is suitable for Hermes' ``ephemeral_system_prompt``;
        it contains no credential values. Skipped skills are returned as safe
        reason metadata for audit events.
        """
        tokens = {part.lower().strip(".,:;!?()[]{}\"") for part in prompt.split() if len(part) > 3}
        allowed = allowed_permissions or set()
        blocks: list[str] = []
        loaded: list[str] = []
        skipped: list[dict[str, str]] = []
        for item in self.browse():
            if not item.enabled:
                continue
            skill_tokens = set(item.name.lower().replace("_", "-").split("-"))
            if item.name.lower() not in tokens and not (tokens & skill_tokens):
                continue
            denied = [permission for permission in item.permissions if permission not in allowed]
            missing = [key for key in item.credentials if credentials is None or not credentials.available("skill:" + item.name, key)]
            missing_deps = [dep for dep in item.dependencies if shutil.which(dep) is None]
            if denied or missing or missing_deps:
                reason = "permissions" if denied else "credentials" if missing else "dependencies"
                skipped.append({"name": item.name, "reason": reason})
                if self.audit:
                    self.audit(item.name, "skipped", reason)
                continue
            blocks.append(f"## Reviewed skill: {item.name}\n{Path(item.path).read_text(encoding='utf-8')[:20_000]}")
            loaded.append(item.name)
            if self.audit:
                self.audit(item.name, "loaded", "relevant enabled skill")
        return "\n\n".join(blocks), loaded, skipped

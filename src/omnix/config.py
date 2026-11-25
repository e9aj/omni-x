from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("OMNIX_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    elif os.name == "nt":
        path = Path(os.environ.get("APPDATA", Path.home())) / "OMNI-X"
    else:
        path = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "omnix"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Settings:
    # The native OMNI-X runtime is the only execution authority. ``runtime``
    # remains in the schema solely to migrate old settings files.
    runtime: str = "omnix"
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    base_url: str = ""
    mode: str = "SMART"
    max_steps: int = 8
    tool_policy: str = "ask"
    max_cost_usd: float = 0.0
    allow_paid: bool = False
    request_timeout_seconds: int = 120
    provider_request_timeout_seconds: int = 120
    agent_execution_timeout_seconds: int = 300
    child_task_timeout_seconds: int = 360
    parent_orchestration_timeout_seconds: int = 420
    retry_limit: int = 2
    free_models: list[str] = field(default_factory=list)
    content_preference: str = "creative"


def config_path() -> Path:
    return data_dir() / "config.json"


def load_settings() -> Settings:
    path = config_path()
    if not path.exists():
        return Settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        values = {k: raw[k] for k in asdict(Settings()) if k in raw}
        settings = Settings(**values)
        if settings.runtime != "omnix":
            settings.runtime = "omnix"
        return settings
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(f"Invalid OMNI-X configuration at {path}: {exc}") from exc


def save_settings(settings: Settings) -> None:
    path = config_path()
    path.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)

"""Scoped metadata over OMNI-X's encrypted secret store.

Secret values remain in DPAPI-backed storage. This file contains only names,
integration scope and revocation metadata; it never stores secret values.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import data_dir
from .secrets import get_secret, set_secret


class CredentialManager:
    def __init__(self, metadata_path: Path | None = None):
        self.path = metadata_path or (data_dir() / "credential-metadata.json")
        self.records = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if self.path.exists() and self.path.stat().st_mode & 0o777:
            try: self.path.chmod(0o600)
            except OSError: pass

    def put(self, integration: str, key: str, value: str) -> None:
        if not integration or not key or not value:
            raise ValueError("integration, key and value are required")
        secret_name = f"integration:{integration}:{key}"
        set_secret(secret_name, value)
        self.records.setdefault(integration, {})[key] = {"secret_name": secret_name, "revoked": False, "updated": time.time()}
        self._save()

    def get(self, integration: str, key: str, *, allowed_integrations: set[str] | None = None) -> str | None:
        if allowed_integrations is not None and integration not in allowed_integrations:
            return None
        record = self.records.get(integration, {}).get(key)
        if not record or record.get("revoked"):
            return None
        return get_secret(record["secret_name"])

    def revoke(self, integration: str, key: str) -> bool:
        record = self.records.get(integration, {}).get(key)
        if not record:
            return False
        record["revoked"] = True
        record["updated"] = time.time()
        self._save()
        return True

    def list(self) -> list[dict[str, Any]]:
        return [{"integration": integration, "key": key, "revoked": bool(meta.get("revoked"))}
                for integration, values in self.records.items() for key, meta in values.items()]

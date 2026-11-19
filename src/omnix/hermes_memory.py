"""Hermes-compatible memory facade backed by OMNI-X SQLite."""

from __future__ import annotations

from typing import Any


class HermesMemoryAdapter:
    """Expose the small memory contract needed by Hermes without a second store."""

    def __init__(self, store: Any):
        self.store = store

    def remember(self, key: str, value: str) -> str:
        self.store.remember(key, value)
        return "Memory stored"

    def recall(self, query: str = "") -> list[dict[str, str]]:
        return self.store.recall(query)

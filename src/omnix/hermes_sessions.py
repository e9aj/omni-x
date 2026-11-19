"""Additive session bridge preserving OMNI-X SQLite history."""

from __future__ import annotations

from typing import Any


class HermesSessionBridge:
    """Record Hermes turns in the existing OMNI-X Store without replacing it."""

    def __init__(self, store: Any):
        self.store = store

    def begin(self, title: str = "Hermes session") -> str:
        return self.store.new_session(title)

    def record_turn(self, session_id: str, prompt: str, answer: str) -> None:
        self.store.add_message(session_id, "user", prompt)
        self.store.add_message(session_id, "assistant", answer)

    def bind(self, session_id: str, hermes_session_id: str | None) -> None:
        if hermes_session_id:
            self.store.bind_hermes_session(session_id, hermes_session_id)

    def history(self, session_id: str) -> list[dict[str, str]]:
        return self.store.messages(session_id)

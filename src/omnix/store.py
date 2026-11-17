from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

from .config import data_dir


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "omnix.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, title TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), role TEXT NOT NULL, content TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY, key TEXT NOT NULL, value TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, UNIQUE(key));
        """)
        self.db.commit()

    def new_session(self, title: str = "OMNI-X session") -> str:
        session_id = str(uuid.uuid4())
        now = time.time()
        self.db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", (session_id, title, now, now))
        self.db.commit()
        return session_id

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self.db.execute("INSERT INTO messages(session_id, role, content, created) VALUES (?, ?, ?, ?)", (session_id, role, content, time.time()))
        self.db.execute("UPDATE sessions SET updated=? WHERE id=?", (time.time(), session_id))
        self.db.commit()

    def messages(self, session_id: str) -> list[dict[str, str]]:
        rows = self.db.execute("SELECT role, content FROM messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def remember(self, key: str, value: str) -> None:
        now = time.time()
        self.db.execute("INSERT INTO memories(key,value,created,updated) VALUES (?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated", (key, value, now, now))
        self.db.commit()

    def recall(self, query: str = "") -> list[dict[str, str]]:
        rows = self.db.execute("SELECT key,value FROM memories WHERE key LIKE ? OR value LIKE ? ORDER BY updated DESC", (f"%{query}%", f"%{query}%")).fetchall()
        return [{"key": row["key"], "value": row["value"]} for row in rows]

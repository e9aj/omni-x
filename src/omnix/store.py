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
        CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, state TEXT NOT NULL, error TEXT, created REAL NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, task_id TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS usage (id INTEGER PRIMARY KEY, task_id TEXT, provider TEXT NOT NULL, model TEXT NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, estimated_cost REAL NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS provider_health (provider TEXT PRIMARY KEY, healthy INTEGER NOT NULL, latency_ms REAL NOT NULL, failures INTEGER NOT NULL DEFAULT 0, successes INTEGER NOT NULL DEFAULT 0, last_error TEXT, updated REAL NOT NULL);
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

    def start_task(self, session_id: str) -> str:
        task_id = str(uuid.uuid4())
        now = time.time()
        self.db.execute("INSERT INTO tasks VALUES (?, ?, 'running', NULL, ?, ?)", (task_id, session_id, now, now))
        self.db.commit()
        return task_id

    def update_task(self, task_id: str, state: str, error: str | None = None) -> None:
        self.db.execute("UPDATE tasks SET state=?, error=?, updated=? WHERE id=?", (state, error, time.time(), task_id))
        self.db.commit()

    def event(self, task_id: str, kind: str, detail: str) -> None:
        self.db.execute("INSERT INTO events(task_id,kind,detail,created) VALUES (?,?,?,?)", (task_id, kind, detail, time.time()))
        self.db.commit()

    def record_usage(self, task_id: str | None, provider: str, model: str, input_tokens: int, output_tokens: int, estimated_cost: float = 0.0) -> None:
        self.db.execute("INSERT INTO usage(task_id,provider,model,input_tokens,output_tokens,estimated_cost,created) VALUES (?,?,?,?,?,?,?)", (task_id, provider, model, input_tokens, output_tokens, estimated_cost, time.time()))
        self.db.commit()

    def record_provider_health(self, provider: str, healthy: bool, latency_ms: float, error: str | None = None) -> None:
        now = time.time()
        self.db.execute(
            """INSERT INTO provider_health(provider,healthy,latency_ms,failures,successes,last_error,updated)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(provider) DO UPDATE SET healthy=excluded.healthy, latency_ms=excluded.latency_ms,
               failures=provider_health.failures + excluded.failures, successes=provider_health.successes + excluded.successes,
               last_error=excluded.last_error, updated=excluded.updated""",
            (provider, int(healthy), float(latency_ms), int(not healthy), int(healthy), error, now),
        )
        self.db.commit()

    def provider_health(self, provider: str | None = None) -> dict[str, dict[str, object]]:
        query = "SELECT * FROM provider_health" + (" WHERE provider=?" if provider else "")
        rows = self.db.execute(query, (provider,) if provider else ()).fetchall()
        return {row["provider"]: dict(row) for row in rows}

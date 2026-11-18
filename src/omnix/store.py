from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path

from .config import data_dir


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "omnix.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self._lock = threading.RLock()
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
        CREATE TABLE IF NOT EXISTS schedules (id TEXT PRIMARY KEY, prompt TEXT NOT NULL, schedule TEXT NOT NULL, kind TEXT NOT NULL, next_run_at REAL NOT NULL, last_run_at REAL, enabled INTEGER NOT NULL DEFAULT 1, missed_runs INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, schedule_id TEXT, parent_job_id TEXT, session_id TEXT, prompt TEXT NOT NULL, state TEXT NOT NULL, result TEXT, error TEXT, attempts INTEGER NOT NULL DEFAULT 0, deadline REAL, created REAL NOT NULL, started REAL, finished REAL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS delegations (id TEXT PRIMARY KEY, parent_job_id TEXT NOT NULL, child_job_id TEXT NOT NULL, role TEXT NOT NULL, state TEXT NOT NULL, result TEXT, error TEXT, created REAL NOT NULL, updated REAL NOT NULL);
        """)
        self.db.commit()

    def recover_orphaned_jobs(self) -> int:
        """Make jobs abandoned by a process restart eligible for recovery."""
        cur = self.db.execute("UPDATE jobs SET state='queued', error='recovered after process restart', updated=? WHERE state='running'", (time.time(),))
        self.db.commit()
        return cur.rowcount

    def create_schedule(self, prompt: str, schedule: str, kind: str, next_run_at: float) -> str:
        ident = str(uuid.uuid4()); now = time.time()
        self.db.execute("INSERT INTO schedules VALUES (?,?,?,?,?,NULL,1,0,?,?)", (ident, prompt, schedule, kind, next_run_at, now, now))
        self.db.commit(); return ident

    def due_schedules(self, now: float) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM schedules WHERE enabled=1 AND next_run_at<=? ORDER BY next_run_at", (now,)).fetchall()]

    def advance_schedule(self, schedule_id: str, next_run_at: float | None, last_run_at: float, missed: int = 0) -> None:
        self.db.execute("UPDATE schedules SET next_run_at=?, last_run_at=?, missed_runs=missed_runs+?, enabled=CASE WHEN ? IS NULL THEN 0 ELSE enabled END, updated=? WHERE id=?", (next_run_at, last_run_at, missed, next_run_at, time.time(), schedule_id)); self.db.commit()

    def create_job(self, prompt: str, schedule_id: str | None = None, parent_job_id: str | None = None, deadline: float | None = None) -> str:
        ident = str(uuid.uuid4()); now = time.time()
        self.db.execute("INSERT INTO jobs(id,schedule_id,parent_job_id,session_id,prompt,state,result,error,attempts,deadline,created,started,finished,updated) VALUES (?,?,?,?,?,'queued',NULL,NULL,0,?,?,NULL,NULL,?)", (ident, schedule_id, parent_job_id, None, prompt, deadline, now, now)); self.db.commit(); return ident

    def job(self, job_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone(); return dict(row) if row else None

    def jobs(self, limit: int = 50) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT ?", (limit,)).fetchall()]

    def claim_job(self, job_id: str) -> bool:
        cur = self.db.execute("UPDATE jobs SET state='running', attempts=attempts+1, started=?, updated=? WHERE id=? AND state='queued'", (time.time(), time.time(), job_id)); self.db.commit(); return cur.rowcount == 1

    def finish_job(self, job_id: str, state: str, result: str | None = None, error: str | None = None) -> None:
        now = time.time(); self.db.execute("UPDATE jobs SET state=?, result=?, error=?, finished=?, updated=? WHERE id=?", (state, result, error, now, now, job_id)); self.db.commit()

    def cancel_job(self, job_id: str) -> None:
        self.db.execute("UPDATE jobs SET state='cancelled', error='cancelled by user', finished=?, updated=? WHERE id=? AND state IN ('queued','running')", (time.time(), time.time(), job_id)); self.db.commit()

    def create_delegation(self, parent_job_id: str, child_job_id: str, role: str) -> str:
        ident = str(uuid.uuid4()); now = time.time(); self.db.execute("INSERT INTO delegations VALUES (?,?,?,?,?,?,?,?,?)", (ident, parent_job_id, child_job_id, role, 'running', None, None, now, now)); self.db.commit(); return ident

    def delegations(self, parent_job_id: str) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM delegations WHERE parent_job_id=? ORDER BY created", (parent_job_id,)).fetchall()]

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

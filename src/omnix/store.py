from __future__ import annotations

import sqlite3
import threading
import json
import time
import uuid
import math
import hashlib
from functools import wraps
from pathlib import Path

from .config import data_dir

_DB_LOCKS: dict[str, threading.RLock] = {}
_DB_LOCKS_GUARD = threading.Lock()


def _locked(method):
    """Serialise complete operations on stores sharing the same database path."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "omnix.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        key = str(self.path.resolve())
        with _DB_LOCKS_GUARD:
            self._lock = _DB_LOCKS.setdefault(key, threading.RLock())
        with self._lock:
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
            CREATE TABLE IF NOT EXISTS provider_failures (id INTEGER PRIMARY KEY, provider TEXT NOT NULL, category TEXT NOT NULL, error TEXT NOT NULL, latency_ms REAL NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS model_health (model TEXT PRIMARY KEY, upstream TEXT, free INTEGER NOT NULL, context_length INTEGER NOT NULL DEFAULT 0, declared_tool_calling INTEGER NOT NULL DEFAULT 0, tested INTEGER NOT NULL DEFAULT 0, available INTEGER NOT NULL DEFAULT 0, tool_verified INTEGER NOT NULL DEFAULT 0, successes INTEGER NOT NULL DEFAULT 0, timeouts INTEGER NOT NULL DEFAULT 0, auth_failures INTEGER NOT NULL DEFAULT 0, rate_limits INTEGER NOT NULL DEFAULT 0, provider_errors INTEGER NOT NULL DEFAULT 0, tool_successes INTEGER NOT NULL DEFAULT 0, tool_failures INTEGER NOT NULL DEFAULT 0, avg_latency_ms REAL NOT NULL DEFAULT 0, p50_latency_ms REAL NOT NULL DEFAULT 0, p95_latency_ms REAL NOT NULL DEFAULT 0, input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0, latency_samples TEXT NOT NULL DEFAULT '[]', last_error TEXT, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS schedules (id TEXT PRIMARY KEY, prompt TEXT NOT NULL, schedule TEXT NOT NULL, kind TEXT NOT NULL, next_run_at REAL NOT NULL, last_run_at REAL, enabled INTEGER NOT NULL DEFAULT 1, missed_runs INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, schedule_id TEXT, parent_job_id TEXT, session_id TEXT, prompt TEXT NOT NULL, state TEXT NOT NULL, result TEXT, error TEXT, attempts INTEGER NOT NULL DEFAULT 0, deadline REAL, created REAL NOT NULL, started REAL, finished REAL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS delegations (id TEXT PRIMARY KEY, parent_job_id TEXT NOT NULL, child_job_id TEXT NOT NULL, role TEXT NOT NULL, state TEXT NOT NULL, result TEXT, error TEXT, created REAL NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS hermes_session_map (omnix_session_id TEXT PRIMARY KEY, hermes_session_id TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS skill_events (id INTEGER PRIMARY KEY, skill TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL, task_id TEXT, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS integration_states (name TEXT PRIMARY KEY, installed INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 0, revoked INTEGER NOT NULL DEFAULT 0, configured INTEGER NOT NULL DEFAULT 0, version TEXT, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS integration_events (id INTEGER PRIMARY KEY, name TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS workflows (id TEXT PRIMARY KEY, name TEXT NOT NULL, definition_json TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS workflow_runs (id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, state TEXT NOT NULL, result_json TEXT, error TEXT, created REAL NOT NULL, finished REAL);
            CREATE TABLE IF NOT EXISTS brain_embeddings (source_id TEXT PRIMARY KEY, source_type TEXT NOT NULL, content_hash TEXT NOT NULL, vector_json TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS brain_canvas (id INTEGER PRIMARY KEY CHECK(id=1), nodes_json TEXT NOT NULL, edges_json TEXT NOT NULL, viewport_json TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS memory_suggestions (id TEXT PRIMARY KEY, session_id TEXT, memory_key TEXT NOT NULL, memory_value TEXT NOT NULL, source TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
            """)
            columns = {row["name"] for row in self.db.execute("PRAGMA table_info(jobs)")}
            if "policy_json" not in columns:
                self.db.execute("ALTER TABLE jobs ADD COLUMN policy_json TEXT NOT NULL DEFAULT '{}'" )
            schedule_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(schedules)")}
            if "workflow_id" not in schedule_columns:
                self.db.execute("ALTER TABLE schedules ADD COLUMN workflow_id TEXT")
            self.db.commit()

    @_locked
    def upsert_embedding(self, source_id: str, source_type: str, content: str, vector: list[float]) -> None:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with self._lock:
            self.db.execute(
                """INSERT INTO brain_embeddings(source_id,source_type,content_hash,vector_json,updated)
                   VALUES (?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET source_type=excluded.source_type,
                   content_hash=excluded.content_hash, vector_json=excluded.vector_json, updated=excluded.updated""",
                (source_id, source_type, digest, json.dumps(vector), time.time()),
            )
            self.db.commit()

    @_locked
    def embeddings(self, limit: int = 1000) -> list[dict]:
        safe_limit = max(1, min(int(limit), 1000))
        rows = self.db.execute(f"SELECT * FROM brain_embeddings ORDER BY updated DESC LIMIT {safe_limit}").fetchall()  # nosec B608
        return [{**dict(row), "vector": json.loads(row["vector_json"])} for row in rows]

    @_locked
    def save_canvas(self, nodes: list[dict], edges: list[dict], viewport: dict) -> None:
        if len(nodes) > 1000 or len(edges) > 3000:
            raise ValueError("canvas is too large")
        with self._lock:
            self.db.execute(
                """INSERT INTO brain_canvas(id,nodes_json,edges_json,viewport_json,updated)
                   VALUES (1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET nodes_json=excluded.nodes_json,
                   edges_json=excluded.edges_json, viewport_json=excluded.viewport_json, updated=excluded.updated""",
                (json.dumps(nodes, sort_keys=True), json.dumps(edges, sort_keys=True), json.dumps(viewport, sort_keys=True), time.time()),
            )
            self.db.commit()

    @_locked
    def canvas(self) -> dict:
        row = self.db.execute("SELECT nodes_json, edges_json, viewport_json, updated FROM brain_canvas WHERE id=1").fetchone()
        if not row:
            return {"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}, "updated": None}
        return {"nodes": json.loads(row["nodes_json"]), "edges": json.loads(row["edges_json"]),
                "viewport": json.loads(row["viewport_json"]), "updated": row["updated"]}

    @_locked
    def add_memory_suggestion(self, memory_key: str, memory_value: str, *, session_id: str | None = None, source: str = "explicit") -> str:
        if not memory_key.strip() or len(memory_key) > 200 or not memory_value.strip() or len(memory_value) > 10_000:
            raise ValueError("memory suggestion is invalid")
        ident, now = str(uuid.uuid4()), time.time()
        with self._lock:
            self.db.execute("INSERT INTO memory_suggestions VALUES (?,?,?,?,?,?,?,?)", (ident, session_id, memory_key.strip(), memory_value.strip(), source[:100], "pending", now, now))
            self.db.commit()
        return ident

    @_locked
    def memory_suggestions(self, state: str | None = None) -> list[dict]:
        if state not in {None, "pending", "approved", "rejected", "deleted"}:
            raise ValueError("memory suggestion state is invalid")
        if state:
            rows = self.db.execute(
                "SELECT * FROM memory_suggestions WHERE state=? ORDER BY created DESC",
                (state,),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM memory_suggestions ORDER BY created DESC",
            ).fetchall()
        return [dict(row) for row in rows]

    @_locked
    def decide_memory_suggestion(self, ident: str, state: str, *, memory_key: str | None = None, memory_value: str | None = None) -> dict:
        if state not in {"approved", "rejected", "deleted"}:
            raise ValueError("memory decision is invalid")
        with self._lock:
            row = self.db.execute("SELECT * FROM memory_suggestions WHERE id=?", (ident,)).fetchone()
            if not row:
                raise KeyError("memory suggestion not found")
            key = memory_key.strip() if isinstance(memory_key, str) and memory_key.strip() else row["memory_key"]
            value = memory_value.strip() if isinstance(memory_value, str) and memory_value.strip() else row["memory_value"]
            self.db.execute("UPDATE memory_suggestions SET memory_key=?, memory_value=?, state=?, updated=? WHERE id=?", (key[:200], value[:10_000], state, time.time(), ident))
            if state == "approved":
                self.db.execute("INSERT INTO memories(key,value,created,updated) VALUES (?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated", (key[:200], value[:10_000], time.time(), time.time()))
            self.db.commit()
            result = self.db.execute("SELECT * FROM memory_suggestions WHERE id=?", (ident,)).fetchone()
        return dict(result)

    @_locked
    def save_workflow(self, name: str, definition: dict, workflow_id: str | None = None) -> str:
        ident, now = workflow_id or str(uuid.uuid4()), time.time()
        with self._lock:
            self.db.execute("INSERT INTO workflows(id,name,definition_json,enabled,created,updated) VALUES (?,?,?,0,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, definition_json=excluded.definition_json, updated=excluded.updated", (ident, name, json.dumps(definition, sort_keys=True), now, now))
            self.db.commit()
        return ident

    @_locked
    def workflows(self) -> list[dict]:
        return [{**dict(row), "definition": json.loads(row["definition_json"])} for row in self.db.execute("SELECT * FROM workflows ORDER BY updated DESC").fetchall()]

    @_locked
    def workflow_runs(self, workflow_id: str | None = None) -> list[dict]:
        if workflow_id:
            rows = self.db.execute("SELECT * FROM workflow_runs WHERE workflow_id=? ORDER BY created DESC", (workflow_id,)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM workflow_runs ORDER BY created DESC").fetchall()
        return [{**dict(row), "result": json.loads(row["result_json"]) if row["result_json"] else None} for row in rows]

    @_locked
    def start_workflow_run(self, workflow_id: str) -> str:
        ident, now = str(uuid.uuid4()), time.time()
        with self._lock:
            self.db.execute("INSERT INTO workflow_runs(id,workflow_id,state,result_json,error,created,finished) VALUES (?,?,?,NULL,NULL,?,NULL)", (ident, workflow_id, "running", now))
            self.db.commit()
        return ident

    @_locked
    def finish_workflow_run(self, run_id: str, state: str, result: dict | None = None, error: str | None = None) -> None:
        if state not in {"completed", "failed", "cancelled"}:
            raise ValueError("workflow terminal state is invalid")
        with self._lock:
            self.db.execute("UPDATE workflow_runs SET state=?, result_json=?, error=?, finished=? WHERE id=?", (state, json.dumps(result, sort_keys=True) if result is not None else None, error, time.time(), run_id))
            self.db.commit()

    @_locked
    def backup(self, destination: Path) -> Path:
        """Create a consistent SQLite backup without replacing the live DB."""
        destination = destination.expanduser().resolve()
        if destination == self.path.resolve():
            raise ValueError("backup destination must differ from the live database")
        destination.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(destination)
        try:
            with self._lock:
                self.db.backup(target)
            result = target.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError("SQLite backup integrity check failed")
        finally:
            target.close()
        return destination

    @staticmethod
    def restore(backup: Path, destination: Path) -> Path:
        """Restore a verified backup to a new database path."""
        backup, destination = backup.expanduser().resolve(), destination.expanduser().resolve()
        if backup == destination or not backup.is_file():
            raise ValueError("backup and destination are invalid")
        source = sqlite3.connect(backup)
        target = sqlite3.connect(destination)
        try:
            if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("SQLite backup is corrupt")
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("restored SQLite database failed integrity check")
        finally:
            target.close()
            source.close()
        return destination

    @_locked
    def recover_orphaned_jobs(self) -> int:
        """Make jobs abandoned by a process restart eligible for recovery."""
        cur = self.db.execute("UPDATE jobs SET state='queued', error='recovered after process restart', updated=? WHERE state='running'", (time.time(),))
        self.db.commit()
        return cur.rowcount

    @_locked
    def create_schedule(self, prompt: str, schedule: str, kind: str, next_run_at: float, workflow_id: str | None = None) -> str:
        with self._lock:
            ident = str(uuid.uuid4()); now = time.time()
            self.db.execute("INSERT INTO schedules(prompt,schedule,kind,next_run_at,last_run_at,enabled,missed_runs,created,updated,workflow_id,id) VALUES (?,?,?,?,NULL,1,0,?,?,?,?)", (prompt, schedule, kind, next_run_at, now, now, workflow_id, ident))
            self.db.commit(); return ident

    @_locked
    def due_schedules(self, now: float) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM schedules WHERE enabled=1 AND next_run_at<=? ORDER BY next_run_at", (now,)).fetchall()]

    @_locked
    def advance_schedule(self, schedule_id: str, next_run_at: float | None, last_run_at: float, missed: int = 0) -> None:
        with self._lock:
            self.db.execute("UPDATE schedules SET next_run_at=?, last_run_at=?, missed_runs=missed_runs+?, enabled=CASE WHEN ? IS NULL THEN 0 ELSE enabled END, updated=? WHERE id=?", (next_run_at, last_run_at, missed, next_run_at, time.time(), schedule_id)); self.db.commit()

    @_locked
    def create_job(self, prompt: str, schedule_id: str | None = None, parent_job_id: str | None = None, deadline: float | None = None, policy: dict | None = None) -> str:
        with self._lock:
            ident = str(uuid.uuid4()); now = time.time()
            self.db.execute("INSERT INTO jobs(id,schedule_id,parent_job_id,session_id,prompt,state,result,error,attempts,deadline,created,started,finished,updated,policy_json) VALUES (?,?,?,?,?,'queued',NULL,NULL,0,?,?,NULL,NULL,?,?)", (ident, schedule_id, parent_job_id, None, prompt, deadline, now, now, json.dumps(policy or {}, sort_keys=True))); self.db.commit(); return ident

    @_locked
    def job(self, job_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone(); return dict(row) if row else None

    @_locked
    def jobs(self, limit: int = 50) -> list[dict]:
        safe_limit = max(1, min(int(limit), 1000))
        # safe_limit is an internal bounded integer, never caller-supplied SQL.
        # Parameterised LIMIT has triggered sqlite API misuse on worker restart.
        return [dict(r) for r in self.db.execute(f"SELECT * FROM jobs ORDER BY created DESC LIMIT {safe_limit}").fetchall()]  # nosec B608

    @_locked
    def claim_job(self, job_id: str) -> bool:
        with self._lock:
            cur = self.db.execute("UPDATE jobs SET state='running', attempts=attempts+1, started=?, updated=? WHERE id=? AND state='queued'", (time.time(), time.time(), job_id)); self.db.commit(); return cur.rowcount == 1

    @_locked
    def finish_job(self, job_id: str, state: str, result: str | None = None, error: str | None = None) -> None:
        with self._lock:
            now = time.time(); self.db.execute("UPDATE jobs SET state=?, result=?, error=?, finished=?, updated=? WHERE id=?", (state, result, error, now, now, job_id)); self.db.commit()

    @_locked
    def cancel_job(self, job_id: str) -> None:
        with self._lock:
            self.db.execute("UPDATE jobs SET state='cancelled', error='cancelled by user', finished=?, updated=? WHERE id=? AND state IN ('queued','running')", (time.time(), time.time(), job_id)); self.db.commit()

    @_locked
    def create_delegation(self, parent_job_id: str, child_job_id: str, role: str) -> str:
        with self._lock:
            ident = str(uuid.uuid4()); now = time.time(); self.db.execute("INSERT INTO delegations VALUES (?,?,?,?,?,?,?,?,?)", (ident, parent_job_id, child_job_id, role, 'running', None, None, now, now)); self.db.commit(); return ident

    @_locked
    def delegations(self, parent_job_id: str) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM delegations WHERE parent_job_id=? ORDER BY created", (parent_job_id,)).fetchall()]

    @_locked
    def new_session(self, title: str = "OMNI-X session") -> str:
        session_id = str(uuid.uuid4())
        now = time.time()
        self.db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", (session_id, title, now, now))
        self.db.commit()
        return session_id

    @_locked
    def add_message(self, session_id: str, role: str, content: str) -> None:
        self.db.execute("INSERT INTO messages(session_id, role, content, created) VALUES (?, ?, ?, ?)", (session_id, role, content, time.time()))
        self.db.execute("UPDATE sessions SET updated=? WHERE id=?", (time.time(), session_id))
        self.db.commit()

    @_locked
    def messages(self, session_id: str) -> list[dict[str, str]]:
        rows = self.db.execute("SELECT role, content FROM messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    @_locked
    def bind_hermes_session(self, omnix_session_id: str, hermes_session_id: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO hermes_session_map VALUES (?,?,?)", (omnix_session_id, hermes_session_id, time.time()))
        self.db.commit()

    @_locked
    def hermes_session(self, omnix_session_id: str) -> str | None:
        row = self.db.execute("SELECT hermes_session_id FROM hermes_session_map WHERE omnix_session_id=?", (omnix_session_id,)).fetchone()
        return row["hermes_session_id"] if row else None

    @_locked
    def record_skill_event(self, skill: str, event: str, detail: str = "", task_id: str | None = None) -> None:
        self.db.execute("INSERT INTO skill_events(skill,event,detail,task_id,created) VALUES (?,?,?,?,?)", (skill, event, detail[:2000], task_id, time.time()))
        self.db.commit()

    @_locked
    def skill_events(self, skill: str | None = None) -> list[dict]:
        if skill:
            rows = self.db.execute("SELECT * FROM skill_events WHERE skill=? ORDER BY id", (skill,)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM skill_events ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    @_locked
    def integration_state(self, name: str) -> dict | None:
        row = self.db.execute("SELECT * FROM integration_states WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None

    @_locked
    def set_integration_state(self, name: str, *, installed: bool | None = None,
                              enabled: bool | None = None, revoked: bool | None = None,
                              configured: bool | None = None, version: str | None = None) -> None:
        current = self.integration_state(name) or {
            "installed": 0, "enabled": 0, "revoked": 0, "configured": 0, "version": None,
        }
        values = {
            "installed": int(current["installed"] if installed is None else installed),
            "enabled": int(current["enabled"] if enabled is None else enabled),
            "revoked": int(current["revoked"] if revoked is None else revoked),
            "configured": int(current["configured"] if configured is None else configured),
            "version": current["version"] if version is None else version,
        }
        with self._lock:
            self.db.execute(
                """INSERT INTO integration_states(name,installed,enabled,revoked,configured,version,updated)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(name) DO UPDATE SET installed=excluded.installed,
                   enabled=excluded.enabled, revoked=excluded.revoked, configured=excluded.configured,
                   version=excluded.version, updated=excluded.updated""",
                (name, values["installed"], values["enabled"], values["revoked"],
                 values["configured"], values["version"], time.time()),
            )
            self.db.commit()

    @_locked
    def record_integration_event(self, name: str, event: str, detail: str = "") -> None:
        with self._lock:
            self.db.execute(
                "INSERT INTO integration_events(name,event,detail,created) VALUES (?,?,?,?)",
                (name, event, detail[:2000], time.time()),
            )
            self.db.commit()

    @_locked
    def integration_events(self, name: str | None = None) -> list[dict]:
        if name:
            rows = self.db.execute("SELECT * FROM integration_events WHERE name=? ORDER BY id", (name,)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM integration_events ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    @_locked
    def remember(self, key: str, value: str) -> None:
        now = time.time()
        self.db.execute("INSERT INTO memories(key,value,created,updated) VALUES (?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated", (key, value, now, now))
        self.db.commit()

    @_locked
    def recall(self, query: str = "") -> list[dict[str, str]]:
        rows = self.db.execute("SELECT key,value FROM memories WHERE key LIKE ? OR value LIKE ? ORDER BY updated DESC", (f"%{query}%", f"%{query}%")).fetchall()
        return [{"key": row["key"], "value": row["value"]} for row in rows]

    @_locked
    def start_task(self, session_id: str) -> str:
        task_id = str(uuid.uuid4())
        now = time.time()
        self.db.execute("INSERT INTO tasks VALUES (?, ?, 'running', NULL, ?, ?)", (task_id, session_id, now, now))
        self.db.commit()
        return task_id

    @_locked
    def update_task(self, task_id: str, state: str, error: str | None = None) -> None:
        self.db.execute("UPDATE tasks SET state=?, error=?, updated=? WHERE id=?", (state, error, time.time(), task_id))
        self.db.commit()

    @_locked
    def event(self, task_id: str, kind: str, detail: str) -> None:
        # Task workers and the control path can share this Store connection.
        # Serialize the write so cancellation cannot interleave a commit with
        # runtime lifecycle/audit events on Windows SQLite.
        with self._lock:
            self.db.execute("INSERT INTO events(task_id,kind,detail,created) VALUES (?,?,?,?)", (task_id, kind, detail, time.time()))
            self.db.commit()

    @_locked
    def record_usage(self, task_id: str | None, provider: str, model: str, input_tokens: int, output_tokens: int, estimated_cost: float = 0.0) -> None:
        self.db.execute("INSERT INTO usage(task_id,provider,model,input_tokens,output_tokens,estimated_cost,created) VALUES (?,?,?,?,?,?,?)", (task_id, provider, model, input_tokens, output_tokens, estimated_cost, time.time()))
        self.db.commit()

    @_locked
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

    @_locked
    def provider_health(self, provider: str | None = None) -> dict[str, dict[str, object]]:
        if provider:
            rows = self.db.execute("SELECT * FROM provider_health WHERE provider=?", (provider,)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM provider_health").fetchall()
        return {row["provider"]: dict(row) for row in rows}

    @_locked
    def record_provider_failure(self, provider: str, category: str, error: str, latency_ms: float) -> None:
        with self._lock:
            self.db.execute("INSERT INTO provider_failures(provider,category,error,latency_ms,created) VALUES (?,?,?,?,?)", (provider, category, error[:2000], float(latency_ms), time.time()))
            self.db.commit()

    @_locked
    def record_model_probe(self, result: dict) -> None:
        with self._lock:
            old = self.db.execute("SELECT * FROM model_health WHERE model=?", (result["model"],)).fetchone()
            samples = []
            if old:
                try: samples = json.loads(old["latency_samples"] or "[]")
                except (TypeError, ValueError): samples = []
            samples = (samples + [float(result.get("latency_ms", 0))])[-100:]
            samples_sorted = sorted(samples)
            p50 = samples_sorted[len(samples_sorted) // 2]
            p95 = samples_sorted[min(len(samples_sorted) - 1, max(0, math.ceil(len(samples) * .95) - 1))]
            values = {
                "model": result["model"], "upstream": result.get("upstream"), "free": int(result.get("free", True)),
                "context_length": int(result.get("context_length", 0) or 0), "declared_tool_calling": int(result.get("declared_tool_calling", False)),
                "tested": 1, "available": int(result.get("available", False)), "tool_verified": int(result.get("tool_verified", False)),
                "successes": int(result.get("successes", 0)), "timeouts": int(result.get("timeouts", 0)), "auth_failures": int(result.get("auth_failures", 0)),
                "rate_limits": int(result.get("rate_limits", 0)), "provider_errors": int(result.get("provider_errors", 0)),
                "tool_successes": int(result.get("tool_successes", 0)), "tool_failures": int(result.get("tool_failures", 0)),
                "avg_latency_ms": sum(samples) / len(samples), "p50_latency_ms": p50, "p95_latency_ms": p95,
                "input_tokens": int(result.get("input_tokens", 0)), "output_tokens": int(result.get("output_tokens", 0)),
                "latency_samples": json.dumps(samples), "last_error": result.get("last_error"), "updated": time.time(),
            }
            self.db.execute("""INSERT INTO model_health(model,upstream,free,context_length,declared_tool_calling,tested,available,tool_verified,successes,timeouts,auth_failures,rate_limits,provider_errors,tool_successes,tool_failures,avg_latency_ms,p50_latency_ms,p95_latency_ms,input_tokens,output_tokens,latency_samples,last_error,updated)
                VALUES (:model,:upstream,:free,:context_length,:declared_tool_calling,:tested,:available,:tool_verified,:successes,:timeouts,:auth_failures,:rate_limits,:provider_errors,:tool_successes,:tool_failures,:avg_latency_ms,:p50_latency_ms,:p95_latency_ms,:input_tokens,:output_tokens,:latency_samples,:last_error,:updated)
                ON CONFLICT(model) DO UPDATE SET upstream=excluded.upstream,free=excluded.free,context_length=excluded.context_length,declared_tool_calling=excluded.declared_tool_calling,tested=1,available=excluded.available,tool_verified=MAX(model_health.tool_verified,excluded.tool_verified),successes=model_health.successes+excluded.successes,timeouts=model_health.timeouts+excluded.timeouts,auth_failures=model_health.auth_failures+excluded.auth_failures,rate_limits=model_health.rate_limits+excluded.rate_limits,provider_errors=model_health.provider_errors+excluded.provider_errors,tool_successes=model_health.tool_successes+excluded.tool_successes,tool_failures=model_health.tool_failures+excluded.tool_failures,avg_latency_ms=excluded.avg_latency_ms,p50_latency_ms=excluded.p50_latency_ms,p95_latency_ms=excluded.p95_latency_ms,input_tokens=model_health.input_tokens+excluded.input_tokens,output_tokens=model_health.output_tokens+excluded.output_tokens,latency_samples=excluded.latency_samples,last_error=excluded.last_error,updated=excluded.updated""", values)
            self.db.commit()

    @_locked
    def model_health(self, model: str | None = None) -> dict[str, dict[str, object]]:
        if model:
            rows = self.db.execute("SELECT * FROM model_health WHERE model=?", (model,)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM model_health").fetchall()
        return {row["model"]: dict(row) for row in rows}

    @_locked
    def record_model_tool_result(self, model: str, success: bool) -> None:
        """Promote only an actually executed tool result to tool evidence."""
        with self._lock:
            row = self.db.execute("SELECT model FROM model_health WHERE model=?", (model,)).fetchone()
            if not row:
                return
            self.db.execute(
                "UPDATE model_health SET tool_successes=tool_successes+?, tool_failures=tool_failures+?, tool_verified=MAX(tool_verified,?), updated=? WHERE model=?",
                (int(success), int(not success), int(success), time.time(), model),
            )
            self.db.commit()

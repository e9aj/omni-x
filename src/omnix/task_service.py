"""Durable OMNI-X task service.

Hermes's cron scheduler and worker ledger are authoritative references for the
schedule and lifecycle semantics.  Their agent-owned stores are deliberately
not opened here: OMNI-X remains the sole execution engine and policy authority.
The adapter uses Hermes's schedule parser when its managed installation is
available, with a small dependency-free interval/ISO fallback for Windows
bootstrap and tests.
"""
from __future__ import annotations

import datetime as dt
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .config import Settings
from .runtime import AgentRuntime
from .store import Store


def _parse_schedule(value: str) -> tuple[str, float, float | None]:
    """Return kind, first due epoch, recurrence seconds (None = one-shot)."""
    raw = value.strip()
    # Prefer the installed Hermes parser, but do not make OMNI-X installation
    # depend on Hermes' optional croniter package.
    try:
        from .hermes_runtime import installed_hermes_source
        import sys
        source = installed_hermes_source()
        if source:
            source_text = str(source)
            if source_text not in sys.path:
                sys.path.insert(0, source_text)
            from cron.jobs import parse_schedule  # type: ignore
            try:
                parsed = parse_schedule(raw)
            except (ValueError, TypeError):
                parsed = None
            if parsed is None:
                raise ImportError("Hermes parser does not support this local interval")
            kind = str(parsed["kind"])
            if kind == "once":
                return kind, dt.datetime.fromisoformat(parsed["run_at"]).timestamp(), None
            if kind == "interval":
                seconds = float(parsed["minutes"]) * 60
                return kind, time.time() + seconds, seconds
            # Hermes cron expressions need croniter; preserving the explicit
            # error is safer than silently interpreting a cron expression.
            raise ValueError("cron expressions require Hermes croniter support")
    except ImportError:
        pass
    if re.fullmatch(r"(?:every\s+)?\d+(?:\.\d+)?[smhd]", raw.lower()):
        token = raw.lower().replace("every", "").strip()
        amount, unit = float(token[:-1]), token[-1]
        seconds = amount * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
        return "interval", time.time() + seconds, seconds
    try:
        when = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("schedule must be an ISO timestamp or interval such as 'every 1m'") from exc
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return "once", when.timestamp(), None


class TaskService:
    """One durable queue for schedules, background jobs and child agents."""

    def __init__(self, settings: Settings, store: Store | None = None, workspace: Path | None = None,
                 approver: Callable[[str], bool] | None = None, executor: Callable[[str, str | None], str] | None = None,
                 max_workers: int = 2):
        self.settings, self.store = settings, store or Store()
        self.workspace, self.approver = Path(workspace or Path.cwd()).resolve(), approver
        self._executor = executor
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="omnix-worker")
        self._stop = threading.Event(); self._wake = threading.Event(); self._thread: threading.Thread | None = None
        self._cancel: dict[str, threading.Event] = {}
        self.store.recover_orphaned_jobs()

    def start(self) -> None:
        if self._thread and self._thread.is_alive(): return
        self._thread = threading.Thread(target=self._loop, name="omnix-task-service", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set(); self._wake.set()
        if self._thread: self._thread.join(timeout=5)
        self._pool.shutdown(wait=True, cancel_futures=True)

    def schedule(self, prompt: str, schedule: str) -> str:
        kind, first, _ = _parse_schedule(schedule)
        ident = self.store.create_schedule(prompt, schedule, kind, first)
        self.start(); self._wake.set(); return ident

    def enqueue(self, prompt: str, parent_job_id: str | None = None, deadline_seconds: float | None = None) -> str:
        deadline = time.time() + deadline_seconds if deadline_seconds else None
        ident = self.store.create_job(prompt, parent_job_id=parent_job_id, deadline=deadline)
        self.start(); self._wake.set(); return ident

    def delegate(self, parent_job_id: str, tasks: list[dict[str, str]]) -> list[str]:
        """Create isolated child jobs; all execute through the same OMNI-X runtime."""
        children = []
        for item in tasks:
            child = self.enqueue(item["prompt"], parent_job_id=parent_job_id)
            self.store.create_delegation(parent_job_id, child, item.get("role", "generalist")); children.append(child)
        return children

    def cancel(self, job_id: str) -> None:
        event = self._cancel.setdefault(job_id, threading.Event()); event.set(); self.store.cancel_job(job_id); self._wake.set()

    def status(self, job_id: str | None = None) -> dict | list[dict] | None:
        return self.store.job(job_id) if job_id else self.store.jobs()

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = time.time()
            for row in self.store.due_schedules(now):
                try:
                    _, _, recurrence = _parse_schedule(row["schedule"])
                    next_run = now + recurrence if recurrence else None
                    self.store.advance_schedule(row["id"], next_run, now, missed=0)
                    self.enqueue(row["prompt"])
                except Exception as exc:
                    self.store.event("schedule:" + row["id"], "schedule_error", str(exc))
                    self.store.advance_schedule(row["id"], None, now)
            for row in self.store.jobs(100):
                if row["state"] == "queued":
                    self._pool.submit(self._run, row["id"])
            self._wake.wait(0.25); self._wake.clear()

    def _run(self, job_id: str) -> None:
        # Multiple pollers may see a row; the atomic claim ensures one owner.
        db = Store(self.store.path)
        if not db.claim_job(job_id): return
        row = db.job(job_id) or {}; cancel = self._cancel.setdefault(job_id, threading.Event())
        try:
            if cancel.is_set(): raise RuntimeError("Task cancelled")
            if row.get("deadline") and time.time() > row["deadline"]: raise TimeoutError("task deadline exceeded")
            session_id = row.get("session_id")
            if self._executor:
                result = self._executor(row["prompt"], session_id)
            else:
                runtime = AgentRuntime(self.settings, Store(self.store.path), self.workspace, self.approver)
                result, session_id = runtime.run(row["prompt"], session_id)
            db.finish_job(job_id, "completed", result=result)
            if row.get("parent_job_id"):
                self._settle_child(db, row["parent_job_id"], job_id, "completed", result, None)
        except Exception as exc:
            state = "cancelled" if cancel.is_set() or str(exc) == "Task cancelled" else "failed"
            db.finish_job(job_id, state, error=str(exc))
            if row.get("parent_job_id"):
                self._settle_child(db, row["parent_job_id"], job_id, state, None, str(exc))

    def _settle_child(self, db: Store, parent: str, child: str, state: str, result: str | None, error: str | None) -> None:
        db.db.execute("UPDATE delegations SET state=?, result=?, error=?, updated=? WHERE parent_job_id=? AND child_job_id=?", (state, result, error, time.time(), parent, child)); db.db.commit()


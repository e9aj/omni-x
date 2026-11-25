"""Durable OMNI-X task service.

OMNI-X owns schedule parsing, the durable worker ledger and execution policy.
The service does not open an external scheduler or agent-owned store.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .config import Settings
from .scheduling import parse_schedule
from .runtime import AgentRuntime
from .store import Store
from .workflow import WorkflowRunner, WorkflowStep, WorkflowError


def _parse_schedule(value: str) -> tuple[str, float, float | None]:
    """Return kind, first due epoch, recurrence seconds (None = one-shot)."""
    return parse_schedule(value)


class TaskService:
    """One durable queue for schedules, background jobs and child agents."""

    def __init__(self, settings: Settings, store: Store | None = None, workspace: Path | None = None,
                 approver: Callable[[str], bool] | None = None, executor: Callable[[str, str | None], str] | None = None,
                 max_workers: int = 2, cancellable_approver: Callable[[str, threading.Event], bool] | None = None):
        self.settings, self.store = settings, store or Store()
        self.workspace, self.approver = Path(workspace or Path.cwd()).resolve(), approver
        self.cancellable_approver = cancellable_approver
        self._executor = executor
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="omnix-worker")
        self._stop = threading.Event(); self._wake = threading.Event(); self._thread: threading.Thread | None = None
        self._cancel: dict[str, threading.Event] = {}
        self._workflow_cancel: dict[str, threading.Event] = {}
        self._inflight: set[str] = set()
        self._inflight_lock = threading.Lock()
        self.store.recover_orphaned_jobs()

    def start(self) -> None:
        if self._thread and self._thread.is_alive(): return
        self._thread = threading.Thread(target=self._loop, name="omnix-task-service", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set(); self._wake.set()
        for event in list(self._cancel.values()) + list(self._workflow_cancel.values()):
            event.set()
        if self._thread: self._thread.join(timeout=5)
        self._pool.shutdown(wait=True, cancel_futures=True)

    def _approve(self, action: str, cancel: threading.Event) -> bool:
        if cancel.is_set():
            return False
        if self.cancellable_approver:
            return bool(self.cancellable_approver(action, cancel)) and not cancel.is_set()
        return bool(self.approver and self.approver(action)) and not cancel.is_set()

    def schedule(self, prompt: str, schedule: str) -> str:
        kind, first, _ = _parse_schedule(schedule)
        ident = self.store.create_schedule(prompt, schedule, kind, first)
        self.start(); self._wake.set(); return ident

    def schedule_workflow(self, workflow_id: str, schedule: str) -> str:
        if not any(item["id"] == workflow_id for item in self.store.workflows()):
            raise KeyError("workflow not found")
        kind, first, _ = _parse_schedule(schedule)
        ident = self.store.create_schedule("workflow:" + workflow_id, schedule, kind, first, workflow_id=workflow_id)
        self.start(); self._wake.set(); return ident

    def enqueue(self, prompt: str, parent_job_id: str | None = None, deadline_seconds: float | None = None) -> str:
        deadline = time.time() + deadline_seconds if deadline_seconds else None
        policy = {"mode": self.settings.mode, "allow_paid": self.settings.allow_paid, "max_cost_usd": self.settings.max_cost_usd, "tool_policy": self.settings.tool_policy}
        if parent_job_id:
            parent = self.store.job(parent_job_id)
            if parent and parent.get("policy_json"):
                policy = json.loads(parent["policy_json"])
        ident = self.store.create_job(prompt, parent_job_id=parent_job_id, deadline=deadline, policy=policy)
        self.start(); self._wake.set(); return ident

    def delegate(self, parent_job_id: str, tasks: list[dict[str, str]]) -> list[str]:
        """Create isolated child jobs; all execute through the same OMNI-X runtime."""
        children = []
        for item in tasks:
            child = self.enqueue(item["prompt"], parent_job_id=parent_job_id)
            self.store.create_delegation(parent_job_id, child, item.get("role", "generalist")); children.append(child)
        return children

    def aggregate(self, parent_job_id: str) -> dict:
        """Commit a parent result only after every child reaches a terminal state."""
        rows = self.store.delegations(parent_job_id)
        if not rows:
            raise ValueError("parent has no delegated children")
        if any(row["state"] in {"running"} for row in rows):
            return {"state": "running", "children": rows}
        failed = [row for row in rows if row["state"] != "completed"]
        state = "failed" if failed else "completed"
        payload = {"children": [{"role": row["role"], "state": row["state"], "result": row["result"], "error": row["error"]} for row in rows]}
        self.store.finish_job(parent_job_id, state, result=json.dumps(payload, sort_keys=True), error=("child failure" if failed else None))
        return {"state": state, **payload}

    def cancel(self, job_id: str) -> None:
        event = self._cancel.setdefault(job_id, threading.Event()); event.set(); self.store.cancel_job(job_id); self._wake.set()

    def status(self, job_id: str | None = None) -> dict | list[dict] | None:
        return self.store.job(job_id) if job_id else self.store.jobs()

    def start_workflow(self, workflow_id: str) -> str:
        run_id = self.store.start_workflow_run(workflow_id)
        cancel = threading.Event()
        self._workflow_cancel[run_id] = cancel
        self._pool.submit(self._run_workflow_background, workflow_id, run_id, cancel)
        return run_id

    def cancel_workflow(self, run_id: str) -> None:
        event = self._workflow_cancel.get(run_id)
        row = next((item for item in self.store.workflow_runs() if item["id"] == run_id), None)
        if not row or row["state"] != "running":
            raise KeyError("workflow run is not active")
        if event:
            event.set()
        self.store.finish_workflow_run(run_id, "cancelled", error="cancelled by user")

    def _run_workflow_background(self, workflow_id: str, run_id: str, cancel: threading.Event) -> None:
        try:
            self.run_workflow(workflow_id, cancel=cancel, run_id=run_id)
        except Exception:
            pass
        finally:
            self._workflow_cancel.pop(run_id, None)

    def run_workflow(self, workflow_id: str, cancel: threading.Event | None = None, run_id: str | None = None) -> dict:
        definitions = {item["id"]: item for item in self.store.workflows()}
        definition = definitions.get(workflow_id)
        if not definition:
            raise KeyError("workflow not found")
        run_id = run_id or self.store.start_workflow_run(workflow_id)
        cancel = cancel or threading.Event()
        steps = []
        for item in definition["definition"].get("nodes", []):
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise WorkflowError("workflow node is invalid")
            payload = dict(item.get("payload") or {})
            if item.get("action") == "agent":
                payload.setdefault("prompt", item.get("prompt", item["id"]))
            steps.append(WorkflowStep(id=item["id"], action=item.get("action", "agent"), payload=payload,
                                      depends_on=tuple(item.get("depends_on") or ()), retries=int(item.get("retries", 0)),
                                      timeout_seconds=float(item.get("timeout_seconds", 30))))
        def agent(payload: dict, event: threading.Event) -> str:
            runtime_store = Store(self.store.path)
            try:
                runtime = AgentRuntime(self.settings, runtime_store, self.workspace, lambda action: self._approve(action, event), cancel_event=event)
                result, _ = runtime.run(str(payload.get("prompt", "")), None)
                return result
            finally:
                runtime_store.db.close()
        runner = WorkflowRunner(agent=agent, integration=None,
                                approve=lambda payload: self._approve(str(payload.get("action", "workflow approval")), cancel),
                                audit=lambda event, detail: self.store.event("workflow:" + run_id, event, detail))
        try:
            result = runner.run(steps, cancel=cancel)
            self.store.finish_workflow_run(run_id, "completed", result)
            return {"run_id": run_id, "state": "completed", "result": result}
        except Exception as exc:
            state = "cancelled" if cancel.is_set() else "failed"
            self.store.finish_workflow_run(run_id, state, error=str(exc))
            raise
        finally:
            runner.close()

    def run_worker_forever(self, idle_seconds: float = 3.0) -> None:
        """Run the managed worker host until idle and no future schedule exists.

        This is the detached Windows entry point.  State is always in SQLite;
        a new process can reclaim rows after a crash without inheriting a live
        Hermes process or session.
        """
        self.start(); idle_since = time.monotonic()
        try:
            while not self._stop.is_set():
                rows = self.store.jobs(100)
                schedules = self.store.db.execute("SELECT 1 FROM schedules WHERE enabled=1 LIMIT 1").fetchone()
                active = any(row["state"] in {"queued", "running"} for row in rows)
                if active or schedules:
                    idle_since = time.monotonic()
                elif time.monotonic() - idle_since >= idle_seconds:
                    break
                time.sleep(.25)
        finally:
            self.close()

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = time.time()
            for row in self.store.due_schedules(now):
                try:
                    kind, parsed_next, recurrence = _parse_schedule(row["schedule"])
                    # Re-parse cron expressions after each fire; intervals use
                    # a fixed duration and one-shot schedules do not recur.
                    next_run = (now + recurrence) if recurrence else (parsed_next if kind == "cron" else None)
                    self.store.advance_schedule(row["id"], next_run, now, missed=0)
                    if row.get("workflow_id"):
                        self.start_workflow(row["workflow_id"])
                    else:
                        self.enqueue(row["prompt"])
                except Exception as exc:
                    self.store.event("schedule:" + row["id"], "schedule_error", str(exc))
                    self.store.advance_schedule(row["id"], None, now)
            for row in self.store.jobs(100):
                if row["state"] == "queued":
                    with self._inflight_lock:
                        if row["id"] in self._inflight:
                            continue
                        self._inflight.add(row["id"])
                    self._pool.submit(self._run, row["id"])
            self._wake.wait(0.25); self._wake.clear()

    def _run(self, job_id: str) -> None:
        # Multiple pollers may see a row; the atomic claim ensures one owner.
        db = Store(self.store.path)
        try:
            if not db.claim_job(job_id):
                return
            row = db.job(job_id) or {}; cancel = self._cancel.setdefault(job_id, threading.Event())
            if self._stop.is_set():
                cancel.set()
            try:
                if cancel.is_set(): raise RuntimeError("Task cancelled")
                if row.get("deadline") and time.time() > row["deadline"]: raise TimeoutError("task deadline exceeded")
                session_id = row.get("session_id")
                if self._executor:
                    result = self._executor(row["prompt"], session_id)
                else:
                    result, session_id = self._run_omnix_job(row, cancel, job_id)
                if row.get("parent_job_id"):
                    self._settle_child(db, row["parent_job_id"], job_id, "completed", result, None)
                # Settle the delegation before exposing the child as completed.
                db.finish_job(job_id, "completed", result=result)
            except Exception as exc:
                state = "cancelled" if cancel.is_set() or str(exc) == "Task cancelled" else "failed"
                if row.get("parent_job_id"):
                    self._settle_child(db, row["parent_job_id"], job_id, state, None, str(exc))
                db.finish_job(job_id, state, error=str(exc))
        finally:
            db.db.close()
            with self._inflight_lock: self._inflight.discard(job_id)

    def _job_settings(self, row: dict) -> Settings:
        policy = json.loads(row.get("policy_json") or "{}")
        values = {"mode": policy.get("mode", self.settings.mode),
                  "allow_paid": policy.get("allow_paid", self.settings.allow_paid),
                  "max_cost_usd": policy.get("max_cost_usd", self.settings.max_cost_usd),
                  "tool_policy": policy.get("tool_policy", self.settings.tool_policy)}
        return Settings(**{**self.settings.__dict__, **values})

    def _run_omnix_job(self, row: dict, cancel: threading.Event, job_id: str) -> tuple[str, str | None]:
        runtime_store = Store(self.store.path)
        try:
            runtime = AgentRuntime(self._job_settings(row), runtime_store, self.workspace, lambda action: self._approve(action, cancel),
                                   cancel_event=cancel,
                                   delegate_handler=lambda **args: self._delegate_for_job(job_id, cancel, **args))
            result, session_id = runtime.run(row["prompt"], row.get("session_id"))
            if row.get("parent_job_id"):
                tool_events = runtime_store.db.execute("SELECT 1 FROM events WHERE task_id=? AND kind='tool_result' LIMIT 1", (runtime.last_task_id,)).fetchone()
                if not tool_events:
                    raise RuntimeError("delegated child completed without a verified tool result")
            return result, session_id
        finally:
            runtime_store.db.close()

    def _delegate_for_job(self, parent_job_id: str, cancel: threading.Event, prompt: str, role: str = "specialist") -> str:
        if cancel.is_set():
            raise RuntimeError("Task cancelled")
        child_budget = max(30.0, float(getattr(self.settings, "child_task_timeout_seconds", self.settings.request_timeout_seconds * 2)))
        child = self.enqueue(prompt, parent_job_id=parent_job_id, deadline_seconds=child_budget)
        self.store.create_delegation(parent_job_id, child, role)
        # Parent waiting and child execution have independent bounded budgets.
        deadline = time.monotonic() + max(30.0, float(getattr(self.settings, "parent_orchestration_timeout_seconds", self.settings.request_timeout_seconds * 3)))
        while time.monotonic() < deadline:
            if cancel.is_set():
                self.cancel(child); raise RuntimeError("Task cancelled")
            with self.store._lock:
                row = self.store.job(child)
            if row and row["state"] in {"completed", "failed", "cancelled"}:
                if row["state"] != "completed":
                    raise RuntimeError(f"delegated child {child} {row['state']}: {row.get('error')}")
                return json.dumps({"child_job_id": child, "role": role, "result": row.get("result")}, sort_keys=True)
            time.sleep(.1)
        self.cancel(child)
        raise TimeoutError(f"delegated child {child} timed out")

    def _settle_child(self, db: Store, parent: str, child: str, state: str, result: str | None, error: str | None) -> None:
        with db._lock:
            db.db.execute("UPDATE delegations SET state=?, result=?, error=?, updated=? WHERE parent_job_id=? AND child_job_id=?", (state, result, error, time.time(), parent, child)); db.db.commit()


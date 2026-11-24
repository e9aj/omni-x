"""Permission-controlled workflow execution primitives for TaskService."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable


class WorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    condition: Callable[[dict[str, Any]], bool] | None = None
    retries: int = 0
    timeout_seconds: float = 30.0


class WorkflowRunner:
    """Execute a validated workflow with no authority beyond supplied callbacks."""

    def __init__(self, *, agent: Callable[[dict[str, Any], threading.Event], Any] | None = None,
                 integration: Callable[[dict[str, Any], threading.Event], Any] | None = None,
                 approve: Callable[[dict[str, Any]], bool] | None = None,
                 audit: Callable[[str, str], None] | None = None, max_workers: int = 3):
        self.agent, self.integration, self.approve, self.audit = agent, integration, approve, audit
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="omnix-workflow")

    def _record(self, event: str, detail: str) -> None:
        if self.audit:
            self.audit(event, detail[:500])

    def run(self, steps: list[WorkflowStep], *, cancel: threading.Event | None = None) -> dict[str, Any]:
        if not steps or len(steps) > 100 or len({step.id for step in steps}) != len(steps):
            raise WorkflowError("workflow steps are invalid")
        by_id = {step.id: step for step in steps}
        if any(step.action not in {"agent", "integration", "approval"} or step.timeout_seconds <= 0 or step.timeout_seconds > 3600 or step.retries < 0 or step.retries > 3 or any(dep not in by_id for dep in step.depends_on) for step in steps):
            raise WorkflowError("workflow step policy is invalid")
        results: dict[str, Any] = {}
        pending = set(by_id)
        while pending:
            if cancel and cancel.is_set():
                self._record("cancelled", "workflow")
                raise WorkflowError("workflow cancelled")
            ready = [by_id[item] for item in pending if all(dep in results for dep in by_id[item].depends_on)]
            if not ready:
                raise WorkflowError("workflow dependencies contain a cycle")
            parallel = [step for step in ready if step.action != "approval"]
            approvals = [step for step in ready if step.action == "approval"]
            for step in approvals:
                if self.approve is None or not self.approve(step.payload):
                    self._record("step_denied", step.id)
                    raise PermissionError(f"workflow approval denied: {step.id}")
                results[step.id] = {"approved": True}
                pending.remove(step.id)
            futures = {self.pool.submit(self._run_step, step, results, cancel): step for step in parallel}
            for future, step in futures.items():
                try:
                    results[step.id] = future.result(timeout=step.timeout_seconds * (step.retries + 1))
                    pending.remove(step.id)
                except FutureTimeout as exc:
                    if cancel:
                        cancel.set()
                    raise WorkflowError(f"workflow step timed out: {step.id}") from exc
        self._record("completed", str(len(results)))
        return results

    def _run_step(self, step: WorkflowStep, results: dict[str, Any], cancel: threading.Event | None) -> Any:
        if step.condition and not step.condition(results):
            self._record("step_skipped", step.id)
            return {"skipped": True}
        callback = self.agent if step.action == "agent" else self.integration
        if callback is None:
            raise WorkflowError(f"workflow action is unavailable: {step.action}")
        last: Exception | None = None
        for attempt in range(step.retries + 1):
            if cancel and cancel.is_set():
                raise WorkflowError("workflow cancelled")
            try:
                self._record("step_started", step.id)
                result = callback({**step.payload, "results": dict(results)}, cancel or threading.Event())
                self._record("step_completed", step.id)
                return result
            except Exception as exc:
                last = exc
                self._record("step_retry", step.id)
        assert last is not None
        raise WorkflowError(f"workflow step failed: {step.id}") from last

    def close(self) -> None:
        self.pool.shutdown(wait=True, cancel_futures=True)

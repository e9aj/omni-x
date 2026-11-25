import time
import sqlite3
import pytest
from pathlib import Path

from omnix.config import Settings
from omnix.store import Store
from omnix.task_service import TaskService
from omnix.tools import ToolRegistry


def wait_for(service, job_id, state, timeout=10):
    observer = Store(service.store.path)
    try:
        end = time.monotonic() + timeout
        while True:
            row = observer.job(job_id)
            if row and row["state"] == state:
                return row
            if time.monotonic() >= end:
                raise AssertionError(row)
            time.sleep(.05)
    finally:
        observer.db.close()


def test_persistent_one_shot_schedule_and_restart_recovery(tmp_path: Path):
    db = tmp_path / "tasks.sqlite3"
    service = TaskService(Settings(), Store(db), tmp_path, executor=lambda prompt, session: "done:" + prompt)
    schedule = service.schedule("scheduled work", "every 0.1s")
    end = time.time() + 4
    job = None
    while time.time() < end and job is None:
        rows = service.store.jobs()
        if rows:
            job = wait_for(service, rows[0]["id"], "completed")
        else:
            time.sleep(.05)
    assert job is not None
    assert job["result"] == "done:scheduled work"
    assert service.store.db.execute("SELECT enabled FROM schedules WHERE id=?", (schedule,)).fetchone()[0] == 1
    service.close()
    recovered = TaskService(Settings(), Store(db), tmp_path, executor=lambda prompt, session: "recovered")
    orphan = recovered.store.create_job("after crash")
    recovered.store.db.execute("UPDATE jobs SET state='running' WHERE id=?", (orphan,)); recovered.store.db.commit()
    recovered.close()
    after = TaskService(Settings(), Store(db), tmp_path, executor=lambda prompt, session: "recovered")
    assert after.store.job(orphan)["state"] == "queued"
    after.close()


def test_delegated_children_are_isolated_and_aggregate_status(tmp_path: Path):
    db = tmp_path / "delegation.sqlite3"
    service = TaskService(Settings(), Store(db), tmp_path, executor=lambda prompt, session: prompt.upper(), max_workers=2)
    parent = service.enqueue("parent")
    children = service.delegate(parent, [{"role": "researcher", "prompt": "one"}, {"role": "tester", "prompt": "two"}])
    assert all(wait_for(service, child, "completed")["result"] in {"ONE", "TWO"} for child in children)
    rows = service.store.delegations(parent)
    assert {row["role"] for row in rows} == {"researcher", "tester"}
    assert {row["state"] for row in rows} == {"completed"}
    service.close()


def test_cancellation_is_persistent(tmp_path: Path):
    db = tmp_path / "cancel.sqlite3"
    service = TaskService(Settings(), Store(db), tmp_path, executor=lambda prompt, session: "never")
    job = service.enqueue("cancel me")
    service.cancel(job)
    assert service.store.job(job)["state"] == "cancelled"
    service.close()


def test_durable_worker_reclaims_queue_after_host_restart(tmp_path: Path):
    db = tmp_path / "worker.sqlite3"
    first = TaskService(Settings(), Store(db), tmp_path, executor=lambda prompt, session: "host-one")
    job = first.store.create_job("queued work")
    first.close()
    second = TaskService(Settings(), Store(db), tmp_path, executor=lambda prompt, session: "host-two")
    second.run_worker_forever(idle_seconds=.2)
    assert Store(db).job(job)["state"] == "completed"
    assert Store(db).job(job)["result"] == "host-two"


def test_delegation_inherits_policy_and_aggregates_results(tmp_path: Path):
    db = tmp_path / "aggregate.sqlite3"
    settings = Settings(mode="FREE", allow_paid=False, max_cost_usd=0.0, tool_policy="deny")
    service = TaskService(settings, Store(db), tmp_path, executor=lambda prompt, session: "tool-result:" + prompt)
    parent = service.store.create_job("parent", policy={"mode": "FREE", "allow_paid": False, "max_cost_usd": 0.0, "tool_policy": "deny"})
    service.store.db.execute("UPDATE jobs SET state='running' WHERE id=?", (parent,)); service.store.db.commit()
    children = service.delegate(parent, [{"role": "research", "prompt": "approved read"}, {"role": "verify", "prompt": "verify"}])
    for child in children:
        wait_for(service, child, "completed")
        assert service.store.job(child)["policy_json"] == '{"allow_paid": false, "max_cost_usd": 0.0, "mode": "FREE", "tool_policy": "deny"}'
    result = service.aggregate(parent)
    assert result["state"] == "completed"
    assert service.store.job(parent)["state"] == "completed"
    service.close()


def test_end_to_end_schedule_background_delegate_tool_restart(tmp_path: Path):
    db = tmp_path / "e2e.sqlite3"
    workspace = tmp_path / "workspace"; workspace.mkdir()
    tools = ToolRegistry(workspace, approver=lambda _: True)

    def execute(prompt, session):
        if prompt == "approved tool":
            return tools.call("write_file", {"path": "result.txt", "content": "completed"})
        return "delegated:" + prompt

    service = TaskService(Settings(mode="FREE", allow_paid=False), Store(db), workspace, executor=execute)
    schedule = service.schedule("approved tool", "every 0.1s")
    end = time.time() + 4
    scheduled = None
    while time.time() < end and scheduled is None:
        rows = service.store.jobs()
        if rows:
            scheduled = wait_for(service, rows[0]["id"], "completed")
        else:
            time.sleep(.05)
    assert scheduled and (workspace / "result.txt").read_text() == "completed"
    parent = service.store.create_job("parent", policy={"mode": "FREE", "allow_paid": False, "max_cost_usd": 0.0, "tool_policy": "ask"})
    service.store.db.execute("UPDATE jobs SET state='running' WHERE id=?", (parent,)); service.store.db.commit()
    child = service.delegate(parent, [{"role": "specialist", "prompt": "analysis"}])[0]
    wait_for(service, child, "completed")
    assert service.aggregate(parent)["state"] == "completed"
    service.close()
    restarted = Store(db)
    assert restarted.job(parent)["state"] == "completed"
    assert restarted.delegations(parent)[0]["state"] == "completed"


def test_native_runtime_executes_delegated_child(monkeypatch, tmp_path: Path):
    db = tmp_path / "native-child.sqlite3"
    service = TaskService(Settings(mode="FREE", allow_paid=False, max_cost_usd=0.0), Store(db), tmp_path, max_workers=1)
    service._run_omnix_job = lambda row, cancel, job_id: ("native child verified", None)
    parent = service.store.create_job("parent", policy={"mode": "FREE", "allow_paid": False,
                                                         "max_cost_usd": 0.0, "tool_policy": "deny"})
    child = service.delegate(parent, [{"role": "specialist", "prompt": "child task"}])[0]
    assert wait_for(service, child, "completed")["result"] == "native child verified"
    assert service.store.delegations(parent)[0]["state"] == "completed"
    service.close()


def test_native_background_job_uses_same_runtime(monkeypatch, tmp_path: Path):
    service = TaskService(Settings(), Store(tmp_path / "native-job.sqlite3"), tmp_path, max_workers=1)
    service._run_omnix_job = lambda row, cancel, job_id: ("native result", None)
    job = service.enqueue("background task")
    assert wait_for(service, job, "completed")["result"] == "native result"
    service.close()


def test_job_worker_closes_its_connection(monkeypatch, tmp_path: Path):
    service = TaskService(Settings(), Store(tmp_path / "closed.sqlite3"), tmp_path, executor=lambda *_: "done")
    job = service.store.create_job("task")
    opened = []

    class TrackedStore(Store):
        def __init__(self, path):
            super().__init__(path)
            opened.append(self)

    monkeypatch.setattr("omnix.task_service.Store", TrackedStore)
    service._run(job)
    assert service.store.job(job)["state"] == "completed"
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].db.execute("SELECT 1")
    service.close()


def test_workflow_cancellation_removes_pending_approval(tmp_path: Path):
    from omnix.desktop_server import ApprovalManager
    manager = ApprovalManager()
    store = Store(tmp_path / "workflow-cancel.sqlite3")
    workflow = store.save_workflow("approval", {"nodes": [{"id": "confirm", "action": "approval"}]})
    service = TaskService(Settings(), store, tmp_path,
                          cancellable_approver=lambda action, event: manager.request(action, timeout=5, cancel_event=event))
    run_id = service.start_workflow(workflow)
    try:
        deadline = time.monotonic() + 3
        while not manager.list() and time.monotonic() < deadline:
            time.sleep(.01)
        assert manager.list()
        service.cancel_workflow(run_id)
        deadline = time.monotonic() + 2
        while manager.list() and time.monotonic() < deadline:
            time.sleep(.01)
        assert manager.list() == []
        assert store.workflow_runs(workflow)[0]["state"] == "cancelled"
    finally:
        service.close()


def test_shutdown_cancels_pending_workflow_approval(tmp_path: Path):
    from omnix.desktop_server import ApprovalManager
    manager = ApprovalManager()
    store = Store(tmp_path / "workflow-shutdown.sqlite3")
    workflow = store.save_workflow("approval", {"nodes": [{"id": "confirm", "action": "approval"}]})
    service = TaskService(Settings(), store, tmp_path,
                          cancellable_approver=lambda action, event: manager.request(action, timeout=5, cancel_event=event))
    service.start_workflow(workflow)
    try:
        deadline = time.monotonic() + 3
        while not manager.list() and time.monotonic() < deadline:
            time.sleep(.01)
        assert manager.list()
    finally:
        started = time.monotonic()
        service.close()
    assert time.monotonic() - started < 2
    assert manager.list() == []
    assert store.workflow_runs(workflow)[0]["state"] == "cancelled"


def test_native_queued_job_cancellation_reaches_terminal_state(tmp_path: Path):
    service = TaskService(Settings(), Store(tmp_path / "native-cancel.sqlite3"), tmp_path, max_workers=1)
    job = service.enqueue("cancel before claim")
    service.cancel(job)
    assert wait_for(service, job, "cancelled")["state"] == "cancelled"
    service.close()




def test_saved_workflow_executes_through_task_service_and_records_run(monkeypatch, tmp_path: Path):
    class FakeRuntime:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, prompt, session):
            return "completed:" + prompt, "session"

    monkeypatch.setattr("omnix.task_service.AgentRuntime", FakeRuntime)
    db = tmp_path / "workflow.sqlite3"
    store = Store(db)
    workflow_id = store.save_workflow("fixture", {"nodes": [{"id": "step-1", "action": "agent", "prompt": "hello"}]})
    service = TaskService(Settings(mode="FREE", allow_paid=False, max_cost_usd=0.0), store, tmp_path, approver=lambda _: True)
    result = service.run_workflow(workflow_id)
    assert result["state"] == "completed"
    assert result["result"]["step-1"] == "completed:hello"
    assert store.workflow_runs(workflow_id)[0]["state"] == "completed"
    service.close()

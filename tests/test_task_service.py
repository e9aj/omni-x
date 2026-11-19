import time
from pathlib import Path

from omnix.config import Settings
from omnix.hermes_primary import HermesPrimaryError
from omnix.store import Store
from omnix.task_service import TaskService
from omnix.tools import ToolRegistry


def wait_for(service, job_id, state, timeout=4):
    end = time.time() + timeout
    while time.time() < end:
        row = Store(service.store.path).job(job_id)
        if row and row["state"] == state:
            return row
        time.sleep(.05)
    raise AssertionError(Store(service.store.path).job(job_id))


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


def test_hermes_runtime_selector_executes_child_and_records_usage(monkeypatch, tmp_path: Path):
    db = tmp_path / "hermes-child.sqlite3"
    settings = Settings(runtime="hermes", mode="FREE", provider="omniroute",
                        model="auto/best-free", base_url="http://127.0.0.1:20128/v1",
                        allow_paid=False, max_cost_usd=0.0)

    def fake_hermes(settings, prompt, *, timeout, cancel_event=None):
        assert settings.mode == "FREE"
        assert settings.allow_paid is False
        assert settings.max_cost_usd == 0.0
        assert cancel_event is not None
        return {"answer": "Hermes child verified", "model": settings.model,
                "engine": "hermes-aiaagent", "usage": {
                    "provider": "omniroute", "input_tokens": 4,
                    "output_tokens": 3, "estimated_cost_usd": 0.0}}

    monkeypatch.setattr("omnix.task_service.run_hermes_primary_probe", fake_hermes)
    service = TaskService(settings, Store(db), tmp_path, max_workers=1)
    parent = service.store.create_job("parent", policy={"mode": "FREE", "allow_paid": False,
                                                         "max_cost_usd": 0.0, "tool_policy": "deny"})
    child = service.delegate(parent, [{"role": "specialist", "prompt": "child task"}])[0]
    row = wait_for(service, child, "completed")
    assert row["result"] == "Hermes child verified"
    assert service.store.db.execute("SELECT COUNT(*) FROM usage WHERE task_id=?", (child,)).fetchone()[0] == 1
    assert service.store.db.execute("SELECT detail FROM events WHERE task_id=? AND kind='runtime_selected'", (child,)).fetchone()[0] == "hermes-aiaagent"
    assert service.store.delegations(parent)[0]["state"] == "completed"
    service.close()


def test_auto_runtime_records_hermes_failure_before_fallback(monkeypatch, tmp_path: Path):
    db = tmp_path / "hermes-fallback.sqlite3"
    settings = Settings(runtime="auto", mode="FREE", provider="omniroute",
                        model="auto/best-free", base_url="http://127.0.0.1:20128/v1",
                        allow_paid=False, max_cost_usd=0.0)
    monkeypatch.setattr("omnix.task_service.run_hermes_primary_probe",
                        lambda *args, **kwargs: (_ for _ in ()).throw(HermesPrimaryError("route unavailable")))
    service = TaskService(settings, Store(db), tmp_path, max_workers=1)
    service._run_omnix_job = lambda row, cancel, job_id: ("fallback result", None)
    job = service.enqueue("fallback task")
    assert wait_for(service, job, "completed")["result"] == "fallback result"
    assert "route unavailable" in service.store.db.execute("SELECT detail FROM events WHERE task_id=? AND kind='runtime_fallback'", (job,)).fetchone()[0]
    service.close()


def test_hermes_child_cancellation_reaches_terminal_state(monkeypatch, tmp_path: Path):
    db = tmp_path / "hermes-cancel.sqlite3"
    settings = Settings(runtime="hermes", mode="FREE", provider="omniroute",
                        model="auto/best-free", base_url="http://127.0.0.1:20128/v1",
                        allow_paid=False, max_cost_usd=0.0)

    def hanging_hermes(settings, prompt, *, timeout, cancel_event=None):
        while cancel_event is not None and not cancel_event.is_set():
            time.sleep(.01)
        raise HermesPrimaryError("Task cancelled")

    monkeypatch.setattr("omnix.task_service.run_hermes_primary_probe", hanging_hermes)
    service = TaskService(settings, Store(db), tmp_path, max_workers=1)
    job = service.enqueue("cancel Hermes child")
    deadline = time.time() + 2
    while time.time() < deadline and service.store.job(job)["state"] == "queued":
        time.sleep(.01)
    service.cancel(job)
    assert wait_for(service, job, "cancelled")["error"] in {"cancelled by user", "Task cancelled"}
    service.close()


def test_auto_selector_never_admits_non_free_policy(monkeypatch, tmp_path: Path):
    db = tmp_path / "hermes-paid-block.sqlite3"
    settings = Settings(runtime="auto", mode="SMART", provider="omniroute",
                        model="auto/best-free", allow_paid=False, max_cost_usd=0.0)
    called = []
    monkeypatch.setattr("omnix.task_service.run_hermes_primary_probe",
                        lambda *args, **kwargs: called.append(True))
    service = TaskService(settings, Store(db), tmp_path, max_workers=1)
    service._run_omnix_job = lambda row, cancel, job_id: ("safe fallback", None)
    job = service.enqueue("must not use Hermes")
    assert wait_for(service, job, "completed")["result"] == "safe fallback"
    assert called == []
    service.close()

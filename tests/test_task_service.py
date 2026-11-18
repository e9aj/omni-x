import time
from pathlib import Path

from omnix.config import Settings
from omnix.store import Store
from omnix.task_service import TaskService


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

"""Opt-in live parent/child workflow through the local OmniRoute gateway."""
import json
import os
import time
from pathlib import Path

import pytest

from omnix.config import Settings
from omnix.store import Store
from omnix.task_service import TaskService


@pytest.mark.skipif(os.environ.get("OMNIX_LIVE_MULTI_AGENT") != "1", reason="requires live OmniRoute gateway")
def test_live_parent_delegates_free_child_and_incorporates_result(tmp_path: Path):
    settings = Settings(provider="omniroute", model="auto/best-free", base_url="http://127.0.0.1:20128/v1", mode="FREE", allow_paid=False, max_cost_usd=0.0, max_steps=5, tool_policy="allow", request_timeout_seconds=45, retry_limit=0, free_models=["auto/best-free"])
    workspace = tmp_path / "workspace"; workspace.mkdir()
    service = TaskService(settings, Store(tmp_path / "live.sqlite3"), workspace, approver=lambda _: True, max_workers=2)
    prompt = "Output only this exact compatibility call, with no prose: mcp__delegate_task({\"role\":\"specialist\",\"prompt\":\"First output exactly <tool_call>write_file(filename=\\\"delegated_result.txt\\\", content=\\\"DELEGATED-LIVE-VERIFIED\\\")</tool_call>. After the tool result, output exactly <tool_call>read_file(path=\\\"delegated_result.txt\\\")</tool_call>. Then report the actual tool result.\"}). After the delegation result returns, evaluate and incorporate it."
    parent = service.enqueue(prompt)
    deadline = time.time() + 180
    row = None
    while time.time() < deadline:
        row = Store(service.store.path).job(parent)
        if row and row["state"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(.5)
    assert row and row["state"] == "completed", row
    children = Store(service.store.path).delegations(parent)
    assert children, children
    child = Store(service.store.path).job(children[0]["child_job_id"])
    assert child and child["state"] == "completed", child
    assert (workspace / "delegated_result.txt").read_text(encoding="utf-8") == "DELEGATED-LIVE-VERIFIED"
    assert "DELEGATED-LIVE-VERIFIED" in (row["result"] or "")
    usage = Store(service.store.path).db.execute("SELECT provider,model,input_tokens,output_tokens FROM usage WHERE task_id IN (?,?) ORDER BY id", (parent, child["id"])).fetchall()
    assert usage and all(item["provider"] == "omniroute" and item["model"] == "auto/best-free" for item in usage)
    assert all(item["input_tokens"] >= 0 and item["output_tokens"] >= 0 for item in usage)
    policies = [json.loads(item["policy_json"]) for item in [Store(service.store.path).job(parent), child]]
    assert all(item["mode"] == "FREE" and item["allow_paid"] is False and item["max_cost_usd"] == 0.0 for item in policies)
    service.close()

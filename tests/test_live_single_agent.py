import os
import time
from pathlib import Path

import pytest

from omnix.config import Settings
from omnix.runtime import AgentRuntime
from omnix.store import Store


@pytest.mark.skipif(os.environ.get("OMNIX_LIVE_SINGLE_AGENT") != "1", reason="requires live OmniRoute gateway")
def test_live_single_agent_writes_and_reads_one_file(tmp_path: Path):
    settings = Settings(provider="omniroute", model="auto/best-free", base_url="http://127.0.0.1:20128/v1", mode="FREE", allow_paid=False, max_cost_usd=0.0, max_steps=4, tool_policy="allow", request_timeout_seconds=45, retry_limit=0, free_models=["auto/best-free"])
    workspace = tmp_path / "workspace"; workspace.mkdir()
    runtime = AgentRuntime(settings, Store(tmp_path / "live.sqlite3"), workspace, approver=lambda _: True)
    answer, session = runtime.run("Output only exact compatibility calls to write_file then read_file. Create verified.txt with exactly SINGLE-LIVE-VERIFIED and verify its actual content.")
    assert (workspace / "verified.txt").read_text(encoding="utf-8") == "SINGLE-LIVE-VERIFIED"
    task = Store(tmp_path / "live.sqlite3").db.execute("SELECT state FROM tasks ORDER BY created DESC LIMIT 1").fetchone()
    usage = Store(tmp_path / "live.sqlite3").db.execute("SELECT provider,model,input_tokens,output_tokens FROM usage ORDER BY id").fetchall()
    assert task["state"] == "completed" and usage
    assert all(row["provider"] == "omniroute" and row["model"] == "auto/best-free" for row in usage)

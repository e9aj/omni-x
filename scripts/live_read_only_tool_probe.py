"""Run one bounded, real read-only OMNI-X tool probe."""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

from omnix.config import load_settings
from omnix.runtime import AgentRuntime
from omnix.store import Store


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="omnix-readonly-") as raw:
        root = Path(raw)
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "probe.txt").write_text("read-only probe", encoding="utf-8")
        settings = replace(load_settings(), provider="omniroute", model="auto/best-free", mode="FREE", allow_paid=False, max_cost_usd=0.0, max_steps=4, request_timeout_seconds=35, retry_limit=0, free_models=["auto/best-free"])
        store = Store(root / "state.sqlite3")
        runtime = AgentRuntime(settings, store, workspace, approver=lambda _: True)
        answer, _ = runtime.run("Use the list_directory tool on the current workspace. Do not narrate an intended call. Return the actual directory listing after the tool result.")
        events = [dict(row) for row in store.db.execute("SELECT kind,detail FROM events ORDER BY id")]
        usage = [dict(row) for row in store.db.execute("SELECT provider,model,input_tokens,output_tokens FROM usage ORDER BY id")]
        print(json.dumps({"answer": answer, "events": events, "tool_result_events": [row for row in events if row["kind"] == "tool_result"], "retry_events": [row for row in events if row["kind"] == "tool_call_retry"], "usage": usage}, sort_keys=True))
        verified = any(row["kind"] == "tool_result" for row in events)
        store.db.close()
        return 0 if verified else 2


if __name__ == "__main__":
    raise SystemExit(main())

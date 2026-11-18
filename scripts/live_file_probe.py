"""Run one bounded live write/read task and print sanitized evidence."""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

from omnix.config import load_settings
from omnix.runtime import AgentRuntime
from omnix.store import Store


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="omnix-file-") as raw:
        root = Path(raw)
        workspace = root / "workspace"
        workspace.mkdir()
        settings = replace(load_settings(), provider="omniroute", model="auto/best-free", mode="FREE", allow_paid=False, max_cost_usd=0.0, max_steps=5, request_timeout_seconds=35, retry_limit=0, free_models=["auto/best-free"])
        store = Store(root / "state.sqlite3")
        runtime = AgentRuntime(settings, store, workspace, approver=lambda _: True)
        answer, session = runtime.run("Create verified.txt with exactly SINGLE-LIVE-VERIFIED using the write_file tool, then use read_file to verify its actual content. Do not claim success without tool results.")
        events = [dict(row) for row in store.db.execute("SELECT kind,detail FROM events ORDER BY id")]
        messages = [dict(row) for row in store.db.execute("SELECT role,content FROM messages WHERE session_id=? ORDER BY id", (session,))]
        print(json.dumps({"answer": answer, "exists": (workspace / "verified.txt").exists(), "content": (workspace / "verified.txt").read_text(encoding="utf-8") if (workspace / "verified.txt").exists() else None, "events": events, "assistant_messages": [row["content"] for row in messages if row["role"] == "assistant"]}, sort_keys=True))
        store.db.close()
        return 0 if (workspace / "verified.txt").exists() and (workspace / "verified.txt").read_text(encoding="utf-8") == "SINGLE-LIVE-VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())

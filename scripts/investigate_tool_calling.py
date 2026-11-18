"""Compare a minimal native tool request at OmniRoute and ModelClient."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import replace

from omnix.config import load_settings
from omnix.providers import ModelClient
from omnix.secrets import get_secret


MODEL = "auto/best-free"
MESSAGES = [{"role": "user", "content": "Call the read-only list_directory tool for path . Do not describe it; emit a tool call."}]
TOOLS = [{
    "type": "function",
    "function": {
        "name": "list_directory",
        "description": "Read-only directory listing",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
}]


def fields(payload: dict) -> dict:
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return {
        "model": payload.get("model"),
        "finish_reason": choice.get("finish_reason"),
        "content": message.get("content"),
        "tool_calls": message.get("tool_calls"),
        "usage": payload.get("usage"),
    }


def main() -> int:
    settings = replace(load_settings(), provider="omniroute", model=MODEL, mode="FREE", allow_paid=False)
    base = (settings.base_url or "http://127.0.0.1:20128/v1").rstrip("/")
    body = {"model": MODEL, "messages": MESSAGES, "tools": TOOLS, "tool_choice": "required"}
    request = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {get_secret('OMNIROUTE_API_KEY')}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=35) as response:
        direct = json.loads(response.read())
    wrapped = ModelClient(settings).complete(MESSAGES, TOOLS)
    print("DIRECT_RAW_FIELDS=" + json.dumps(fields(direct), ensure_ascii=False, sort_keys=True))
    print("OMNIX_CLIENT_FIELDS=" + json.dumps(fields(wrapped), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

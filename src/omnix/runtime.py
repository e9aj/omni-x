from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable

from .config import Settings
from .providers import ProviderError
from .routing import Router, Route
from .store import Store
from .tools import ToolRegistry
from .skills import discover_skills, relevant_instructions
from .optimize import compress_terminal_output


SYSTEM = "You are OMNI-X, a careful autonomous agent. Use tools only when useful. Never claim an action succeeded unless the tool result proves it. Ask for approval before sensitive actions. Keep answers concise and explain limitations."


class AgentRuntime:
    def __init__(self, settings: Settings, store: Store | None = None, workspace: Path | None = None, approver: Callable[[str], bool] | None = None):
        self.store = store or Store()
        self.router = Router(settings)
        self.tools = ToolRegistry(workspace, approver)
        self.max_steps = settings.max_steps
        self.workspace = workspace or Path.cwd()
        self.cancel_event = threading.Event()
        self.timeout_seconds = settings.request_timeout_seconds * max(1, settings.max_steps)

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self, prompt: str, session_id: str | None = None, on_text: Callable[[str], None] | None = None) -> tuple[str, str]:
        session_id = session_id or self.store.new_session(prompt[:80])
        task_id = self.store.start_task(session_id)
        deadline = time.monotonic() + self.timeout_seconds
        if not self.store.messages(session_id):
            skills = relevant_instructions(discover_skills(self.workspace), prompt)
            self.store.add_message(session_id, "system", SYSTEM + (f"\n\n{skills}" if skills else ""))
        self.store.add_message(session_id, "user", prompt)
        messages = self.store.messages(session_id)
        try:
            for step in range(self.max_steps):
                if self.cancel_event.is_set():
                    raise RuntimeError("Task cancelled")
                if time.monotonic() > deadline:
                    raise RuntimeError("Task timeout exceeded")
                self.store.event(task_id, "step_started", str(step + 1))
                response, route = self.router.complete(messages, self.tools.schemas(), lambda r, u, latency: self._record_usage(task_id, r, u, latency))
                message = response["choices"][0]["message"]
                text = message.get("content") or ""
                calls = message.get("tool_calls") or []
                if text:
                    self.store.add_message(session_id, "assistant", text)
                    if on_text:
                        on_text(text)
                if not calls:
                    self.store.update_task(task_id, "completed")
                    self.store.event(task_id, "completed", route.provider)
                    return text, session_id
                messages.append({"role": "assistant", "content": text, "tool_calls": calls})
                for call in calls:
                    try:
                        args = json.loads(call["function"].get("arguments") or "{}")
                    except (KeyError, TypeError, json.JSONDecodeError) as exc:
                        raise RuntimeError(f"Invalid tool call from model: {exc}") from exc
                    name = call["function"].get("name")
                    raw_result = self.tools.call(name, args)
                    # OmniRoute may already apply its RTK → Caveman pipeline. Avoid stacking
                    # OMNI-X compression on top of a gateway-compressed tool result.
                    result = raw_result if route.provider == "omniroute" else compress_terminal_output(raw_result)
                    messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
                    self.store.add_message(session_id, "tool", f"{name}: {result}")
                    self.store.event(task_id, "tool_result", name)
            raise RuntimeError(f"Agent stopped after {self.max_steps} steps without completing")
        except Exception as exc:
            self.store.update_task(task_id, "cancelled" if str(exc) == "Task cancelled" else "failed", str(exc))
            self.store.event(task_id, "failed", str(exc))
            raise

    def _record_usage(self, task_id: str, route: Route, usage: dict, latency_ms: float) -> None:
        self.store.record_usage(task_id, route.provider, route.model, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)), 0.0)
        self.store.event(task_id, "provider_call", f"{route.provider}/{route.model} latency_ms={latency_ms:.1f}")

from __future__ import annotations

import ast
import json
import re
import threading
from pathlib import Path
from typing import Callable

from .config import Settings
from .routing import Router, Route
from .store import Store
from .tools import ToolRegistry
from .skills import discover_skills, relevant_instructions
from .hermes_bridge import TOOL_CALL_CONTRACT
from .hermes_backend import HermesExecutionBackend


SYSTEM = "You are OMNI-X, a careful autonomous agent. Use tools only when useful. Never claim an action succeeded unless the tool result proves it. Ask for approval before sensitive actions. Keep answers concise and explain limitations. When a task asks for a specialist, invoke the supplied delegate_task function immediately; do not merely narrate that you will delegate. Use the supplied function tools; if the provider cannot emit standard tool calls, follow this Hermes-compatible contract: " + TOOL_CALL_CONTRACT + " Never invent a tool result."


_PSEUDO_TOOLS = {
    "read_file": "read_file",
    "list_workspace_files": "list_directory",
    "list_directory": "list_directory",
    "search_text": "search_text",
    "write_file": "write_file",
    "run_command": "run_command",
    "delegate_task": "delegate_task",
}


class AgentRuntime:
    def __init__(self, settings: Settings, store: Store | None = None, workspace: Path | None = None, approver: Callable[[str], bool] | None = None, cancel_event: threading.Event | None = None, delegate_handler=None):
        self.settings = settings
        self.store = store or Store()
        self.workspace = Path(workspace or Path.cwd()).resolve()
        try:
            self.router = Router(settings, self.store.provider_health, self.store.record_provider_health, self.store.record_provider_failure, self.store.model_health)
        except TypeError:
            # Preserve the small Router seam used by embedders and tests written
            # against the original one-argument constructor.
            self.router = Router(settings)
        self.cancel_event = cancel_event or threading.Event()
        self.tools = ToolRegistry(self.workspace, approver, self.cancel_event, delegate_handler)
        self.max_steps = settings.max_steps
        self.timeout_seconds = settings.request_timeout_seconds * max(1, settings.max_steps)

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self, prompt: str, session_id: str | None = None, on_text: Callable[[str], None] | None = None) -> tuple[str, str]:
        session_id = session_id or self.store.new_session(prompt[:80])
        task_id = self.store.start_task(session_id)
        self.last_task_id = task_id
        if not self.store.messages(session_id):
            skills = relevant_instructions(discover_skills(self.workspace), prompt)
            self.store.add_message(session_id, "system", SYSTEM + (f"\n\n{skills}" if skills else ""))
        self.store.add_message(session_id, "user", prompt)
        messages = self.store.messages(session_id)
        try:
            backend = HermesExecutionBackend(
                router=self.router,
                tools=self.tools,
                store=self.store,
                max_steps=self.max_steps,
                cancel_event=self.cancel_event,
                timeout_seconds=self.timeout_seconds,
                pseudo_tool_calls=self._pseudo_tool_calls,
                record_usage=self._record_usage,
                record_tool_result=lambda route, success: self._record_tool_result(self.settings, route, success),
            )
            return backend.execute(task_id=task_id, session_id=session_id, messages=messages, on_text=on_text), session_id
        except Exception as exc:
            self.store.update_task(task_id, "cancelled" if str(exc) == "Task cancelled" else "failed", str(exc))
            self.store.event(task_id, "failed", str(exc))
            raise

    def _record_usage(self, task_id: str, route: Route, usage: dict, latency_ms: float) -> None:
        self.store.record_usage(task_id, route.provider, route.model, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)), 0.0)
        self.store.event(task_id, "provider_call", f"{route.provider}/{route.model} latency_ms={latency_ms:.1f}")

    def _record_tool_result(self, settings: Settings, route: Route, success: bool) -> None:
        # Health is keyed by the configured route alias; the actual upstream
        # model remains recorded separately in usage rows.
        self.store.record_model_tool_result(settings.model, success)

    @staticmethod
    def _pseudo_tool_calls(text: str) -> list[dict]:
        match = re.fullmatch(r"\s*mcp__([a-z_]+)\((.*)\)\s*", text or "", re.DOTALL)
        if match:
            tool_key = match.group(1)
            raw_args = match.group(2).strip()
        else:
            formatted = re.search(r"tool_call:\s*mcp__([a-z_]+)__([a-z_]+)\s*\n(?:tool_params:\s*\n)?(?P<params>.*)", text or "", re.DOTALL)
            if not formatted:
                return []
            tool_key = formatted.group(2)
            raw_args = formatted.group("params")
            if tool_key not in _PSEUDO_TOOLS:
                return []
            args = {}
            for line in raw_args.splitlines():
                item = re.match(r"\s*([a-z_]+):\s*(.*)\s*$", line)
                if not item:
                    continue
                value = item.group(2).strip()
                try:
                    args[item.group(1)] = ast.literal_eval(value) if value[:1] in {"'", '"'} else value
                except (SyntaxError, ValueError):
                    return []
            return [{"id": "pseudo-tool", "type": "function", "function": {"name": _PSEUDO_TOOLS[tool_key], "arguments": json.dumps(args)}}]
        if tool_key not in _PSEUDO_TOOLS:
            return []
        if not raw_args:
            args = {}
        else:
            try:
                if "=" in raw_args:
                    expression = ast.parse(f"f({raw_args})", mode="eval").body
                    if not isinstance(expression, ast.Call) or expression.args:
                        return []
                    args = {keyword.arg: ast.literal_eval(keyword.value) for keyword in expression.keywords if keyword.arg}
                else:
                    args = json.loads(raw_args)
            except (SyntaxError, ValueError, json.JSONDecodeError):
                return []
            if not isinstance(args, dict):
                return []
        return [{"id": "pseudo-tool", "type": "function", "function": {"name": _PSEUDO_TOOLS[tool_key], "arguments": json.dumps(args)}}]

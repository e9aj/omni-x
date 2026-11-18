from __future__ import annotations

import json
import ast
import re
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


SYSTEM = "You are OMNI-X, a careful autonomous agent. Use tools only when useful. Never claim an action succeeded unless the tool result proves it. Ask for approval before sensitive actions. Keep answers concise and explain limitations. Use the supplied function tools; if the provider cannot emit standard tool calls, use only these exact compatibility forms: mcp__read_file(...), mcp__list_workspace_files(...), mcp__search_text(...), mcp__write_file(...), mcp__run_command(...). Never invent a tool result."


_PSEUDO_TOOLS = {
    "read_file": "read_file",
    "list_workspace_files": "list_directory",
    "list_directory": "list_directory",
    "search_text": "search_text",
    "write_file": "write_file",
    "run_command": "run_command",
}


class AgentRuntime:
    def __init__(self, settings: Settings, store: Store | None = None, workspace: Path | None = None, approver: Callable[[str], bool] | None = None):
        self.store = store or Store()
        self.router = Router(settings)
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.tools = ToolRegistry(self.workspace, approver)
        self.max_steps = settings.max_steps
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
                calls = message.get("tool_calls") or self._pseudo_tool_calls(text)
                if calls:
                    text = ""
                if text:
                    self.store.add_message(session_id, "assistant", text)
                    if on_text:
                        on_text(text)
                if not calls:
                    # Some OpenAI-compatible free models describe the next action
                    # instead of emitting a function call. Give them one corrective
                    # turn, but never treat the narrative as completed work.
                    if not any(item.get("role") == "tool" for item in messages) and step < self.max_steps - 1 and self._looks_actionable(text):
                        messages.append({"role": "assistant", "content": text})
                        messages.append({"role": "user", "content": "No tool was executed. Use one exact compatibility tool call now, with valid arguments. Do not describe the action first."})
                        self.store.event(task_id, "tool_call_retry", "provider returned narrative without an executable call")
                        continue
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

    @staticmethod
    def _looks_actionable(text: str) -> bool:
        lowered = (text or "").lower()
        return any(marker in lowered for marker in ("i'll create", "i will create", "create the file", "run the test", "use the tool", "tool_call", "tool_params"))

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

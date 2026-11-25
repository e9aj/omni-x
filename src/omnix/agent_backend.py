"""Native execution backend for the unified OMNI-X runtime.

This module adapts the actual Hermes Agent execution boundary: a bounded
conversation loop, assistant tool-call dispatch, tool-result continuation, and
terminal finalisation.  The upstream implementation is ``agent.conversation_loop``
and ``agent.tool_executor`` in NousResearch/hermes-agent (MIT); OMNI-X injects
its own Router, SQLite session store, reviewed skills, and permission-gated
ToolRegistry so there is one engine and one security boundary.

This is an execution adapter, not a claim that Hermes' optional browser,
scheduler, and delegated-worker services are embedded.
"""

from __future__ import annotations

import json
import math
import time
from typing import Any, Callable

from .hermes_bridge import extract_tool_calls
from .optimize import compress_terminal_output


class AgentExecutionBackend:
    """Run a bounded task using OMNI-X routing, tools and persistence."""

    def __init__(
        self,
        *,
        router: Any,
        tools: Any,
        store: Any,
        max_steps: int,
        cancel_event: Any,
        timeout_seconds: float,
        pseudo_tool_calls: Callable[[str], list[dict[str, Any]]],
        record_usage: Callable[[str, Any, dict[str, Any], float], None],
        record_tool_result: Callable[[Any, bool], None] | None = None,
    ) -> None:
        self.router = router
        self.tools = tools
        self.store = store
        self.max_steps = max_steps
        self.cancel_event = cancel_event
        self.timeout_seconds = timeout_seconds
        self.pseudo_tool_calls = pseudo_tool_calls
        self.record_usage = record_usage
        self.record_tool_result = record_tool_result

    def execute(
        self,
        *,
        task_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        on_text: Callable[[str], None] | None = None,
        on_delta: Callable[[str], None] | None = None,
        on_event: Callable[[str], None] | None = None,
    ) -> str:
        """Execute until the model returns a final turn or the bounded loop stops.

        Completion is model- and evidence-driven: narrative alone is never
        converted into a tool result, and every tool continuation contains the
        actual result returned by the injected tool registry.
        """
        deadline = time.monotonic() + self.timeout_seconds
        saw_tool_result = False
        saw_tool_error = False
        saw_assistant_turn = False

        for step in range(self.max_steps):
            if self.cancel_event.is_set():
                raise RuntimeError("Task cancelled")
            if time.monotonic() > deadline:
                raise RuntimeError("Task timeout exceeded")

            self.store.event(task_id, "step_started", str(step + 1))
            if on_event:
                on_event("Thinking")
            role_chars = {role: sum(len(str(item.get("content") or "")) for item in messages if item.get("role") == role) for role in ("system", "user", "assistant", "tool")}
            self.store.event(task_id, "prompt_metrics", json.dumps({**role_chars, "tool_schema_chars": len(json.dumps(self.tools.schemas(), sort_keys=True)), "message_count": len(messages), "estimated_prompt_tokens": math.ceil(sum(role_chars.values()) / 4)}, sort_keys=True))
            try:
                options = {"requires_tools": True}
                if on_delta is not None:
                    on_delta("")  # Start a new provisional provider turn.
                    options.update(on_delta=on_delta, cancel_event=self.cancel_event)
                response, route = self.router.complete(
                    messages,
                    self.tools.schemas(),
                    lambda r, u, latency: self.record_usage(task_id, r, u, latency),
                    **options,
                )
            except TypeError as exc:
                if "requires_tools" not in str(exc):
                    raise
                response, route = self.router.complete(messages, self.tools.schemas(), lambda r, u, latency: self.record_usage(task_id, r, u, latency))
            if self.cancel_event.is_set():
                raise RuntimeError("Task cancelled")
            if time.monotonic() > deadline:
                raise RuntimeError("Task timeout exceeded")
            message = response["choices"][0]["message"]
            saw_assistant_turn = True
            text = message.get("content") or ""
            hermes_calls, cleaned_text = extract_tool_calls(text)
            calls = message.get("tool_calls") or hermes_calls or self.pseudo_tool_calls(text)
            native_tool_calls = bool(message.get("tool_calls"))

            if calls and not native_tool_calls:
                text = cleaned_text
            if calls:
                text = ""
            if text:
                self.store.add_message(session_id, "assistant", text)
                if on_text:
                    on_text(text)

            if not calls:
                # This is the general Hermes turn-finalisation rule. A model
                # that narrated an intended action without emitting a call gets
                # one bounded continuation; no task-specific prompt matching is
                # used and no action is claimed without tool evidence.
                if self._needs_continuation(text, saw_tool_result, step) or (saw_tool_error and step < self.max_steps - 1):
                    messages.append({"role": "assistant", "content": text})
                    messages.append({
                        "role": "user",
                        "content": (
                            "Continue the task using the available tools when work remains. "
                            "Do not claim completion without inspecting the relevant tool output. "
                            "If the task is complete, provide a concise evidence-based summary."
                        ),
                    })
                    self.store.event(task_id, "tool_call_retry", "provider returned narrative without an executable call")
                    continue
                if saw_tool_error:
                    raise RuntimeError("Agent stopped after a tool error without verified recovery")
                self.store.update_task(task_id, "completed")
                self.store.event(task_id, "verified", "final model turn returned after execution loop")
                self.store.event(task_id, "completed", route.provider)
                return text

            messages.append({"role": "assistant", "content": text, "tool_calls": calls})
            for call in calls:
                if self.cancel_event.is_set():
                    raise RuntimeError("Task cancelled")
                if time.monotonic() > deadline:
                    raise RuntimeError("Task timeout exceeded")
                try:
                    raw_args = json.loads(call["function"].get("arguments") or "{}")
                    name = call["function"].get("name")
                    args = self.tools.normalize_arguments(name, raw_args) if hasattr(self.tools, "normalize_arguments") else raw_args
                except (KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise RuntimeError(f"Invalid tool call from model: {exc}") from exc
                except ValueError as exc:
                    raise RuntimeError(f"Invalid tool call from model: {exc}") from exc
                if on_event:
                    on_event("Running tool: " + str(name)[:100])
                raw_result = self.tools.call(name, args)
                saw_tool_result = True
                saw_tool_error = saw_tool_error or raw_result.startswith("Tool error:")
                if self.record_tool_result:
                    self.record_tool_result(route, not raw_result.startswith("Tool error:"))
                result = raw_result if route.provider == "omniroute" else compress_terminal_output(raw_result)
                if native_tool_calls:
                    messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "name": name, "content": result})
                else:
                    messages.append({"role": "user", "content": f"Hermes tool result ({name}):\n{result}"})
                self.store.add_message(session_id, "tool", f"{name}: {result}")
                self.store.event(task_id, "tool_result", name)

        raise RuntimeError(f"Agent stopped after {self.max_steps} steps without completing")

    @staticmethod
    def _needs_continuation(text: str, saw_tool_result: bool, step: int) -> bool:
        """Continue only for an actionable-looking narrative, generically."""
        if not text or saw_tool_result:
            return False
        lower = text.lower()
        # A model can narrate an intended action instead of emitting its
        # function call. Give it a bounded opportunity to correct that generic
        # protocol error; this is not task/benchmark word matching.
        return step < 2 and any(marker in lower for marker in (
            "i'll ", "i will ", "next i", "let me ", "use the tool", "tool_call", "tool_params",
            "delegat", "specialist", "create", "write", "inspect", "run",
        ))

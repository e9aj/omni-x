from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .config import Settings
from .providers import ModelClient
from .store import Store
from .tools import ToolRegistry
from .skills import discover_skills, relevant_instructions
from .optimize import compress_terminal_output


SYSTEM = "You are OMNI-X, a careful autonomous agent. Use tools only when useful. Never claim an action succeeded unless the tool result proves it. Ask for approval before sensitive actions. Keep answers concise and explain limitations."


class AgentRuntime:
    def __init__(self, settings: Settings, store: Store | None = None, workspace: Path | None = None, approver: Callable[[str], bool] | None = None):
        self.store = store or Store()
        self.client = ModelClient(settings)
        self.tools = ToolRegistry(workspace, approver)
        self.max_steps = settings.max_steps
        self.workspace = workspace or Path.cwd()

    def run(self, prompt: str, session_id: str | None = None, on_text: Callable[[str], None] | None = None) -> tuple[str, str]:
        session_id = session_id or self.store.new_session(prompt[:80])
        if not self.store.messages(session_id):
            skills = relevant_instructions(discover_skills(self.workspace), prompt)
            self.store.add_message(session_id, "system", SYSTEM + (f"\n\n{skills}" if skills else ""))
        self.store.add_message(session_id, "user", prompt)
        messages = self.store.messages(session_id)
        for _ in range(self.max_steps):
            response = self.client.complete(messages, self.tools.schemas())
            message = response["choices"][0]["message"]
            text = message.get("content") or ""
            calls = message.get("tool_calls") or []
            if text:
                self.store.add_message(session_id, "assistant", text)
                if on_text:
                    on_text(text)
            if not calls:
                return text, session_id
            messages.append({"role": "assistant", "content": text, "tool_calls": calls})
            for call in calls:
                args = json.loads(call["function"].get("arguments") or "{}")
                result = compress_terminal_output(self.tools.call(call["function"]["name"], args))
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
                self.store.add_message(session_id, "tool", f"{call['function']['name']}: {result}")
        raise RuntimeError(f"Agent stopped after {self.max_steps} steps without completing")

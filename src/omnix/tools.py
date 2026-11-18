from __future__ import annotations

import json
import os
import subprocess
import re
import threading
from pathlib import Path
from typing import Any, Callable

from .hermes_browser import HermesBrowserAdapter
from .process_control import terminate_process_tree, wait_owned_process


class PermissionDenied(RuntimeError):
    pass


class ToolRegistry:
    def __init__(self, workspace: Path | None = None, approver: Callable[[str], bool] | None = None, cancel_event=None, delegate_handler: Callable[..., str] | None = None):
        self.workspace = (workspace or Path.cwd()).resolve()
        self.approver = approver or (lambda _: False)
        self.cancel_event = cancel_event or threading.Event()
        self.delegate_handler = delegate_handler
        self._active: set[subprocess.Popen] = set()
        self._active_lock = threading.Lock()
        self.tools: dict[str, Callable[..., str]] = {"read_file": self.read_file, "list_directory": self.list_directory, "search_text": self.search_text, "write_file": self.write_file, "run_command": self.run_command}
        self.browser = HermesBrowserAdapter(approver=self.approver, cancel_event=self.cancel_event)
        if self.browser.available:
            self.tools["browser_exec"] = self.browser_exec
            self.tools["browser_shutdown"] = self.browser_shutdown
        if self.delegate_handler:
            self.tools["delegate_task"] = self.delegate_task

    def schemas(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": name, "description": getattr(fn, "description", "OMNI-X tool"), "parameters": getattr(fn, "parameters", {"type": "object", "properties": {}})}} for name, fn in self.tools.items()]

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in self.tools:
            return f"Tool error: unknown tool {name}"
        try:
            self._validate(name, arguments)
            return self.tools[name](**arguments)
        except (OSError, ValueError, TypeError, PermissionDenied, subprocess.SubprocessError) as exc:
            return f"Tool error: {exc}"

    def _validate(self, name: str, arguments: dict[str, Any]) -> None:
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be a JSON object")
        schema = getattr(self.tools[name], "parameters", {})
        properties = schema.get("properties", {})
        missing = [key for key in schema.get("required", []) if key not in arguments]
        unknown = [key for key in arguments if key not in properties]
        if missing or unknown:
            raise ValueError(f"invalid arguments for {name}: missing={missing}, unknown={unknown}")
        for key, value in arguments.items():
            expected = properties.get(key, {}).get("type")
            if expected == "string" and not isinstance(value, str):
                raise ValueError(f"argument {key} must be a string")
            if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                raise ValueError(f"argument {key} must be an integer")

    def normalize_arguments(self, name: str, arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, list):
            properties = list(getattr(self.tools[name], "parameters", {}).get("properties", {}))
            if len(arguments) > len(properties):
                raise ValueError(f"too many positional arguments for {name}")
            return dict(zip(properties, arguments))
        raise ValueError("tool arguments must be an object or supported positional list")

    def _inside(self, raw: str) -> Path:
        path = (self.workspace / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
        if path != self.workspace and self.workspace not in path.parents:
            raise PermissionDenied("path is outside the configured workspace")
        return path

    def read_file(self, path: str) -> str:
        return self._inside(path).read_text(encoding="utf-8")[:100_000]

    def list_directory(self, path: str = ".") -> str:
        return json.dumps(sorted(p.name for p in self._inside(path).iterdir()))

    def search_text(self, pattern: str, path: str = ".") -> str:
        root = self._inside(path)
        matches = []
        for file in root.rglob("*"):
            if file.is_file() and file.stat().st_size < 2_000_000:
                try:
                    for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
                        if pattern.lower() in line.lower():
                            matches.append(f"{file.relative_to(self.workspace)}:{number}:{line[:300]}")
                except UnicodeDecodeError:
                    continue
        return "\n".join(matches[:200]) or "No matches."

    def write_file(self, path: str, content: str) -> str:
        target = self._inside(path)
        if not self.approver(f"write {target}"):
            raise PermissionDenied("write requires explicit approval")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {target.relative_to(self.workspace)}"

    def run_command(self, command: str) -> str:
        dangerous = re.compile(r"(^|[;&|])(\s*)(rm\s+-rf|del\s+/s|format\s+|shutdown\s|git\s+reset\s+--hard|remove-item\s+-recurse)", re.IGNORECASE)
        if dangerous.search(command):
            raise PermissionDenied("dangerous command rejected")
        if not self.approver(f"run command: {command}"):
            raise PermissionDenied("command execution requires explicit approval")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        process = subprocess.Popen(command, cwd=self.workspace, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy(), creationflags=flags, start_new_session=(os.name != "nt"))
        with self._active_lock: self._active.add(process)
        try:
            _, stopped = wait_owned_process(process, self.cancel_event, 120)
            stdout, stderr = process.communicate(timeout=10)
            if stopped and self.cancel_event.is_set():
                raise RuntimeError("Task cancelled; owned command process tree terminated")
            if stopped:
                raise subprocess.TimeoutExpired(command, 120)
            return (stdout + stderr)[-20_000:]
        finally:
            with self._active_lock: self._active.discard(process)

    def cancel_active_processes(self) -> None:
        with self._active_lock:
            processes = list(self._active)
        for process in processes:
            terminate_process_tree(process)

    def browser_exec(self, code: str, timeout_s: int = 120) -> str:
        return self.browser.execute(code, timeout_s)

    def browser_shutdown(self) -> str:
        return self.browser.shutdown()

    def delegate_task(self, prompt: str, role: str = "specialist") -> str:
        if not self.delegate_handler:
            raise PermissionDenied("delegation is unavailable in this runtime")
        if not prompt.strip():
            raise ValueError("delegation prompt is required")
        return self.delegate_handler(prompt=prompt, role=role)


ToolRegistry.read_file.parameters = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
ToolRegistry.list_directory.parameters = {"type": "object", "properties": {"path": {"type": "string"}}}
ToolRegistry.search_text.parameters = {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}
ToolRegistry.write_file.parameters = {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}
ToolRegistry.run_command.parameters = {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}
ToolRegistry.browser_exec.parameters = {"type": "object", "properties": {"code": {"type": "string"}, "timeout_s": {"type": "integer"}}, "required": ["code"]}
ToolRegistry.browser_shutdown.parameters = {"type": "object", "properties": {}}
ToolRegistry.delegate_task.parameters = {"type": "object", "properties": {"prompt": {"type": "string"}, "role": {"type": "string"}}, "required": ["prompt"]}

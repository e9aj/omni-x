from __future__ import annotations

import json
import os
import subprocess
import re
from pathlib import Path
from typing import Any, Callable

from .hermes_browser import HermesBrowserAdapter


class PermissionDenied(RuntimeError):
    pass


class ToolRegistry:
    def __init__(self, workspace: Path | None = None, approver: Callable[[str], bool] | None = None):
        self.workspace = (workspace or Path.cwd()).resolve()
        self.approver = approver or (lambda _: False)
        self.tools: dict[str, Callable[..., str]] = {"read_file": self.read_file, "list_directory": self.list_directory, "search_text": self.search_text, "write_file": self.write_file, "run_command": self.run_command}
        self.browser = HermesBrowserAdapter(approver=self.approver)
        if self.browser.available:
            self.tools["browser_exec"] = self.browser_exec

    def schemas(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": name, "description": getattr(fn, "description", "OMNI-X tool"), "parameters": getattr(fn, "parameters", {"type": "object", "properties": {}})}} for name, fn in self.tools.items()]

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in self.tools:
            return f"Tool error: unknown tool {name}"
        try:
            return self.tools[name](**arguments)
        except (OSError, ValueError, PermissionDenied, subprocess.SubprocessError) as exc:
            return f"Tool error: {exc}"

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
        result = subprocess.run(command, cwd=self.workspace, shell=True, capture_output=True, text=True, timeout=120, env=os.environ.copy())
        return (result.stdout + result.stderr)[-20_000:]

    def browser_exec(self, code: str, timeout_s: int = 120) -> str:
        return self.browser.execute(code, timeout_s)


ToolRegistry.read_file.parameters = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
ToolRegistry.list_directory.parameters = {"type": "object", "properties": {"path": {"type": "string"}}}
ToolRegistry.search_text.parameters = {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}
ToolRegistry.write_file.parameters = {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}
ToolRegistry.run_command.parameters = {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}
ToolRegistry.browser_exec.parameters = {"type": "object", "properties": {"code": {"type": "string"}, "timeout_s": {"type": "integer"}}, "required": ["code"]}

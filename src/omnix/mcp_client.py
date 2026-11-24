"""Small, policy-gated MCP JSON-RPC client.

The client deliberately owns no credentials and performs no implicit network
connection. Callers must construct a connection explicitly and supply a
permission/audit boundary owned by OMNI-X.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


class MCPError(RuntimeError):
    pass


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str = ""
    input_schema: dict[str, Any] | None = None


class MCPConnection:
    def __init__(self, *, name: str, transport: str, endpoint: str = "", command: str = "",
                 args: tuple[str, ...] = (), headers: dict[str, str] | None = None,
                 permission: Callable[[str, dict[str, Any]], bool] | None = None,
                 audit: Callable[[str, str], None] | None = None, timeout: float = 10.0):
        if not name or len(name) > 120 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in name):
            raise ValueError("MCP connection name is invalid")
        if transport not in {"stdio", "http"}:
            raise ValueError("MCP transport must be stdio or http")
        if transport == "stdio" and not command:
            raise ValueError("stdio MCP command is required")
        if transport == "http" and not endpoint.startswith(("http://", "https://")):
            raise ValueError("HTTP MCP endpoint must use http or https")
        self.name, self.transport, self.endpoint, self.command = name, transport, endpoint, command
        self.args, self.headers = args, dict(headers or {})
        self.permission, self.audit, self.timeout = permission, audit, timeout
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._next_id = 0
        self._tools: dict[str, MCPTool] = {}
        self._lock = threading.Lock()

    def _record(self, event: str, detail: str = "") -> None:
        if self.audit:
            self.audit(event, detail[:500])

    def connect(self) -> dict[str, Any]:
        if self.transport == "stdio":
            if self._process is not None and self._process.poll() is None:
                return {"status": "connected", "transport": self.transport}
            self._process = subprocess.Popen([self.command, *self.args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                             shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self._reader = threading.Thread(target=self._read_stdout, daemon=True)
            self._reader.start()
        result = self._request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                                "clientInfo": {"name": "OMNI-X", "version": "0.1.0"}})
        self._record("connected", self.transport)
        return {"status": "connected", "transport": self.transport, "server": result.get("serverInfo", {})}

    def _read_stdout(self) -> None:
        assert self._process and self._process.stdout
        for line in self._process.stdout:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    self._messages.put(value)
            except (ValueError, TypeError):
                self._record("protocol_error", "invalid JSON response")

    def _request(self, method: str, params: dict[str, Any], cancel: threading.Event | None = None) -> dict[str, Any]:
        with self._lock:
            self._next_id += 1
            ident = self._next_id
            payload = json.dumps({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
            if self.transport == "http":
                request = urllib.request.Request(self.endpoint, data=payload.encode(), headers={"Content-Type": "application/json", **self.headers}, method="POST")
                try:
                    with urllib.request.urlopen(request, timeout=self.timeout) as response:
                        value = json.loads(response.read())
                except (OSError, ValueError) as exc:
                    raise MCPError("MCP HTTP request failed") from exc
            else:
                if not self._process or not self._process.stdin or self._process.poll() is not None:
                    raise MCPError("MCP stdio process is not connected")
                self._process.stdin.write(payload + "\n")
                self._process.stdin.flush()
                deadline = time.monotonic() + self.timeout
                while True:
                    if cancel and cancel.is_set():
                        raise MCPError("MCP request cancelled")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise MCPError("MCP request timed out")
                    try:
                        value = self._messages.get(timeout=min(0.2, remaining))
                    except queue.Empty:
                        continue
                    if value.get("id") == ident:
                        break
            if "error" in value:
                raise MCPError("MCP server returned an error")
            result = value.get("result")
            if not isinstance(result, dict):
                raise MCPError("MCP response result is invalid")
            return result

    def discover_tools(self) -> list[MCPTool]:
        result = self._request("tools/list", {})
        tools: list[MCPTool] = []
        for item in result.get("tools", []):
            if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]:
                tool = MCPTool(item["name"], str(item.get("description", "")), item.get("inputSchema"))
                tools.append(tool)
        self._tools = {item.name: item for item in tools}
        self._record("tools_discovered", str(len(tools)))
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any], *, cancel: threading.Event | None = None) -> dict[str, Any]:
        if name not in self._tools:
            raise MCPError("MCP tool is not discovered or allowlisted")
        if not isinstance(arguments, dict):
            raise MCPError("MCP tool arguments must be an object")
        if self.permission and not self.permission(name, arguments):
            self._record("tool_denied", name)
            raise PermissionError("MCP tool permission denied")
        self._record("tool_started", name)
        result = self._request("tools/call", {"name": name, "arguments": arguments}, cancel)
        self._record("tool_completed", name)
        return result

    def close(self) -> None:
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        self._record("closed", self.transport)


class MCPConnectionManager:
    """Bind MCP clients to an already reviewed and enabled registry entry."""

    def __init__(self, registry: Any, audit: Callable[[str, str], None] | None = None):
        self.registry = registry
        self.audit = audit
        self.connections: dict[str, MCPConnection] = {}

    def connect(self, name: str, **kwargs: Any) -> dict[str, Any]:
        spec = self.registry.get(name)
        if spec is None or "mcp" not in spec.interface.lower():
            raise MCPError("MCP integration is not registered")
        if not spec.enabled or spec.revoked or not spec.configured:
            raise PermissionError("MCP integration must be configured and enabled")
        connection = MCPConnection(name=name, audit=self.audit, **kwargs)
        result = connection.connect()
        self.connections[name] = connection
        return result

    def discover_tools(self, name: str) -> list[MCPTool]:
        connection = self.connections.get(name)
        if connection is None:
            raise MCPError("MCP connection is not active")
        return connection.discover_tools()

    def call_tool(self, name: str, tool: str, arguments: dict[str, Any], *, cancel: threading.Event | None = None) -> dict[str, Any]:
        connection = self.connections.get(name)
        if connection is None:
            raise MCPError("MCP connection is not active")
        return connection.call_tool(tool, arguments, cancel=cancel)

    def close(self, name: str) -> None:
        connection = self.connections.pop(name, None)
        if connection:
            connection.close()

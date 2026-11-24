import json
import sys
import textwrap
from threading import Event

import pytest

from omnix.integrations import IntegrationRegistry, IntegrationSpec
from omnix.mcp_client import MCPConnection, MCPConnectionManager, MCPError


SERVER = """import json, sys
for line in sys.stdin:
    request = json.loads(line)
    method = request['method']
    if method == 'initialize':
        result = {'serverInfo': {'name': 'fixture'}}
    elif method == 'tools/list':
        result = {'tools': [{'name': 'read_note', 'description': 'read', 'inputSchema': {'type': 'object'}}]}
    elif method == 'tools/call':
        result = {'content': [{'type': 'text', 'text': 'fixture-result'}]}
    else:
        result = {}
    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}), flush=True)
"""


def test_stdio_mcp_connects_discovers_and_executes_with_permission(tmp_path):
    events = []
    connection = MCPConnection(name="fixture", transport="stdio", command=sys.executable,
                               args=("-u", "-c", SERVER),
                               permission=lambda name, arguments: name == "read_note" and arguments == {"path": "x.md"},
                               audit=lambda event, detail: events.append((event, detail)))
    try:
        assert connection.connect()["status"] == "connected"
        assert [tool.name for tool in connection.discover_tools()] == ["read_note"]
        result = connection.call_tool("read_note", {"path": "x.md"})
        assert result["content"][0]["text"] == "fixture-result"
        with pytest.raises(PermissionError):
            connection.call_tool("read_note", {"path": "secret.md"})
        with pytest.raises(MCPError):
            connection.call_tool("unknown", {})
        assert ("tool_completed", "read_note") in events
        assert ("tool_denied", "read_note") in events
    finally:
        connection.close()


def test_mcp_cancellation_is_bounded(tmp_path):
    slow_server = textwrap.dedent("""import json, sys, time
for line in sys.stdin:
    request = json.loads(line)
    if request['method'] == 'initialize':
        result = {'serverInfo': {'name': 'fixture'}}
    else:
        time.sleep(30)
        result = {}
    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}), flush=True)
    """)
    connection = MCPConnection(name="fixture", transport="stdio", command=sys.executable,
                               args=("-u", "-c", slow_server), timeout=0.2)
    cancel = Event()
    try:
        connection.connect()
        cancel.set()
        with pytest.raises(MCPError):
            connection._request("tools/list", {}, cancel=cancel)
    finally:
        connection.close()


def test_mcp_manager_requires_reviewed_enabled_configured_entry():
    registry = IntegrationRegistry()
    registry.register(IntegrationSpec("fixture-mcp", "mcp", interface="mcp", enabled=False, configured=False))
    manager = MCPConnectionManager(registry)
    with pytest.raises(PermissionError):
        manager.connect("fixture-mcp", transport="stdio", command=sys.executable, args=("-u", "-c", SERVER))

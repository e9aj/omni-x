from pathlib import Path

from omnix.hermes_tool_adapter import HermesToolAdapter
from omnix.tools import ToolRegistry


def test_hermes_adapter_exposes_only_omnix_tools(tmp_path: Path):
    registry = ToolRegistry(tmp_path)
    adapter = HermesToolAdapter(registry)
    names = {item["function"]["name"] for item in adapter.schemas()}
    assert names == set(registry.tools)
    assert adapter.as_hermes_toolset() == sorted(registry.tools)


def test_hermes_adapter_normalizes_and_executes_read_only_tool(tmp_path: Path):
    (tmp_path / "note.txt").write_text("evidence", encoding="utf-8")
    adapter = HermesToolAdapter(ToolRegistry(tmp_path))
    assert adapter.call("read_file", ["note.txt"]) == "evidence"


def test_hermes_adapter_keeps_omnix_approval_boundary(tmp_path: Path):
    adapter = HermesToolAdapter(ToolRegistry(tmp_path))
    result = adapter.call("write_file", {"path": "blocked.txt", "content": "x"})
    assert result.startswith("Tool error:")
    assert not (tmp_path / "blocked.txt").exists()


def test_hermes_adapter_rejects_unknown_and_malformed_calls(tmp_path: Path):
    adapter = HermesToolAdapter(ToolRegistry(tmp_path))
    assert adapter.call("not_registered", {}) == "Tool error: unknown tool not_registered"
    result = adapter.call("read_file", {"path": "x", "extra": True})
    assert result.startswith("Tool error:")

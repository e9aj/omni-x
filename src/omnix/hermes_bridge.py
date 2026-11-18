"""Small Hermes Agent compatibility bridge used by the OMNI-X runtime.

This parser is adapted from NousResearch/hermes-agent's
``agent/acp_openai_bridge.py`` under its MIT licence. OMNI-X keeps its own
runtime, tools, permissions, storage, and branding; this module reuses the
Hermes tool-call wire contract for providers that return calls as text.
"""

from __future__ import annotations

import json
import ast
import re
from typing import Any

TOOL_CALL_CONTRACT = (
    "Available tools (OpenAI function schema). When using a tool, emit ONLY "
    "<tool_call>{...}</tool_call> with one JSON object containing "
    "id/type/function{name,arguments}. arguments must be a JSON string."
)
TOOL_CALL_BLOCK_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
TOOL_CALL_JSON_RE = re.compile(
    r'\{\s*"id"\s*:\s*"[^"]+"\s*,\s*"type"\s*:\s*"function"\s*,\s*"function"\s*:\s*\{.*?\}\s*\}',
    re.DOTALL,
)
TOOL_CALL_COMPAT_RE = re.compile(r"<tool_call>\s*mcp__[^_]+__(?P<name>[a-z_]+)\s*(?P<args>\{.*?\})", re.DOTALL)
FUNCTION_INVOKE_RE = re.compile(r"<invoke\s+name=\"mcp__[^_]+__(?P<name>[a-z_]+)\"\s*>\s*<arguments>(?P<args>\{.*?\})</arguments>\s*</invoke>", re.DOTALL)
GENERIC_TOOL_RE = re.compile(r"<tool_call>\s*tool_call\s*(?P<args>\{.*?\})\s*</tool_call>", re.DOTALL)
NAMESPACE_CALL_RE = re.compile(r"<tool_call>\s*mcp__[a-z_]+__(?P<name>[a-z_]+)\((?P<args>.*?)\)", re.DOTALL)
DIRECT_CALL_RE = re.compile(r"<tool_call>\s*(?P<name>[a-z_]+)\s*(?P<args>\{.*?\})", re.DOTALL)
PYTHON_CALL_RE = re.compile(r"<tool_call>\s*(?P<name>[a-z_]+)\s*\((?P<args>.*?)\)", re.DOTALL)
SINGLE_NAMESPACE_CALL_RE = re.compile(r"<tool_call>\s*mcp__(?P<name>[a-z_]+)\((?P<args>.*?)\)", re.DOTALL)


def _parse(raw: str, ordinal: int) -> dict[str, Any] | None:
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError):
        return None
    fn = obj.get("function") if isinstance(obj, dict) else None
    name = fn.get("name") if isinstance(fn, dict) else None
    if not isinstance(name, str) or not name.strip():
        return None
    args = fn.get("arguments", "{}")
    if not isinstance(args, str):
        args = json.dumps(args, ensure_ascii=False)
    call_id = obj.get("id") if isinstance(obj, dict) else None
    if not isinstance(call_id, str) or not call_id.strip():
        call_id = f"hermes_call_{ordinal}"
    return {"id": call_id, "type": "function", "function": {"name": name.strip(), "arguments": args}}


def extract_tool_calls(text: str) -> tuple[list[dict[str, Any]], str]:
    """Extract Hermes XML/bare-JSON calls and return cleaned assistant text."""
    if not isinstance(text, str) or not text.strip():
        return [], ""
    calls: list[dict[str, Any]] = []
    spans: list[tuple[int, int]] = []
    for pattern, group in ((TOOL_CALL_BLOCK_RE, 1), (TOOL_CALL_JSON_RE, 0)):
        for match in pattern.finditer(text):
            call = _parse(match.group(group), len(calls) + 1)
            if call is not None:
                calls.append(call)
            spans.append((match.start(), match.end()))
        if calls:
            break
    if not calls:
        for pattern in (TOOL_CALL_COMPAT_RE, FUNCTION_INVOKE_RE):
            for match in pattern.finditer(text):
                try:
                    arguments = json.loads(match.group("args"))
                except ValueError:
                    continue
                calls.append({
                    "id": f"hermes_call_{len(calls) + 1}",
                    "type": "function",
                    "function": {"name": match.group("name"), "arguments": json.dumps(arguments)},
                })
                spans.append((match.start(), match.end()))
            if calls:
                break
    if not calls:
        for match in GENERIC_TOOL_RE.finditer(text):
            try:
                payload = json.loads(match.group("args"))
                arguments = payload.get("arguments", {})
                if isinstance(arguments, str):
                    json.loads(arguments)
                else:
                    arguments = json.dumps(arguments)
                name = payload.get("name")
                if not isinstance(name, str) or not name:
                    continue
            except (TypeError, ValueError):
                continue
            calls.append({"id": f"hermes_call_{len(calls) + 1}", "type": "function", "function": {"name": name, "arguments": arguments}})
            spans.append((match.start(), match.end()))
    if not calls:
        for match in NAMESPACE_CALL_RE.finditer(text):
            try:
                expression = ast.parse(f"f({match.group('args')})", mode="eval").body
                arguments = {item.arg: ast.literal_eval(item.value) for item in expression.keywords if item.arg}
            except (SyntaxError, ValueError):
                continue
            for alias in ("file_path", "filename"):
                if alias in arguments and "path" not in arguments:
                    arguments["path"] = arguments.pop(alias)
            calls.append({"id": f"hermes_call_{len(calls) + 1}", "type": "function", "function": {"name": match.group("name"), "arguments": json.dumps(arguments)}})
            spans.append((match.start(), match.end()))
    if not calls:
        aliases = {"execute_command": "run_command"}
        for match in DIRECT_CALL_RE.finditer(text):
            if match.group("name") in {"tool_call", "mcp"}:
                continue
            try:
                arguments = json.loads(match.group("args"))
            except ValueError:
                continue
            name = aliases.get(match.group("name"), match.group("name"))
            calls.append({"id": f"hermes_call_{len(calls) + 1}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}})
            spans.append((match.start(), match.end()))
    if not calls:
        for pattern in (PYTHON_CALL_RE, SINGLE_NAMESPACE_CALL_RE):
            for match in pattern.finditer(text):
                try:
                    expression = ast.parse(f"f({match.group('args')})", mode="eval").body
                    arguments = {item.arg: ast.literal_eval(item.value) for item in expression.keywords if item.arg}
                except (SyntaxError, ValueError):
                    continue
                for alias in ("file_path", "filename"):
                    if alias in arguments and "path" not in arguments:
                        arguments["path"] = arguments.pop(alias)
                name = match.group("name")
                calls.append({"id": f"hermes_call_{len(calls) + 1}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}})
                spans.append((match.start(), match.end()))
            if calls:
                break
    if not spans:
        return [], text.strip()
    parts: list[str] = []
    cursor = 0
    for start, end in sorted(spans):
        if cursor < start:
            parts.append(text[cursor:start])
        cursor = max(cursor, end)
    if cursor < len(text):
        parts.append(text[cursor:])
    return calls, "\n".join(part.strip() for part in parts if part.strip()).strip()

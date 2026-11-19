"""Opt-in bridge to the actual Hermes ``AIAgent`` runtime.

The first migration slice is deliberately text-only: Hermes runs in its
installer-managed environment against OMNI-X's selected free OmniRoute route,
with Hermes-owned tools and persistence disabled. The existing OMNI-X runtime
remains the default until policy, tool and SQLite adapters are proven.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from typing import Any

from .config import Settings
from .hermes_runtime import hermes_python, installed_hermes_source
from .secrets import get_secret

_HERMES_PROBE = r'''
import json, sys
from run_agent import AIAgent
payload = json.loads(sys.stdin.read())
agent = AIAgent(
    base_url=payload["base_url"], api_key=payload["api_key"], provider="custom",
    model=payload["model"], max_iterations=payload["max_iterations"],
    enabled_toolsets=[], quiet_mode=True, skip_context_files=True,
    skip_memory=True, save_trajectories=False,
    platform="omnix-hermes-primary-probe",
)
result = agent.run_conversation(user_message=payload["prompt"])
if isinstance(result, dict):
    # Keep the bridge deliberately narrow: expose execution evidence, never the
    # full Hermes result (which may contain prompts or provider metadata).
    output = {
        "answer": result.get("final_response") or result.get("answer") or "",
        "provider": result.get("provider"),
        "served_model": result.get("served_model"),
        "input_tokens": result.get("input_tokens", result.get("prompt_tokens")),
        "output_tokens": result.get("output_tokens", result.get("completion_tokens")),
        "total_tokens": result.get("total_tokens"),
        "estimated_cost_usd": result.get("estimated_cost_usd"),
        "api_calls": result.get("api_calls"),
        "completed": result.get("completed"),
        "turn_exit_reason": result.get("turn_exit_reason"),
        "session_id": result.get("session_id"),
    }
else:
    output = {"answer": str(result)}
print(json.dumps(output, default=str), flush=True)
# Hermes owns background client/cache hooks that can outlive a short probe. The
# probe has no tools, memory or persistence, so process exit is the cleanest
# boundary after the result has been flushed.
import os
os._exit(0)
'''

_HERMES_TOOL_PROBE = r'''
import json, os, sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
sys.path.insert(0, payload["omnix_root"])
from omnix.tools import ToolRegistry
from omnix.hermes_tool_adapter import HermesToolAdapter
from omnix.hermes_bridge import extract_tool_calls

registry = ToolRegistry(Path(payload["workspace"]))
adapter = HermesToolAdapter(registry)
events = []

def hermes_schemas(*args, **kwargs):
    return adapter.schemas()

def hermes_dispatch(name, arguments, *args, **kwargs):
    safe_arguments = arguments if isinstance(arguments, dict) else {}
    result = adapter.call(name, safe_arguments)
    events.append({
        "name": name,
        "arguments": safe_arguments,
        "result": str(result)[-4000:],
        "success": not str(result).startswith("Tool error:"),
    })
    return result

import model_tools
model_tools.get_tool_definitions = hermes_schemas
model_tools.handle_function_call = hermes_dispatch
from run_agent import AIAgent
import agent.conversation_loop as conversation_loop
from types import SimpleNamespace

# Hermes normally receives native tool_calls. Some OmniRoute free routes return
# one of OMNI-X's already-supported, anchored textual contracts instead. Reuse
# that parser only at Hermes' response-normalization boundary; ordinary prose
# remains prose and never reaches dispatch.
_normalize_model_response = conversation_loop.normalize_model_response
def normalize_with_omnix_text_calls(*args, **kwargs):
    verdict = _normalize_model_response(*args, **kwargs)
    message = getattr(verdict, "assistant_message", None)
    if message is not None and not getattr(message, "tool_calls", None):
        calls, cleaned = extract_tool_calls(getattr(message, "content", "") or "")
        if calls:
            tool_calls = [SimpleNamespace(
                id=call["id"], type="function",
                function=SimpleNamespace(
                    name=call["function"]["name"],
                    arguments=call["function"]["arguments"],
                ),
            ) for call in calls]
            message.tool_calls = tool_calls
            message.content = cleaned
    return verdict
conversation_loop.normalize_model_response = normalize_with_omnix_text_calls

agent = AIAgent(
    base_url=payload["base_url"], api_key=payload["api_key"], provider="custom",
    model=payload["model"], max_iterations=payload["max_iterations"],
    enabled_toolsets=[], quiet_mode=True, skip_context_files=True,
    skip_memory=True, save_trajectories=False,
    platform="omnix-hermes-tool-probe",
)
result = agent.run_conversation(user_message=payload["prompt"])
if isinstance(result, dict):
    output = {
        "answer": result.get("final_response") or result.get("answer") or "",
        "provider": result.get("provider"),
        "served_model": result.get("served_model"),
        "input_tokens": result.get("input_tokens", result.get("prompt_tokens")),
        "output_tokens": result.get("output_tokens", result.get("completion_tokens")),
        "total_tokens": result.get("total_tokens"),
        "estimated_cost_usd": result.get("estimated_cost_usd"),
        "api_calls": result.get("api_calls"),
        "completed": result.get("completed"),
        "turn_exit_reason": result.get("turn_exit_reason"),
    }
else:
    output = {"answer": str(result)}
output["tool_events"] = events
output["available_tools"] = sorted(getattr(agent, "valid_tool_names", set()))
print(json.dumps(output, default=str), flush=True)
os._exit(0)
'''


class HermesPrimaryError(RuntimeError):
    """The actual Hermes runtime could not be safely invoked."""


def _is_explicitly_free(settings: Settings) -> bool:
    return settings.model in settings.free_models or settings.model in {"auto/best-free"} or settings.model.endswith(":free")


def run_hermes_primary_probe(settings: Settings, prompt: str, *, timeout: float = 120.0) -> dict[str, Any]:
    """Run one bounded, tool-disabled turn through Hermes's real ``AIAgent``."""
    if settings.mode != "FREE" or settings.allow_paid or settings.max_cost_usd != 0:
        raise HermesPrimaryError("Hermes primary probe requires FREE mode with zero spending")
    if settings.provider != "omniroute" or not _is_explicitly_free(settings):
        raise HermesPrimaryError("Hermes primary probe accepts only an explicitly free OmniRoute model")
    source = installed_hermes_source()
    python = hermes_python()
    if source is None or python is None:
        raise HermesPrimaryError("managed Hermes source and Python environment are required")
    if not settings.base_url:
        raise HermesPrimaryError("OmniRoute base URL is not configured")
    if not prompt.strip():
        raise HermesPrimaryError("prompt must not be empty")
    api_key = get_secret("OMNIROUTE_API_KEY") or os.environ.get("OMNIROUTE_API_KEY") or "omniroute-local"
    payload = {"base_url": settings.base_url.rstrip("/"), "api_key": api_key, "model": settings.model,
               "max_iterations": max(1, min(settings.max_steps, 8)), "prompt": prompt}
    env = os.environ.copy()
    env["PYTHONPATH"] = str(source)
    env["OMNIX_HERMES_PRIMARY"] = "1"
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    started = time.perf_counter()
    process = subprocess.Popen([str(python), "-c", _HERMES_PROBE], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               cwd=str(source), env=env, creationflags=flags)
    try:
        stdout, stderr = process.communicate(json.dumps(payload), timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            process.kill()
        process.communicate(timeout=5)
        raise HermesPrimaryError("Hermes primary probe timed out") from exc
    if process.returncode != 0:
        safe_error = stderr[-1000:].replace(api_key, "[redacted]")
        raise HermesPrimaryError(f"Hermes exited with code {process.returncode}: {safe_error}")
    for line in reversed(stdout.splitlines()):
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict) and isinstance(result.get("answer"), str):
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            metrics = {key: result.get(key) for key in (
                "provider", "served_model", "input_tokens", "output_tokens", "total_tokens",
                "estimated_cost_usd", "api_calls", "completed", "turn_exit_reason", "session_id"
            ) if key in result}
            metrics["latency_ms"] = elapsed_ms
            return {"answer": result["answer"], "model": settings.model,
                    "engine": "hermes-aiaagent", "usage": metrics}
    raise HermesPrimaryError("Hermes returned no structured result")


def run_hermes_tool_probe(settings: Settings, prompt: str, workspace: str, *, timeout: float = 120.0) -> dict[str, Any]:
    """Run the real Hermes loop with schemas and dispatch delegated to OMNI-X."""
    if settings.mode != "FREE" or settings.allow_paid or settings.max_cost_usd != 0:
        raise HermesPrimaryError("Hermes tool probe requires FREE mode with zero spending")
    if settings.provider != "omniroute" or not _is_explicitly_free(settings):
        raise HermesPrimaryError("Hermes tool probe accepts only an explicitly free OmniRoute model")
    source = installed_hermes_source()
    python = hermes_python()
    if source is None or python is None:
        raise HermesPrimaryError("managed Hermes source and Python environment are required")
    if not settings.base_url or not prompt.strip():
        raise HermesPrimaryError("OmniRoute base URL and prompt are required")
    workspace_path = os.path.abspath(workspace)
    if not os.path.isdir(workspace_path):
        raise HermesPrimaryError("tool probe workspace must exist")
    # The source checkout uses a src-layout; expose that directory to Hermes'
    # managed interpreter rather than relying on the caller's environment.
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    api_key = get_secret("OMNIROUTE_API_KEY") or os.environ.get("OMNIROUTE_API_KEY") or "omniroute-local"
    payload = {"base_url": settings.base_url.rstrip("/"), "api_key": api_key,
               "model": settings.model, "max_iterations": max(1, min(settings.max_steps, 6)),
               "prompt": prompt, "workspace": workspace_path, "omnix_root": project_root}
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(source), project_root))
    env["OMNIX_HERMES_PRIMARY"] = "1"
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    started = time.perf_counter()
    payload_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
    payload_file.write(json.dumps(payload))
    payload_file.close()
    payload["payload_path"] = payload_file.name
    process = subprocess.Popen([str(python), "-c", _HERMES_TOOL_PROBE, payload_file.name],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               cwd=str(source), env=env, creationflags=flags)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            process.kill()
        process.communicate(timeout=5)
        raise HermesPrimaryError("Hermes tool probe timed out") from exc
    finally:
        try:
            os.unlink(payload_file.name)
        except OSError:
            pass
    if process.returncode != 0:
        safe_error = stderr[-1000:].replace(api_key, "[redacted]")
        raise HermesPrimaryError(f"Hermes tool probe exited with code {process.returncode}: {safe_error}")
    for line in reversed(stdout.splitlines()):
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict) and isinstance(result.get("answer"), str):
            usage = {key: result.get(key) for key in (
                "provider", "served_model", "input_tokens", "output_tokens", "total_tokens",
                "estimated_cost_usd", "api_calls", "completed", "turn_exit_reason", "tool_events"
            ) if key in result}
            if "available_tools" in result:
                usage["available_tools"] = result["available_tools"]
            usage["latency_ms"] = round((time.perf_counter() - started) * 1000)
            return {"answer": result["answer"], "model": settings.model,
                    "engine": "hermes-aiaagent+omnix-tools", "usage": usage}
    raise HermesPrimaryError("Hermes tool probe returned no structured result")

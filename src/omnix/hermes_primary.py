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

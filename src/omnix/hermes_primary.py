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
try:
    result = agent.run_conversation(user_message=payload["prompt"])
    print(json.dumps({"answer": result if isinstance(result, str) else str(result)}))
finally:
    agent.close()
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
    completed = subprocess.run([str(python), "-c", _HERMES_PROBE], input=json.dumps(payload), text=True,
                               capture_output=True, cwd=str(source), env=env, timeout=timeout, check=False)
    if completed.returncode != 0:
        raise HermesPrimaryError(f"Hermes exited with code {completed.returncode}: {completed.stderr[-1000:]}")
    for line in reversed(completed.stdout.splitlines()):
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict) and isinstance(result.get("answer"), str):
            return {"answer": result["answer"], "model": settings.model, "engine": "hermes-aiaagent"}
    raise HermesPrimaryError("Hermes returned no structured result")

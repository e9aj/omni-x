from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .secrets import get_secret


@dataclass
class Discovery:
    gateway: str
    reachable: bool
    auth_required: bool
    models: list[dict[str, Any]]
    free_models: list[dict[str, Any]]
    latency_ms: float | None = None
    error: str | None = None


def _is_explicitly_free(model: dict[str, Any]) -> bool:
    if model.get("free") is True or model.get("isFree") is True:
        return True
    pricing = model.get("pricing") or {}
    if isinstance(pricing, dict) and pricing and all(str(pricing.get(k, "1")) in {"0", "0.0", "0.00"} for k in ("prompt", "completion", "input", "output") if k in pricing):
        return True
    model_id = str(model.get("id", "")).lower()
    return ":free" in model_id or model_id.endswith("-free") or "/free" in model_id


def discover_omniroute(settings: Settings) -> Discovery:
    base = (settings.base_url or "http://127.0.0.1:20128/v1").rstrip("/")
    url = base + "/models"
    key = get_secret("OMNIROUTE_API_KEY")
    headers = {"User-Agent": "OMNI-X", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    started = time.perf_counter()
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=min(settings.request_timeout_seconds, 10)) as response:
            payload = json.loads(response.read())
        models = payload.get("data", []) if isinstance(payload, dict) else []
        free = [model for model in models if isinstance(model, dict) and _is_explicitly_free(model)]
        return Discovery(base, True, False, models, free, (time.perf_counter() - started) * 1000)
    except urllib.error.HTTPError as exc:
        return Discovery(base, False, exc.code in {401, 403}, [], [], (time.perf_counter() - started) * 1000, f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return Discovery(base, False, False, [], [], (time.perf_counter() - started) * 1000, str(exc))


def choose_free_model(discovery: Discovery, task: str = "general") -> dict[str, Any] | None:
    if not discovery.free_models:
        return None
    terms = set(task.lower().split())
    def score(model: dict[str, Any]) -> tuple[int, int]:
        model_id = str(model.get("id", "")).lower()
        capabilities = model.get("capabilities") or {}
        capability_score = sum(2 for word in terms if word in model_id)
        if capabilities.get("tool_calling"):
            capability_score += 5
        if capabilities.get("reasoning"):
            capability_score += 1
        if "code" in terms and capabilities.get("tool_calling"):
            capability_score += 3
        context = int(model.get("context_length", 0) or 0)
        return capability_score, context
    return max(discovery.free_models, key=score)

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import Any

from .config import Settings
from .discovery import Discovery, discover_omniroute
from .hermes_bridge import extract_tool_calls
from .providers import ModelClient, ProviderError
from .store import Store


class ModelProbe:
    """Bounded, evidence-producing probes for explicitly free OmniRoute models."""

    def __init__(self, settings: Settings, store: Store | None = None):
        self.settings = settings
        self.store = store or Store()

    def discover(self) -> Discovery:
        return discover_omniroute(replace(self.settings, provider="omniroute"))

    @staticmethod
    def _category(error: str) -> str:
        text = error.lower()
        if "401" in text or "403" in text or "credential" in text or "auth" in text:
            return "auth_failures"
        if "429" in text or "rate limit" in text:
            return "rate_limits"
        if "timeout" in text or "timed out" in text:
            return "timeouts"
        return "provider_errors"

    def probe(self, model: dict[str, Any], tool: bool = False) -> dict[str, Any]:
        model_id = str(model.get("id"))
        started = time.perf_counter()
        result: dict[str, Any] = {
            "model": model_id,
            "upstream": model.get("owned_by") or model.get("provider"),
            "free": True,
            "context_length": model.get("context_length", 0),
            "declared_tool_calling": bool((model.get("capabilities") or {}).get("tool_calling")),
            "available": False,
            "tool_verified": False,
            "successes": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_ms": 0,
        }
        messages = [{"role": "user", "content": "Reply with exactly: OMNIX_PROBE_OK"}]
        schemas = None
        if tool:
            schemas = [{"type": "function", "function": {"name": "list_directory", "description": "List a directory read-only.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}]
            messages = [{"role": "user", "content": "Use the list_directory tool on the current workspace, then report the result."}]
        try:
            settings = replace(self.settings, provider="omniroute", model=model_id, mode="FREE", allow_paid=False, max_cost_usd=0.0)
            response = ModelClient(settings).complete(messages, schemas)
            usage = response.get("usage") or {}
            result["input_tokens"] = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
            result["output_tokens"] = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
            result["available"] = True
            result["successes"] = 1
            if tool:
                message = (response.get("choices") or [{}])[0].get("message") or {}
                calls = message.get("tool_calls") or extract_tool_calls(message.get("content") or "")[0]
                if calls and calls[0].get("function", {}).get("name") == "list_directory":
                    result["tool_verified"] = True
                    result["tool_successes"] = 1
                else:
                    result["tool_failures"] = 1
        except ProviderError as exc:
            result["last_error"] = str(exc)
            result[self._category(str(exc))] = 1
        finally:
            result["latency_ms"] = (time.perf_counter() - started) * 1000
            self.store.record_model_probe(result)
        return result

    def probe_models(self, models: list[dict[str, Any]], max_workers: int = 2) -> list[dict[str, Any]]:
        # Probe declared tool-capable routes and one ordinary free route. The
        # catalogue remains complete; probes are deliberately bounded.
        selected: list[dict[str, Any]] = []
        for model in models:
            capabilities = model.get("capabilities") or {}
            if capabilities.get("tool_calling"):
                selected.append(model)
        selected.extend(model for model in models if model not in selected and len(selected) < 3)
        selected = selected[:4]
        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, 2))) as pool:
            futures = {pool.submit(self.probe, model, bool((model.get("capabilities") or {}).get("tool_calling"))): model for model in selected}
            for future in as_completed(futures):
                results.append(future.result())
        return sorted(results, key=lambda item: item["model"])


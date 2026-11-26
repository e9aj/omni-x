from __future__ import annotations

import time
import os
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .providers import ModelClient, ProviderError, PROVIDERS
from .secrets import get_secret


@dataclass(frozen=True)
class Route:
    provider: str
    model: str


class Router:
    def __init__(self, settings: Settings, health_provider=None, health_recorder=None, failure_recorder=None, model_health_provider=None):
        self.settings = settings
        self.health_provider = health_provider or (lambda: {})
        self.health_recorder = health_recorder
        self.failure_recorder = failure_recorder
        self.model_health_provider = model_health_provider or (lambda: {})
        self.routes = self._routes()

    def _routes(self) -> list[Route]:
        requested = Route(self.settings.provider, self.settings.model)
        candidates = [requested]
        if self.settings.mode == "FREE" and self.settings.provider == "omniroute":
            health = self.model_health_provider()
            free_models = [model for model in self.settings.free_models if model]
            verified = [model for model in free_models if int((health.get(model) or {}).get("tested", 0) or 0) and not int((health.get(model) or {}).get("available", 0) or 0)]
            if len(verified) < len(free_models):
                free_models = [model for model in free_models if model not in verified]
            free_models.sort(key=lambda model: self._model_rank(model, health), reverse=True)
            candidates = [Route("omniroute", model) for model in free_models if model != requested.model]
            requested_row = health.get(requested.model) or {}
            if not (int(requested_row.get("tested", 0) or 0) and not int(requested_row.get("available", 0) or 0)):
                candidates.insert(0, requested)
        if self.settings.mode in {"FREE", "SMART"}:
            for name in ("groq", "cerebras", "gemini", "omniroute"):
                if name != requested.provider and name != "omniroute" and PROVIDERS[name].free_eligible:
                    candidates.append(Route(name, self.settings.model))
        requested, *fallbacks = candidates
        health = self.health_provider()
        fallbacks.sort(key=lambda route: (not health.get(route.provider, {}).get("healthy", True), health.get(route.provider, {}).get("latency_ms", float("inf"))))
        return [requested, *fallbacks]

    @staticmethod
    def _model_rank(model: str, health: dict[str, dict[str, object]]) -> tuple[int, int, float]:
        row = health.get(model, {})
        tested = int(row.get("tested", 0) or 0)
        available = int(row.get("available", 0) or 0)
        tool_verified = int(row.get("tool_verified", 0) or 0)
        failures = int(row.get("auth_failures", 0) or 0) + int(row.get("timeouts", 0) or 0) + int(row.get("provider_errors", 0) or 0)
        latency = float(row.get("p95_latency_ms", 999999) or 999999)
        return (tool_verified * 100 + available * 20 + tested * 5 - min(failures, 20) * 10, int(row.get("successes", 0) or 0), -latency)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                 record=None, requires_tools: bool = False,
                 parameters: dict[str, Any] | None = None, on_delta=None, cancel_event=None) -> tuple[dict[str, Any], Route]:
        errors = []
        for route in self.routes[:5]:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Task cancelled")
            provider = PROVIDERS[route.provider]
            if requires_tools and route.provider == "omniroute":
                model_row = self.model_health_provider().get(route.model, {})
                if int(model_row.get("tested", 0) or 0) and not int(model_row.get("tool_verified", 0) or 0):
                    errors.append(f"{route.model}: tool calling is not verified")
                    continue
            if not provider.free_eligible and not self.settings.allow_paid:
                errors.append(f"{route.provider}: paid inference requires allow_paid=true")
                continue
            if self.settings.mode == "FREE" and route.provider == "omniroute":
                known_free = route.model in self.settings.free_models or ":free" in route.model.lower() or route.model.lower().endswith("-free")
                if not known_free:
                    errors.append(f"{route.provider}: model is not verified free by discovery")
                    continue
            if self.settings.mode == "FREE" and route.provider == "openrouter" and ":free" not in route.model:
                errors.append("openrouter: model is not explicitly marked :free")
                continue
            if provider.name != "omniroute" and not (get_secret(provider.key_name) or os.environ.get(provider.key_name)):
                errors.append(f"{route.provider}: credential unavailable")
                continue
            started = time.perf_counter()
            emitted = False

            def emit(text):
                nonlocal emitted
                emitted = True
                if on_delta:
                    on_delta(text)

            try:
                client = ModelClient(self.settings.__class__(**{**self.settings.__dict__, "provider": route.provider, "model": route.model}))
                if on_delta is not None:
                    result = client.stream(messages, tools, parameters, emit, cancel_event)
                else:
                    result = client.complete(messages, tools, parameters)
                usage = result.get("usage", {})
                latency_ms = (time.perf_counter() - started) * 1000
                actual_model = result.get("model") if isinstance(result, dict) else None
                observed_route = Route(route.provider, str(actual_model or route.model))
                if self.health_recorder:
                    self.health_recorder(route.provider, True, latency_ms, None)
                if record:
                    record(observed_route, usage, latency_ms)
                return result, observed_route
            except ProviderError as exc:
                if self.failure_recorder:
                    text = str(exc).lower()
                    category = "401" if "401" in text or "credential" in text else "429" if "429" in text or "rate limit" in text else "502" if "502" in text or "bad gateway" in text else "timeout" if "timeout" in text or "timed out" in text else "provider_error"
                    self.failure_recorder(route.provider, category, str(exc), (time.perf_counter() - started) * 1000)
                if self.health_recorder:
                    self.health_recorder(route.provider, False, (time.perf_counter() - started) * 1000, str(exc))
                if emitted:
                    raise ProviderError("Provider stream interrupted after partial output") from exc
                errors.append(f"{route.provider}: {exc}")
        raise ProviderError("All eligible provider routes failed: " + " | ".join(errors))

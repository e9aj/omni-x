from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .providers import ModelClient, ProviderError, PROVIDERS


@dataclass(frozen=True)
class Route:
    provider: str
    model: str


class Router:
    def __init__(self, settings: Settings, health_provider=None, health_recorder=None):
        self.settings = settings
        self.health_provider = health_provider or (lambda: {})
        self.health_recorder = health_recorder
        self.routes = self._routes()

    def _routes(self) -> list[Route]:
        requested = Route(self.settings.provider, self.settings.model)
        candidates = [requested]
        if self.settings.mode in {"FREE", "SMART"}:
            for name in ("groq", "cerebras", "gemini", "omniroute"):
                if name != requested.provider and PROVIDERS[name].free_eligible:
                    candidates.append(Route(name, self.settings.model))
        requested, *fallbacks = candidates
        health = self.health_provider()
        fallbacks.sort(key=lambda route: (not health.get(route.provider, {}).get("healthy", True), health.get(route.provider, {}).get("latency_ms", float("inf"))))
        return [requested, *fallbacks]

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, record=None) -> tuple[dict[str, Any], Route]:
        errors = []
        for route in self.routes[:3]:
            provider = PROVIDERS[route.provider]
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
            try:
                client = ModelClient(self.settings.__class__(**{**self.settings.__dict__, "provider": route.provider, "model": route.model}))
                started = time.perf_counter()
                result = client.complete(messages, tools)
                usage = result.get("usage", {})
                latency_ms = (time.perf_counter() - started) * 1000
                if self.health_recorder:
                    self.health_recorder(route.provider, True, latency_ms, None)
                if record:
                    record(route, usage, latency_ms)
                return result, route
            except ProviderError as exc:
                if self.health_recorder:
                    self.health_recorder(route.provider, False, (time.perf_counter() - started) * 1000, str(exc))
                errors.append(f"{route.provider}: {exc}")
        raise ProviderError("All eligible provider routes failed: " + " | ".join(errors))

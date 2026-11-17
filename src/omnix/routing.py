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
    def __init__(self, settings: Settings):
        self.settings = settings
        self.routes = self._routes()

    def _routes(self) -> list[Route]:
        requested = Route(self.settings.provider, self.settings.model)
        candidates = [requested]
        if self.settings.mode in {"FREE", "SMART"}:
            for name in ("groq", "cerebras", "gemini", "omniroute"):
                if name != requested.provider and PROVIDERS[name].free_eligible:
                    candidates.append(Route(name, self.settings.model))
        return candidates

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, record=None) -> tuple[dict[str, Any], Route]:
        errors = []
        for route in self.routes[:3]:
            provider = PROVIDERS[route.provider]
            if not provider.free_eligible and not self.settings.allow_paid:
                errors.append(f"{route.provider}: paid inference requires allow_paid=true")
                continue
            if self.settings.mode == "FREE" and route.provider == "openrouter" and ":free" not in route.model:
                errors.append("openrouter: model is not explicitly marked :free")
                continue
            try:
                client = ModelClient(self.settings.__class__(**{**self.settings.__dict__, "provider": route.provider, "model": route.model}))
                started = time.perf_counter()
                result = client.complete(messages, tools)
                usage = result.get("usage", {})
                if record:
                    record(route, usage, (time.perf_counter() - started) * 1000)
                return result, route
            except ProviderError as exc:
                errors.append(f"{route.provider}: {exc}")
        raise ProviderError("All eligible provider routes failed: " + " | ".join(errors))

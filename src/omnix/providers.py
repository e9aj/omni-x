from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .secrets import get_secret


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    key_name: str
    kind: str = "openai"
    free_eligible: bool = False


PROVIDERS = {
    "openai": Provider("openai", "https://api.openai.com/v1", "OPENAI_API_KEY"),
    "omniroute": Provider("omniroute", "http://127.0.0.1:20128/v1", "OMNIROUTE_API_KEY"),
    "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "groq": Provider("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", free_eligible=True),
    "cerebras": Provider("cerebras", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY", free_eligible=True),
    "gemini": Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", free_eligible=True),
    "mistral": Provider("mistral", "https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "together": Provider("together", "https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "deepseek": Provider("deepseek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "anthropic": Provider("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY", "anthropic"),
}


class ProviderError(RuntimeError):
    pass


class ModelClient:
    def __init__(self, settings: Settings):
        if settings.provider not in PROVIDERS:
            raise ProviderError(f"Unknown provider '{settings.provider}'. Supported: {', '.join(PROVIDERS)}")
        self.settings = settings
        self.provider = PROVIDERS[settings.provider]
        self.api_key = get_secret(self.provider.key_name) or os.environ.get(self.provider.key_name)
        if not self.api_key:
            raise ProviderError(f"No credential configured for {self.provider.name}; use 'omnix config set-key {self.provider.key_name}'")

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if self.provider.kind == "anthropic":
            return self._anthropic(messages, tools or [])
        url = (self.settings.base_url or self.provider.base_url).rstrip("/") + "/chat/completions"
        body: dict[str, Any] = {"model": self.settings.model, "messages": messages}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        return self._post(url, body, {"Authorization": f"Bearer {self.api_key}"})

    def list_models(self) -> list[dict[str, Any]]:
        if self.provider.kind == "anthropic":
            return []
        url = (self.settings.base_url or self.provider.base_url).rstrip("/") + "/models"
        return self._request_json(url, {"Authorization": f"Bearer {self.api_key}"}).get("data", [])

    def health_check(self) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            models = self.list_models()
            return {"provider": self.provider.name, "healthy": True, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "models": len(models)}
        except ProviderError as exc:
            return {"provider": self.provider.name, "healthy": False, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error": str(exc)}

    def _anthropic(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        converted = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        body: dict[str, Any] = {"model": self.settings.model, "max_tokens": 4096, "messages": converted}
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""), "input_schema": t["function"]["parameters"]} for t in tools]
        result = self._post(self.provider.base_url + "/v1/messages", body, {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
        text = "".join(part.get("text", "") for part in result.get("content", []) if part.get("type") == "text")
        calls = [{"id": part.get("id", ""), "type": "function", "function": {"name": part["name"], "arguments": json.dumps(part.get("input", {}))}} for part in result.get("content", []) if part.get("type") == "tool_use"]
        usage = result.get("usage", {})
        return {"choices": [{"message": {"role": "assistant", "content": text, "tool_calls": calls}}], "usage": {"prompt_tokens": usage.get("input_tokens", 0), "completion_tokens": usage.get("output_tokens", 0)}}

    def _post(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        return self._request_json(url, headers, body)

    def _request_json(self, url: str, headers: dict[str, str], body: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in range(self.settings.retry_limit + 1):
            request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json", **headers}, method="POST" if body is not None else "GET")
            try:
                with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")
                retryable = exc.code == 429 or exc.code in {500, 502, 503, 504}
                if not retryable or attempt >= self.settings.retry_limit:
                    label = "rate limit" if exc.code == 429 else f"HTTP {exc.code}"
                    raise ProviderError(f"Provider {label}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt >= self.settings.retry_limit:
                    raise ProviderError(f"Provider request failed: {exc}") from exc
            time.sleep(min(2 ** attempt, 8))
        raise ProviderError("Provider request exhausted retry limit")

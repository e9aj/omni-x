from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
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
    "omniroute": Provider("omniroute", "http://127.0.0.1:20128/v1", "OMNIROUTE_API_KEY", free_eligible=True),
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _safe_generation_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    """Allow only bounded, provider-neutral generation controls."""
    if not parameters:
        return {}
    result: dict[str, Any] = {}
    if isinstance(parameters.get("temperature"), (int, float)):
        result["temperature"] = max(0.0, min(float(parameters["temperature"]), 2.0))
    if isinstance(parameters.get("top_p"), (int, float)):
        result["top_p"] = max(0.0, min(float(parameters["top_p"]), 1.0))
    if isinstance(parameters.get("max_tokens"), int):
        result["max_tokens"] = max(1, min(parameters["max_tokens"], 8192))
    if isinstance(parameters.get("seed"), int):
        result["seed"] = parameters["seed"]
    return result


def _validate_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProviderError("provider URL must use HTTP(S)")
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ProviderError("provider URL must not contain credentials, query or fragment")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ProviderError("unencrypted provider URLs are limited to loopback")
    return url


class ModelClient:
    def __init__(self, settings: Settings):
        if settings.provider not in PROVIDERS:
            raise ProviderError(f"Unknown provider '{settings.provider}'. Supported: {', '.join(PROVIDERS)}")
        self.settings = settings
        self.provider = PROVIDERS[settings.provider]
        self.api_key = get_secret(self.provider.key_name) or os.environ.get(self.provider.key_name)
        if not self.api_key and self.provider.name != "omniroute":
            raise ProviderError(f"No credential configured for {self.provider.name}; use 'omnix config set-key {self.provider.key_name}'")

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                 parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.provider.kind == "anthropic":
            return self._anthropic(messages, tools or [], parameters)
        url = (self.settings.base_url or self.provider.base_url).rstrip("/") + "/chat/completions"
        body: dict[str, Any] = {"model": self.settings.model, "messages": messages}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        body.update(_safe_generation_parameters(parameters))
        return self._post(url, body, self._auth_headers())

    def stream(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
               parameters: dict[str, Any] | None = None, on_delta=None, cancel_event=None) -> dict[str, Any]:
        """Consume OpenAI-compatible SSE incrementally and reconstruct tool calls.

        No retry is attempted here: replaying a partially displayed response can
        duplicate output or actions. The runtime still owns all tool dispatch.
        """
        if self.provider.kind != "openai":
            raise ProviderError("Streaming is unavailable for this provider")
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Task cancelled")
        url = _validate_http_url((self.settings.base_url or self.provider.base_url).rstrip("/") + "/chat/completions")
        body: dict[str, Any] = {"model": self.settings.model, "messages": messages, "stream": True}
        if tools:
            body.update({"tools": tools, "tool_choice": "auto"})
        body.update(_safe_generation_parameters(parameters))
        request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Accept": "text/event-stream", **self._auth_headers()}, method="POST")
        chunks: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        usage: dict[str, Any] = {}
        model = self.settings.model
        total = 0
        done = False
        try:
            opener = urllib.request.build_opener(_NoRedirect)
            with opener.open(request, timeout=getattr(self.settings, "provider_request_timeout_seconds", self.settings.request_timeout_seconds)) as response:  # nosec B310
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise RuntimeError("Task cancelled")
                    line = response.readline(1_000_001)
                    if not line:
                        break
                    total += len(line)
                    if total > 8_000_000 or len(line) > 1_000_000:
                        raise ProviderError("Provider stream exceeded size limit")
                    if not line.startswith(b"data:"):
                        continue
                    data = line[5:].strip()
                    if data == b"[DONE]":
                        done = True
                        break
                    try:
                        part = json.loads(data)
                        if not isinstance(part, dict):
                            raise ValueError("invalid event")
                        if part.get("error"):
                            raise ProviderError("Provider reported a streaming error")
                        model = part.get("model") or model
                        usage = part.get("usage") or usage
                        for choice in part.get("choices") or []:
                            if choice.get("index", 0) != 0:
                                continue
                            delta = choice.get("delta") or {}
                            text = delta.get("content")
                            if isinstance(text, str) and text:
                                chunks.append(text)
                                if on_delta:
                                    on_delta(text)
                            for item in delta.get("tool_calls") or []:
                                index = item.get("index")
                                if not isinstance(index, int) or index < 0 or index >= 128:
                                    raise ValueError("invalid tool call index")
                                call = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                                call["id"] += item.get("id") or ""
                                function = item.get("function") or {}
                                call["function"]["name"] += function.get("name") or ""
                                call["function"]["arguments"] += function.get("arguments") or ""
                    except (ValueError, TypeError, AttributeError, KeyError) as exc:
                        raise ProviderError("Invalid provider stream event") from exc
        except urllib.error.HTTPError as exc:
            exc.close()
            raise ProviderError(f"Provider HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderError("Provider stream failed or timed out") from exc
        if not done:
            raise ProviderError("Provider stream ended before completion")
        return {"model": model, "choices": [{"message": {"role": "assistant", "content": "".join(chunks), "tool_calls": [calls[i] for i in sorted(calls)]}}], "usage": usage}

    def list_models(self) -> list[dict[str, Any]]:
        if self.provider.kind == "anthropic":
            return []
        url = (self.settings.base_url or self.provider.base_url).rstrip("/") + "/models"
        return self._request_json(url, self._auth_headers()).get("data", [])

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def health_check(self) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            models = self.list_models()
            return {"provider": self.provider.name, "healthy": True, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "models": len(models)}
        except ProviderError as exc:
            return {"provider": self.provider.name, "healthy": False, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error": str(exc)}

    def _anthropic(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
                   parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        converted = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        body: dict[str, Any] = {"model": self.settings.model, "max_tokens": 4096, "messages": converted}
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""), "input_schema": t["function"]["parameters"]} for t in tools]
        body.update(_safe_generation_parameters(parameters))
        result = self._post(self.provider.base_url + "/v1/messages", body, {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
        text = "".join(part.get("text", "") for part in result.get("content", []) if part.get("type") == "text")
        calls = [{"id": part.get("id", ""), "type": "function", "function": {"name": part["name"], "arguments": json.dumps(part.get("input", {}))}} for part in result.get("content", []) if part.get("type") == "tool_use"]
        usage = result.get("usage", {})
        return {"choices": [{"message": {"role": "assistant", "content": text, "tool_calls": calls}}], "usage": {"prompt_tokens": usage.get("input_tokens", 0), "completion_tokens": usage.get("output_tokens", 0)}}

    def _post(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        return self._request_json(url, headers, body)

    def _request_json(self, url: str, headers: dict[str, str], body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = _validate_http_url(url)
        for attempt in range(self.settings.retry_limit + 1):
            request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json", **headers}, method="POST" if body is not None else "GET")
            try:
                opener = urllib.request.build_opener(_NoRedirect)
                with opener.open(request, timeout=getattr(self.settings, "provider_request_timeout_seconds", self.settings.request_timeout_seconds)) as response:  # nosec B310
                    payload = response.read(8_000_001)
                    if len(payload) > 8_000_000:
                        raise ProviderError("Provider response exceeded size limit")
                    try:
                        result = json.loads(payload)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise ProviderError("Provider returned invalid JSON") from exc
                    if not isinstance(result, dict):
                        raise ProviderError("Provider returned an invalid response")
                    return result
            except urllib.error.HTTPError as exc:
                retryable = exc.code == 429 or exc.code in {500, 502, 503, 504}
                exc.close()
                if not retryable or attempt >= self.settings.retry_limit:
                    label = "rate limit" if exc.code == 429 else f"HTTP {exc.code}"
                    raise ProviderError(f"Provider {label}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt >= self.settings.retry_limit:
                    raise ProviderError("Provider request failed or timed out") from exc
            time.sleep(min(2 ** attempt, 8))
        raise ProviderError("Provider request exhausted retry limit")

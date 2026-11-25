from omnix.config import Settings
from omnix.providers import ProviderError
from omnix.routing import Router, Route
import pytest
from types import SimpleNamespace


def test_free_mode_rejects_paid_requested_provider():
    router = Router(Settings(provider="openai", mode="FREE"))
    try:
        router.complete([{"role": "user", "content": "hello"}])
    except ProviderError as exc:
        assert "paid inference requires allow_paid=true" in str(exc)
    else:
        raise AssertionError("FREE mode accepted a paid-only route")


def test_partial_stream_failure_is_not_retried_on_another_route(monkeypatch):
    attempted = []

    class FakeClient:
        def __init__(self, settings):
            attempted.append(settings.model)
            self.provider = SimpleNamespace(kind="openai")

        def stream(self, _messages, _tools, _parameters, on_delta, _cancel):
            on_delta("partial")
            raise ProviderError("lost connection")

    monkeypatch.setattr("omnix.routing.ModelClient", FakeClient)
    settings = Settings(provider="omniroute", mode="FREE", model="one-free", free_models=["one-free", "two-free"])
    router = Router(settings)
    router.routes = [Route("omniroute", "one-free"), Route("omniroute", "two-free")]
    received = []
    with pytest.raises(ProviderError, match="interrupted after partial output"):
        router.complete([], on_delta=received.append)
    assert received == ["partial"]
    assert attempted == ["one-free"]


def test_free_omniroute_prefers_verified_tool_model_and_excludes_failed_model():
    settings = Settings(provider="omniroute", mode="FREE", model="auto/best-free", free_models=["auto/best-free", "ddgw/gpt-5.4-mini", "auto/coding:free"])
    health = {
        "auto/best-free": {"tested": 1, "available": 1, "tool_verified": 1, "successes": 1, "p95_latency_ms": 100},
        "ddgw/gpt-5.4-mini": {"tested": 1, "available": 0, "tool_verified": 0},
        "auto/coding:free": {"tested": 0, "available": 0, "tool_verified": 0},
    }
    router = Router(settings, model_health_provider=lambda: health)
    assert [route.model for route in router.routes[:2]] == ["auto/best-free", "auto/coding:free"]
    assert "ddgw/gpt-5.4-mini" not in [route.model for route in router.routes]


def test_free_omniroute_excludes_tool_unverified_route_for_tool_task():
    settings = Settings(provider="omniroute", mode="FREE", model="auto/best-free", free_models=["auto/best-free"])
    health = {"auto/best-free": {"tested": 1, "available": 1, "tool_verified": 0}}
    router = Router(settings, model_health_provider=lambda: health)
    try:
        router.complete([], [], requires_tools=True)
    except ProviderError as exc:
        assert "tool calling is not verified" in str(exc)
    else:
        raise AssertionError("tool-unverified FREE route was selected for a tool task")

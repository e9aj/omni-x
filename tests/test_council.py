import pytest

from omnix.config import Settings
from omnix.council import CouncilConfig, CouncilService, ModelRef
from omnix.routing import Route


class FakeRouter:
    calls = []

    def __init__(self, settings):
        self.settings = settings

    def complete(self, messages, tools=None, parameters=None):
        self.calls.append((self.settings.provider, self.settings.model, parameters))
        text = f"answer from {self.settings.model} with distinct evidence"
        return ({"choices": [{"message": {"content": text}}],
                 "usage": {"prompt_tokens": 4, "completion_tokens": 3}},
                Route(self.settings.provider, self.settings.model))


def service():
    FakeRouter.calls = []
    return CouncilService(Settings(provider="omniroute", model="m1", mode="FREE", free_models=["m1"]), FakeRouter)


def test_standard_is_one_model_and_records_usage():
    result = service().run([{"role": "user", "content": "hello"}])
    assert result.mode == "standard"
    assert len(result.candidates) == 1
    assert result.total_input_tokens == 4
    assert result.answer.startswith("answer from")


def test_council_runs_three_models_and_passes_adaptive_parameters():
    result = service().run([], CouncilConfig(
        mode="council", models=(ModelRef("omniroute", "m1"), ModelRef("omniroute", "m2"), ModelRef("omniroute", "m3")),
        max_concurrency=2, adaptive_parameters={"temperature": 0.1}))
    assert len(result.candidates) == 3
    assert len(FakeRouter.calls) == 3
    assert all(call[2]["temperature"] == 0.1 and call[2]["max_tokens"] == 2048 for call in FakeRouter.calls)


def test_research_requires_explicit_model_group():
    with pytest.raises(ValueError):
        service().run([], CouncilConfig(mode="research"))


def test_paid_council_is_denied_without_explicit_policy():
    with pytest.raises(PermissionError):
        service().run([], CouncilConfig(mode="standard", free_only=False, max_cost_usd=1))


def test_robustness_testing_requires_explicit_authorisation():
    with pytest.raises(PermissionError):
        service().authorised_robustness_test(["safe capability probe"])


def test_benchmark_returns_measured_candidates():
    candidates = service().benchmark_models(["return a short capability answer"], CouncilConfig(
        mode="research", models=(ModelRef("omniroute", "m1"),)))
    assert candidates[0].input_tokens == 4
    assert candidates[0].latency_ms >= 0

"""Independent multi-model Council capability for OMNI-X.

This is an OMNI-X service, not a GODMOD3 runtime or code import. It uses the
existing Router, credential policy and usage boundary. Standard mode is the
default and deterministic synthesis avoids an unbounded extra model call.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable, Literal

from .config import Settings
from .routing import Router

CouncilMode = Literal["standard", "council", "advanced", "research"]


@dataclass(frozen=True)
class ModelRef:
    provider: str
    model: str


@dataclass(frozen=True)
class CouncilConfig:
    mode: CouncilMode = "standard"
    models: tuple[ModelRef, ...] = ()
    max_models: int = 5
    max_concurrency: int = 3
    free_only: bool = True
    max_cost_usd: float = 0.0
    timeout_seconds: float = 120.0
    adaptive_parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class Candidate:
    provider: str
    model: str
    content: str = ""
    score: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    estimated_cost: float = 0.0
    error: str | None = None


@dataclass
class CouncilResult:
    answer: str
    candidates: list[Candidate]
    mode: CouncilMode
    total_input_tokens: int
    total_output_tokens: int
    latency_ms: float
    errors: list[str]


class CouncilService:
    """Run bounded parallel opinions through OMNI-X's existing Router."""

    def __init__(self, settings: Settings, router_factory: Callable[[Settings], Any] | None = None,
                 usage_recorder: Callable[[Candidate], None] | None = None):
        self.settings = settings
        self.router_factory = router_factory or Router
        self.usage_recorder = usage_recorder

    @staticmethod
    def model_count(config: CouncilConfig) -> int:
        requested = {"standard": 1, "council": 3, "advanced": 5}.get(config.mode, len(config.models))
        if config.mode == "research" and not config.models:
            raise ValueError("research mode requires an explicit model group")
        return min(max(1, requested), max(1, min(config.max_models, 5)))

    def run(self, messages: list[dict[str, Any]], config: CouncilConfig | None = None) -> CouncilResult:
        config = config or CouncilConfig()
        if config.free_only and (config.max_cost_usd != 0 or self.settings.allow_paid):
            raise PermissionError("FREE Council mode requires zero spending and paid inference disabled")
        if not config.free_only and (not self.settings.allow_paid or config.max_cost_usd <= 0):
            raise PermissionError("paid Council mode requires explicit paid-inference and budget settings")
        count = self.model_count(config)
        refs = list(config.models[:count])
        if not refs:
            refs = [ModelRef(self.settings.provider, self.settings.model)] * count
        elif len(refs) < count:
            refs.extend([refs[-1]] * (count - len(refs)))
        started = perf_counter()
        candidates: list[Candidate] = []
        workers = max(1, min(config.max_concurrency, count))
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="omnix-council")
        futures: list[Future[Candidate]] = [pool.submit(self._ask, ref, messages, config) for ref in refs]
        try:
            for future in as_completed(futures, timeout=max(0.1, config.timeout_seconds)):
                candidate = future.result()
                candidates.append(candidate)
                if self.usage_recorder:
                    self.usage_recorder(candidate)
        except FuturesTimeoutError:
            for future in futures:
                future.cancel()
            candidates.extend(Candidate(ref.provider, ref.model, error="CouncilTimeout")
                              for ref, future in zip(refs, futures) if not future.done())
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        candidates.sort(key=lambda item: (-item.score, item.latency_ms, item.model))
        successful = [item for item in candidates if not item.error and item.content.strip()]
        answer = self._synthesise(successful)
        return CouncilResult(answer, candidates, config.mode,
                             sum(item.input_tokens for item in candidates),
                             sum(item.output_tokens for item in candidates),
                             (perf_counter() - started) * 1000,
                             [item.error for item in candidates if item.error])

    def _ask(self, ref: ModelRef, messages: list[dict[str, Any]], config: CouncilConfig) -> Candidate:
        started = perf_counter()
        candidate = Candidate(ref.provider, ref.model)
        try:
            mode = "FREE" if config.free_only else self.settings.mode
            settings = Settings(**{**self.settings.__dict__, "provider": ref.provider, "model": ref.model,
                                   "mode": mode, "allow_paid": False if config.free_only else self.settings.allow_paid,
                                   "max_cost_usd": 0.0 if config.free_only else config.max_cost_usd})
            result, route = self.router_factory(settings).complete(messages, parameters=self._parameters(config))
            message = ((result.get("choices") or [{}])[0].get("message") or {})
            candidate.content = str(message.get("content") or "")
            usage = result.get("usage") or {}
            candidate.input_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
            candidate.output_tokens = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
            candidate.provider, candidate.model = route.provider, route.model
            candidate.score = self._evaluate(candidate.content)
        except Exception as exc:  # isolate one model failure from the Council
            candidate.error = type(exc).__name__ + ": " + str(exc)[:300]
        candidate.latency_ms = (perf_counter() - started) * 1000
        return candidate

    def _parameters(self, config: CouncilConfig) -> dict[str, Any]:
        params = dict(config.adaptive_parameters)
        params.setdefault("temperature", {"standard": 0.2, "council": 0.4, "advanced": 0.5, "research": 0.6}[config.mode])
        params.setdefault("max_tokens", 2048)
        return params

    @staticmethod
    def _evaluate(content: str) -> float:
        text = content.strip()
        if not text:
            return 0.0
        words = text.split()
        diversity = len(set(word.lower() for word in words)) / max(1, len(words))
        return min(100.0, 50.0 + min(len(words), 500) / 10.0 + diversity * 20.0)

    @staticmethod
    def _synthesise(candidates: list[Candidate]) -> str:
        # Selection is deliberate: it gives a stable answer without a fourth
        # hidden model call, extra credentials, or an unbounded spend.
        return candidates[0].content if candidates else "No Council model returned a usable response."

    def authorised_robustness_test(self, prompts: list[str], *, authorised: bool = False) -> list[CouncilResult]:
        if not authorised:
            raise PermissionError("AI robustness testing requires explicit authorisation")
        return [self.run([{"role": "user", "content": prompt}]) for prompt in prompts]

    def benchmark_models(self, prompts: list[str], config: CouncilConfig | None = None) -> list[Candidate]:
        """Run a bounded capability probe and return measured candidates."""
        if not prompts:
            raise ValueError("at least one benchmark prompt is required")
        result = self.run([{"role": "user", "content": prompts[0]}], config or CouncilConfig(mode="research"))
        return result.candidates

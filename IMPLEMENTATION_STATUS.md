# OMNI-X Implementation Status

Last reviewed: 2026-11-18

## Verified working locally

- Python package installation and `omnix` CLI entry point.
- SQLite sessions, messages, persistent key/value memory, task state, event logs, and usage records.
- OpenAI-compatible provider interface with direct adapters for OpenAI, OmniRoute, OpenRouter, Groq, Cerebras, Gemini, Mistral, Together, and DeepSeek.
- OmniRoute-first onboarding probe for local `/v1/models`, explicit free-model filtering, no-key probing, and automatic configuration only after a free model is actually advertised.
- Direct Anthropic Messages API adapter.
- Provider model listing and health-check methods.
- FREE-mode route filtering and bounded SMART-mode fallback candidates.
- Windows DPAPI credential storage; authenticated fallback encryption requires `OMNIX_MASTER_KEY` outside Windows.
- Read-only file tools, workspace path containment, approval-gated writes and commands, dangerous-command rejection.
- `SKILL.md` discovery from project and user skill directories, with prompt-relevant loading only.
- Deterministic terminal-output compression and usage/event recording hooks.
- Maximum steps, task timeout, cancellation event, structured failure state, and tool-call validation.
- Automated tests and Ubuntu GitHub Actions CI.
- Windows GitHub Actions matrix added for Python 3.11 and 3.13.
- Project-scoped OmniRoute 3.8.53 installation on Windows 11; local gateway verified at `127.0.0.1:20128`.
- Live `/v1/models` discovery returned 465 models, including nine explicitly free models; onboarding selected `auto/best-free` in FREE mode.
- Real free inference succeeded through OmniRoute and returned provider usage metadata (199 total tokens, estimated cost $0).
- Live agent tool execution succeeded in an isolated workspace with an explicit test approver; default CLI approval gating remains enabled.
- Hermes Agent execution adapter integrated from the MIT-licensed conversation-loop/tool-executor boundaries, plus the ACP/OpenAI tool-call contract, with attribution and architecture plan.
- Additive SQLite provider-health tracking records success/failure, latency, error, and counts; routing orders fallback candidates using observed health.
- A real `auto/best-free` autonomous repair completed: read project files, wrote the fix, ran tests, inspected output, retried/corrected, reran tests, and finished with all five tests passing.

## Not yet verified or complete

- No direct provider credentials were used. The live inference used OmniRoute's available free route; upstream availability and quotas remain subject to change.
- The first live request exercised fallback failures (missing Chromium and a closed UncloseAI public beta), then succeeded after installing OmniRoute's supported Chromium dependency.
- Provider pricing and free-tier metadata are not yet persisted in a model registry; estimated cost is currently recorded as zero until verified pricing is added.
- SMART routing is a bounded provider-order fallback with bounded transient retries, not yet a quota/latency/success-rate optimizer.
- Tool-result caching, prompt caching, semantic context deduplication, and reusable task-result storage are not implemented.
- MCP lifecycle management, browser automation, scheduling, multi-agent collaboration, marketplace, desktop application, and research citation workflow remain incomplete.
- Hermes's optional browser, scheduler, background-worker, and multi-agent subsystems are assessed but not yet embedded; the current integration includes the actual execution-loop boundary and tool dispatch, while preserving OMNI-X's security-scoped equivalents.
- Long-run quota/latency optimization remains future work. The live repair trace records transient provider failures and retries without hiding them; 22 automated tests currently pass after this integration, including varied non-benchmark backend tasks.
- OmniRoute upstream's changing free catalogue is treated as advisory. OMNI-X requires a reachable `/v1/models` response with explicit free metadata before auto-configuring a model.
- Hermes source remains an external inspection checkout; the adapted execution boundary is attributed in `THIRD_PARTY_NOTICES.md` and is not presented as the full Hermes backend.

## Evidence policy

Automated tests use local servers or injected test clients where needed and are labelled as such. They demonstrate code behavior, not external provider availability. Live results above record only actual provider responses, usage metadata, and failure behavior without exposing secrets. Phase 2's autonomous repair gate is now satisfied for the recorded run; the broader feature set remains active development.

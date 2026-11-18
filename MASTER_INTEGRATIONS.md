# OMNI-X — Master Integration Register

This is the decision record for repositories considered for OMNI-X. It is intended to be maintained as investigations progress and before any executable third-party integration is enabled.

## Register policy

- **Accept** means an integration or reusable component is recommended in a defined scope. It does not authorize copying code or silently installing executables.
- **Defer** means useful capability was identified, but architecture, dependency, legal, security, or maintenance work is still required.
- **Reject** means the repository is not approved for the current design; the reason is recorded so it is not reconsidered without new evidence.
- A licence shown as `NOASSERTION` or `NONE/UNKNOWN` is not treated as an open-source licence until the repository's licence files are reviewed.
- Metadata below was checked against the GitHub repository API on **2026-11-16**. Stars and timestamps are context only, not quality or security approval. A full dependency, source, release, security, and compatibility review remains required before activation.
- The target architecture remains one unified OMNI-X runtime, SQLite by default, optional integrations, explicit user approval before installation, and no mandatory paid or hosted service.

## Decision summary

| Area | Accept | Defer | Reject | Total |
|---|---:|---:|---:|---:|
| Explicit GitHub repositories | 21 | 12 | 5 | 38 |

## Repository register

| Area | Repository | Licence | Capabilities relevant to OMNI-X | Integration status | Decision and rationale |
|---|---|---|---|---|---|
| Agent framework | [hermes-agent](https://github.com/NousResearch/hermes-agent) | MIT | Autonomous agent foundation, tools, sessions, task execution, schedule grammar, worker/delegation lifecycle patterns | **Accepted — unified-runtime adapters** | OMNI-X reuses verified execution/browser/skills boundaries and `cron.jobs.parse_schedule`; worker/delegation lifecycle semantics are adapted from `persistence/workers/executions.py`, `persistence/workers/delegations.py`, `agent/managed_worker.py` and `tools/delegate_tool.py`. Hermes-owned agents are not launched as a competing runtime. |
| Agent framework | [openclaw](https://github.com/openclaw/openclaw) | MIT | Cross-platform agent actions and integrations | **Accepted — selective patterns/adapters** | Useful integration patterns, but adopting its runtime wholesale would create a competing orchestrator. |
| Agent framework | [OpenManus](https://github.com/FoundationAgents/OpenManus) | MIT | Open-ended autonomous workflows and browser-oriented execution | **Deferred — patterns only** | Good workflow ideas; defer code reuse until overlap and dependency boundaries with Hermes are proven. |
| Agent framework | [MetaGPT](https://github.com/geekan/MetaGPT) | MIT | Role-based multi-agent collaboration and software workflows | **Rejected for core runtime** | A second orchestration engine would conflict with the unified-runtime requirement; inspect ideas selectively later. |
| Agent framework | [crewAI](https://github.com/crewAIInc/crewAI) | MIT | Role-based agent teams and task delegation | **Rejected for core runtime** | Functional overlap with Hermes is too high; no reason to add a competing execution model. |
| Agent framework | [AutoGen](https://github.com/microsoft/autogen) | CC-BY-4.0 | Agent conversation and collaboration framework | **Deferred — legal/architecture review** | Potentially useful collaboration patterns, but CC-BY obligations and runtime overlap require review before reuse. |
| Agent framework | [LangGraph](https://github.com/langchain-ai/langgraph) | MIT | Durable graph-based agent workflows and recovery | **Deferred — pattern evaluation** | Strong workflow concepts, but adopting it as an engine would duplicate OMNI-X orchestration. |
| Agent framework | [browser-use](https://github.com/browser-use/browser-use) | MIT | AI browser agents and browser interaction | **Accepted — optional browser adapter** | Directly supports browser automation; keep deterministic Playwright paths ahead of AI-driven interaction. |
| Model gateway | [OmniRoute](https://github.com/cheaper-inference/OmniRoute) | MIT | Multi-provider gateway, routing, quota-aware fallback, MCP/A2A | **Accepted — optional gateway integration** | Aligns with provider routing and free-tier goals; isolate it behind OMNI-X's model registry and never silently fall back to paid inference. |
| Model gateway | [Free-LLM-API](https://github.com/golapkamal/Free-LLM-API) | MIT | Free-LLM API access | **Rejected** | Very small project with insufficient evidence of maintenance, provider reliability, or security for a core dependency; OmniRoute/provider adapters cover the need. |
| Model gateway | [LiteLLM](https://github.com/BerriAI/litellm) | NOASSERTION | OpenAI-compatible gateway, provider abstraction, cost tracking, guardrails | **Deferred — licence review** | Technically relevant, but GitHub reports no asserted SPDX licence; cannot approve code reuse until licensing and dependency obligations are clear. |
| Model gateway | [Portkey gateway](https://github.com/Portkey-AI/gateway) | MIT | LLM routing, guardrails, provider adapters | **Deferred — overlap review** | Useful reference and possible adapter, but substantial overlap with OmniRoute and the unified OMNI-X registry. |
| Token optimisation | [rtk](https://github.com/rtk-ai/rtk) | Apache-2.0 | Terminal-output reduction and token-saving CLI proxy | **Accepted — optional CLI/output adapter** | Directly supports output compression; preserve code, errors, and security-critical output without semantic distortion. |
| Token optimisation | [caveman](https://github.com/JuliusBrussee/caveman) | Apache-2.0 | Compact agent-facing command/output protocol | **Accepted — benchmarked optional adapter** | Worth testing for terminal savings, but only after repeatable quality and meaning-preservation benchmarks. |
| Token optimisation / coding | [ponytail](https://github.com/DietrichGebert/ponytail) | MIT | Coding-agent efficiency and minimal-change practices | **Accepted — skills/patterns** | Fits coding-agent goals; reuse concepts and compatible skills rather than introducing a second runtime. |
| Memory / knowledge | [graphify](https://github.com/Graphify-Labs/graphify) | Apache-2.0 | Deterministic codebase/document knowledge graph and project intelligence | **Accepted — optional project-index adapter** | Strong fit for coding-agent repository understanding; keep it optional and compatible with SQLite-first storage. |
| Memory / knowledge | [mem0](https://github.com/mem0ai/mem0) | Apache-2.0 | Persistent agent memory and memory retrieval | **Deferred — storage/dependency review** | Relevant capability, but default OMNI-X storage is SQLite and the operational/dependency footprint must be assessed first. |
| Memory / knowledge | [graphiti](https://github.com/getzep/graphiti) | Apache-2.0 | Real-time knowledge graphs for agents | **Deferred — optional backend** | Useful graph capability, but introduces a more complex graph stack and should not displace SQLite without a measured need. |
| Memory / knowledge | [LlamaIndex](https://github.com/run-llama/llama_index) | MIT | Document ingestion, indexing, retrieval, knowledge workflows | **Deferred — document adapter review** | Valuable for document workflows, but broad dependency surface and overlap with a focused OMNI-X indexer need assessment. |
| Memory / knowledge | [Chroma](https://github.com/chroma-core/chroma) | Apache-2.0 | Vector search and AI search infrastructure | **Deferred — optional backend** | Could support semantic search, but SQLite remains the default and an extra service/storage layer requires justification. |
| Skills | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | Engineering skills and agent instructions | **Accepted — skill source** | Directly named by the specification and useful for the coding agent; import only reviewed, relevant skills with permissions. |
| Skills | [anthropics/skills](https://github.com/anthropics/skills) | NONE/UNKNOWN | Public agent skills | **Deferred — licence verification** | GitHub reports no asserted licence; inspect each skill and repository licence before redistribution or installation. |
| Skills | [vercel-labs/skills](https://github.com/vercel-labs/skills) | MIT | Skill discovery, installation, and management CLI | **Accepted — skills-manager adapter** | Matches the skills marketplace requirements; sandbox, review, and permission checks remain mandatory. |
| Skills | [obra/superpowers](https://github.com/obra/superpowers) | MIT | Agentic software-development skills and methodology | **Accepted — selective skills/patterns** | Useful for coding workflows, but load only compatible skills and avoid replacing the unified runtime. |
| Multi-model intelligence | [GODMOD3](https://github.com/MSL135/GODMOD3) | AGPL-3.0 | Multi-model comparison, evaluation, and voting | **Rejected for bundled code** | AGPL obligations conflict with the current integration boundary and the feature can be implemented behind an independent interface; reconsider only after legal review. |
| Browser automation | [Playwright](https://github.com/microsoft/playwright) | Apache-2.0 | Deterministic browser navigation, interaction, screenshots, downloads, testing | **Accepted — primary browser engine** | Mature fit for reliable browser automation and testing; use AI browser control only where deterministic automation is insufficient. |
| Browser automation | [Skyvern](https://github.com/Skyvern-AI/skyvern) | AGPL-3.0 | AI-driven browser workflow automation | **Deferred — isolated optional integration** | Capability is relevant, but AGPL and overlapping browser-use functionality require a separate-process and legal/security review. |
| Desktop automation | [pywinauto](https://github.com/pywinauto/pywinauto) | BSD-3-Clause | Windows GUI automation through controls and text properties | **Accepted — Windows desktop adapter** | Direct fit for the Windows 11 first release; wrap with permissions, approval checkpoints, and audit logging. |
| Security | [TruffleHog](https://github.com/trufflesecurity/trufflehog) | AGPL-3.0 | Secret discovery and credential verification | **Deferred — external scanner adapter** | Security value is high, but AGPL and verification behavior require isolated execution, legal review, and safe handling of findings. |
| Security | [BLA](https://github.com/qybaihe/bla) | MIT | Protection against AI reverse-engineering agents; MCP/CLI security tooling | **Accepted — optional protection integration** | The specification explicitly calls for BLA as optional; never auto-enable and validate its threat model before use. |
| Security | [Grype](https://github.com/anchore/grype) | Apache-2.0 | Filesystem and container vulnerability scanning | **Accepted — vulnerability scanner adapter** | Strong fit for dependency and artifact scanning; integrate as a controlled CLI with pinned versions and report provenance. |
| Security | [Trivy](https://github.com/aquasecurity/trivy) | Apache-2.0 | Vulnerabilities, misconfigurations, secrets, SBOMs | **Accepted — scanner option** | Broad security coverage; support as an alternative to Grype rather than bundling redundant scanners by default. |
| Security | [Semgrep](https://github.com/semgrep/semgrep) | LGPL-2.1 | Pattern-based static analysis and bug finding | **Accepted — code-security adapter** | Supports coding-agent review and security checks; confirm rules, licensing, and offline behavior for the selected distribution. |
| Security | [OpenSSF Scorecard](https://github.com/ossf/scorecard) | Apache-2.0 | Open-source supply-chain security health metrics | **Accepted — provenance/repository check** | Directly supports repository discovery and dependency provenance decisions. |
| Voice / audio | [whisper.cpp](https://github.com/ggml-org/whisper.cpp) | MIT | Speech-to-text and audio transcription | **Accepted — optional STT adapter** | Useful for optional voice features; must not become a mandatory local inference dependency. |
| Voice / audio | [silero-vad](https://github.com/snakers4/silero-vad) | MIT | Voice activity detection | **Accepted — optional VAD adapter** | Fits push-to-talk and interruption handling; keep it optional and measure resource impact. |
| Voice / audio | [Piper](https://github.com/rhasspy/piper) | MIT | Local neural text-to-speech | **Rejected — current upstream archived** | GitHub marks the repository archived; do not build a new dependency on an inactive upstream. Reinvestigate a maintained successor. |
| Voice / audio | [Kokoro](https://github.com/hexgrad/kokoro) | Apache-2.0 | Text-to-speech model/runtime assets | **Accepted — optional TTS adapter** | Promising optional TTS capability with a permissive repository licence; verify model and voice-asset licences separately. |

## Named integrations without a repository URL

The specification also names AppFlowy, OpenProject, Cal.com, Chatwoot, Cap, Weknora, open-source PDF processing, and open-source document conversion tools. These are **not counted as investigated repositories** because the specification does not identify exact upstream repositories. Before adding them to the accepted set, record the canonical repository URL, exact licence, release/activity evidence, dependencies, security posture, and a scoped decision in this file.

## Current implementation boundary

The initial approved direction is:

1. Hermes-compatible unified runtime.
2. Playwright for deterministic browser automation, with browser-use as an optional AI browser adapter.
3. OmniRoute/provider adapters behind one OMNI-X model registry, with explicit free/smart/performance policy enforcement.
4. SQLite-first memory and configuration, with graph/vector backends optional and justified by benchmarks.
5. Reviewed skills from approved sources, loaded selectively and permissioned.
6. Optional security scanners and voice adapters, isolated and pinned.

No repository in this register is automatically installed, executed, copied, or treated as production-ready solely because it appears here. Every accepted integration still requires source review, dependency pinning, licence attribution, security checks, tests, and documented limitations.

## Change log

| Date | Change |
|---|---|
| 2026-11-16 | Created the initial register from the 38 explicit GitHub URLs in the OMNI-X specification and recorded GitHub API metadata plus preliminary scope decisions. |
| 2026-11-17 | Verified Hermes's upstream MIT `LICENSE`; selected compatible concepts (provider abstraction, tools, SQLite state, approvals, skills, and CLI boundaries) for an independent OMNI-X implementation. Implemented the first scoped runtime, provider adapters, SQLite sessions/memory, permission-gated tools, skills discovery, and deterministic terminal compression. |
| 2026-11-17 | Phase 2 review added provider health/model discovery methods, bounded retry and routing policy, task/event/usage state, dangerous-command rejection, Windows CI coverage, and documented live-provider limitations. |
| 2026-11-17 | OmniRoute review verified the MIT local gateway, npm/source/Docker installation paths, OpenAI-compatible `/v1` API, `/v1/models` discovery, `/v1/models/query` documentation, third-party free-tier/account requirements, and RTK→Caveman gateway compression. OMNI-X added fail-closed onboarding and avoids duplicate local compression when routed through OmniRoute. |
| 2026-11-18 | Windows 11 validation installed OmniRoute 3.8.53 project-scoped with Node 26/npm 11, started the loopback gateway, discovered 465 models/9 explicit free entries, and verified live free inference plus a permission-approved OMNI-X write-tool execution. No direct provider credential or paid route was used. |
| 2026-11-18 | Inspected Hermes revision `4ae451d4126327c871fd084e60c045dec0c85911` and MIT licence. Reused Hermes `SKILL.md` trees through an explicit allowlisted source adapter and added a thin approved bridge to Hermes `tools/browser_use_cli.py`; the unified execution adapter remains behind OMNI-X routing, SQLite and permissions. OMNI-X scheduling, worker and delegation adapters are now implemented without launching Hermes-owned agents. |
| 2026-11-18 | Added a pinned Windows installer wrapper around Hermes `scripts/install.ps1`; validated managed Python/Chromium/browser-harness installation and live browser startup, navigation, screenshot, shutdown and restart recovery. |
| 2026-11-18 | Stage 1 task lifecycle added SQLite-backed schedules, jobs and child records with restart recovery; Hermes schedule parsing is reused through an OMNI-X adapter. |
| 2026-11-18 | Stage 2 durable worker host added: detached Windows worker, atomic SQLite claims, bounded concurrency, cancellation persistence and restart reclamation. Hermes worker modules remain references/adapters, not a second runtime. |
| 2026-11-18 | Stage 3 delegation added parent/child policy inheritance, specialist roles, concurrent child jobs, aggregation and failure propagation; actual child execution remains OMNI-X `AgentRuntime`. |

## OMNI-X implementation status

The repository currently implements a functional CLI-first subset of the accepted register: Hermes-compatible agent looping, direct OpenAI-compatible and Anthropic provider calls, an OmniRoute-compatible base URL, secure local credential storage, SQLite sessions/memory/task scheduling/background/delegation state, local `SKILL.md` discovery, RTK/Caveman-inspired deterministic terminal-output compression, and approval-gated file/command/browser tools. This is an active implementation, not completion of the full specification; live multi-agent verification, MCP lifecycle management, marketplace workflows, desktop UI, and broad provider verification remain incomplete.

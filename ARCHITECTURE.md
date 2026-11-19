# OMNI-X architecture and Hermes integration plan

OMNI-X remains one unified CLI-first runtime. The Hermes integration is an
internal compatibility layer, not a second permanently running agent engine and
not a public Hermes fork.

## Assessment

Hermes Agent is MIT-licensed and currently provides a mature execution loop,
OpenAI-compatible provider routing, tool execution/approval, session persistence,
memory, skills, terminal backends, browser supervision, cron scheduling,
background review, subagent delegation, and extensive recovery/observability.
Its extension points include provider profiles, tool registries, ACP/OpenAI
bridges, persistence repositories, scheduler providers, terminal environment
providers, and delegated worker backends.

## Component-by-component plan

| Hermes capability | OMNI-X disposition | Rationale |
|---|---|---|
| Agent loop | **Integrated now:** `HermesExecutionBackend` adapted from Hermes `conversation_loop` and tool-executor boundaries | One unified loop; OMNI-X injects its Router, SQLite task/session store, and permission boundary. |
| Tool calling | **Integrated now:** Hermes-compatible XML/JSON bridge inside the execution adapter | Supports native OpenAI calls and Hermes text-call responses from OmniRoute. |
| Sessions and memory | Retain OMNI-X SQLite behind the Hermes backend | Existing schema is stable and security-scoped; Hermes persistence is broader than needed yet. |
| Skills | **Reused directly:** Hermes `skills/` and allowlisted `optional-skills/` `SKILL.md` trees through OMNI-X loader | Explicit source path and optional-skill allowlist preserve review controls. |
| Terminal execution | Retain OMNI-X containment/approval tools behind the Hermes executor boundary | Hermes execution semantics are reused without bypassing OMNI-X approvals. |
| Browser automation | **Thin adapter added:** invokes Hermes `tools/browser_use_cli.py` from the installer-managed source | Reuses Hermes browser-harness/CDP lifecycle; unavailable rather than emulated when dependencies or source are absent. |
| Scheduling/background tasks | `TaskService` adapter + managed worker host | OMNI-X SQLite owns definitions/history; Hermes `cron.jobs.parse_schedule` is reused when available, while OMNI-X executes jobs. `omnix worker` is a detached, bounded host that reclaims queued work after restart. |
| Multi-agent delegation | `TaskService` child-job adapter | Hermes worker ledger/delegation semantics are the reference; children inherit a persisted OMNI-X policy snapshot and use the unified runtime. |
| Error recovery | Adapt incrementally | Current bounded retry/health tracking is compatible; Hermes recovery is a later slice. |
| Provider interface | Reuse compatible wire contract now | OmniRoute already speaks OpenAI-compatible chat completions; no provider replacement needed. |

## Data and branding rules

No existing SQLite tables are removed. `provider_health` is additive and
backward-compatible. Public commands remain `omnix`; public product language
remains OMNI-X. Required Hermes attribution is in `THIRD_PARTY_NOTICES.md`.

## Latest source reuse assessment

The inspected Hermes source revision is `4ae451d4126327c871fd084e60c045dec0c85911`.
The current reuse boundary is explicit: the execution loop and tool dispatch are
adapted into `HermesExecutionBackend`; session/memory state remains OMNI-X SQLite;
skills are directly loaded from an operator-selected Hermes source tree; browser
automation is delegated to Hermes `browser_use_cli` through a thin approved
subprocess adapter. Stage 1 reuses Hermes `cron.jobs.parse_schedule` through
`TaskService`, while OMNI-X retains the scheduler store and executor. Terminal
execution is retained in OMNI-X because its containment and approval policy is a
security boundary.

The reproducible Windows installer pins Hermes to
`4ae451d4126327c871fd084e60c045dec0c85911` and uses Hermes's own
`scripts/install.ps1`, locked Python environment, Chromium and browser-harness
artifacts. The installed source is discovered under `%LOCALAPPDATA%\hermes`;
normal OMNI-X operation does not require a manual clone or source environment
variable.

Stage 2 adds a durable OMNI-X worker host rather than Hermes's gateway worker
process: the queue is claimed atomically in SQLite, concurrency is bounded by
`ThreadPoolExecutor`, cancellation is persisted, and the detached host exits
cleanly when no jobs or enabled schedules remain. Hermes
`persistence/workers/executions.py` and `agent/managed_worker.py` remain the
lifecycle reference; their Hermes-owned identity and storage are not imported.

Owned cancellation is process-scoped: command and Hermes-browser subprocesses
are created as OMNI-X-owned process groups, receive graceful cancellation first,
and are force-terminated only by their captured PID/tree. OmniRoute is never
matched by name and is therefore outside the cancellation boundary.

## Free-model evidence and routing

`discovery.py` treats OmniRoute's `/v1/models` response as an advisory
catalogue and only admits models with explicit free metadata (zero pricing,
free flags, or an explicit free suffix). `model_probe.py` then performs a
bounded real text probe and, when declared, a harmless read-only tool probe.
The additive SQLite `model_health` table stores upstream identity, declared
capabilities, availability, categorized failures, tool-call evidence, tokens,
and latency samples. `Router` ranks tested tool-capable free models first,
excludes tested-unavailable routes, and retains bounded free fallbacks. The
policy is intentionally conservative: an advertised model is not considered
reliable until it has been tested, and no paid route is eligible in FREE mode.

## Phase 3 desktop foundation

The Windows-first shell in `desktop/` is Tauri 2 with React, TypeScript, Vite
and Tailwind CSS. Tauri owns a supervised Python `omnix.desktop_server`
process and keeps an ephemeral IPC token in native state. The frontend invokes
native commands for backend status; it never receives provider credentials or
calls an unauthenticated local HTTP endpoint. The server binds only to
`127.0.0.1` and requires a constant-time bearer-token comparison. Chat, task,
model and settings panels remain presentation foundations until connected to
the existing SQLite/runtime APIs. Packaging the Python/Hermes/OmniRoute
dependencies as signed Windows sidecars is a later installer milestone.

The current bridge exposes authenticated chat, stop, shutdown and approval
operations through Tauri native commands. Chat calls the existing
`AgentRuntime` with the existing SQLite store. Sensitive tools synchronously
wait on a backend-owned, expiring approval record; the frontend can only submit
the scoped decision through the authenticated bridge and cannot bypass the
backend policy. The native layer owns the child process, monitors unexpected
exit and restarts only that captured process. The single-instance plugin and
fixed loopback port prevent duplicate desktop hosts.

Hosted packaging builds a PyInstaller `omnix-backend.exe` from the existing
Python package, generates the branded Tauri icons from `desktop/src/assets/omnix.svg`,
and includes the backend as an NSIS resource. Installed SQLite data remains in
the normal per-user OMNI-X data directory rather than inside the installer.

## Hermes backend assessment — 2026-11-19

The current Hermes `main` source is MIT licensed (copyright Nous Research);
required notices must remain with any redistributed substantial portions. Hermes
has a real `AIAgent` facade in `run_agent.py`, a split conversation loop under
`agent/`, provider adapters in `hermes_cli/runtime_provider.py`, a central
schema/dispatch registry in `tools/registry.py` and `model_tools.py`, SQLite
session/state persistence through `persistence_assembly.py` and
`persistence/sqlite/`, and gateway session lifecycle in `gateway/session.py`.
Its architecture is materially broader than the current OMNI-X compatibility
layer.

| Subsystem | Hermes implementation | OMNI-X comparison | Recommendation |
|---|---|---|---|
| Agent execution/tool loop | `AIAgent` plus `agent/conversation_loop.py`, `agent/turn_*.py`, `model_tools.py` | OMNI-X currently uses its own `AgentRuntime` and Hermes-compatible backend loop | Adapt Hermes `AIAgent` behind an OMNI-X executor interface after policy injection is proven; do not run both loops permanently |
| Tool calling | `tools/registry.py`, `model_tools.py`, structured schemas and toolset filtering | OMNI-X has `ToolRegistry`, schema validation, textual-call compatibility and approvals | Reuse Hermes registry/dispatch only through an OMNI-X permission adapter; retain OMNI-X deny-by-default, workspace containment and audit boundary |
| Sessions/memory | `persistence/sqlite/`, `gateway/session.py`, `agent/memory_manager.py`, `session_search` | OMNI-X SQLite schema stores sessions, messages, tasks, events, usage and health | Use an OMNI-X persistence adapter or migration layer; do not point Hermes directly at OMNI-X tables until schema/locking/identity mapping is verified |
| Skills | `skills/`, `optional-skills/`, `tools/skills_tool.py`, `hermes_cli/skills_config.py` | OMNI-X already discovers approved `SKILL.md` instructions | Reuse Hermes skill loading/read-only execution with OMNI-X allowlisting and prompt-budget limits |
| Browser | `tools/browser_use_cli.py`, `browser_session.py`, `browser_launcher.py`, CDP lifecycle | OMNI-X already has a thin Hermes browser adapter | Directly reuse the installed Hermes browser harness; wrap startup, origin, profile and shutdown permissions |
| Scheduling | `cron/jobs.py`, `cron/scheduler.py`, missed-run, ownership and delivery modules | OMNI-X has persistent schedules and task service in SQLite | Prefer Hermes scheduler semantics behind an adapter, preserving OMNI-X job IDs, provider policy and history migrations |
| Background workers | Hermes cron detached-worker/process-registry modules | OMNI-X has durable jobs, bounded workers and Windows process-tree ownership | Reuse isolated worker concepts selectively; retain OMNI-X Windows ownership/cancellation until a direct process contract is demonstrated |
| Delegation | `tools/delegate_tool.py`, delegation context and isolated child sessions | OMNI-X has parent/child jobs and inherited policies | Adapt Hermes delegation context to OMNI-X policy snapshots, spending limits and result verification; replace OMNI-X delegation only after live evidence |
| Gateway | Hermes gateway/run, RPC and platform adapters | OMNI-X desktop uses authenticated loopback and OmniRoute | Do not adopt Hermes gateway as the desktop transport; use it as a possible internal execution service later |

### Feasibility and migration plan

Direct reuse is technically feasible for Hermes's browser harness, skill loader,
tool schema/dispatch primitives, session persistence interfaces and delegation
context. Full direct replacement is not yet safe: Hermes assumes its own profile
home, SQLite schema, provider/credential resolution, tool approval lifecycle,
session identity and broad tool catalogue. Those assumptions conflict with
OMNI-X's free-first OmniRoute routing, zero-spend enforcement, content
preferences, authenticated desktop transport and backend-owned permissions.

Recommended sequence:

1. Pin a reviewed Hermes release/source package and preserve MIT notices.
2. Build a narrow `HermesExecutionAdapter` that supplies OMNI-X's provider,
   credential, permission and persistence interfaces to Hermes `AIAgent`.
3. Run deterministic tool/schema/session tests against the adapter, then a
   bounded live OmniRoute run; retain the existing runtime as rollback until
   equivalent evidence exists.
4. Migrate browser and skills first because OMNI-X already wraps those Hermes
   capabilities; then migrate session/memory with explicit SQLite migrations.
5. Migrate scheduling, workers and delegation only after identity, cancellation,
   crash recovery and inherited FREE-mode policy pass on Windows.
6. Remove duplicate OMNI-X loop code only after the adapter is the sole runtime
   for CLI and desktop and all existing commands remain compatible.

The Hermes source remains an implementation dependency under evaluation, not a
public OMNI-X brand claim and not yet the active OMNI-X execution engine.

## Hermes-primary migration branch — initial slice

Branch `feat/hermes-primary-runtime` begins the migration without changing the
working desktop runtime. `omnix hermes probe` is an explicit opt-in command
(`OMNIX_HERMES_PRIMARY=1`) that invokes the installed Hermes `run_agent.AIAgent`
through its managed Python environment and OMNI-X's configured OmniRoute URL.
The probe is restricted to explicitly free models, zero spending and no Hermes
tools, memory or persistence. It proves the actual Hermes execution loop can be
called safely through the provider boundary, while the existing OMNI-X runtime
continues to own tools, permissions and SQLite.

The next adapter must inject OMNI-X's ToolRegistry, approval callback, router
policy and SQLite session interface into Hermes before any tool-enabled primary
execution is enabled. Until that work is proven, the probe is not a replacement
engine and must not be used to claim full Hermes integration.

### Live primary-runtime evidence — 2026-11-19

The opt-in probe invoked the real installer-managed `run_agent.AIAgent` through local OmniRoute. `auto/coding:free` returned `HERMES-PRIMARY-OK` in 24,361 ms with 1,425 input, 58 output and 1,483 total tokens at estimated cost `$0`. Hermes exposed `served_model=None`, so OMNI-X records that limitation. The probe is text-only. `HermesToolAdapter` is the next compatibility boundary: Hermes-compatible schemas and calls route back into OMNI-X's existing permission-gated `ToolRegistry`. Live wiring and Hermes persistence/services remain separate validation steps.

The tool probe now implements that boundary in the managed process by replacing
only Hermes's model-facing schema and dispatch functions with the adapter. The
Hermes `AIAgent` loop remains the sole engine; OMNI-X still owns validation,
workspace containment and approvals. Deterministic execution passes, but the
available free routes have not yet produced a verified live tool call. Textual
normalization reuses `omnix.hermes_bridge.extract_tool_calls` and only accepts
its anchored, syntactically valid contracts; narrative prose is left untouched.

The controlled raw-response trace found `tool_calls=null`, `finish_reason=stop`
and empty content from the selected free model. Hermes therefore correctly had
no executable call to validate or dispatch; this is not evidence of a lost call
inside OMNI-X.

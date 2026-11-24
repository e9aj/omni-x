# OMNI-X Implementation Status

Last reviewed: 2026-11-19

## Hermes reuse assessment

- Current upstream Hermes source was inspected at `main`. It is MIT licensed
  and provides substantial reusable implementations for the agent loop,
  structured tool registry, SQLite persistence, memory providers, skills,
  browser/CDP lifecycle, cron scheduling, background process management and
  delegated workers.
- Direct replacement is not yet safe because Hermes owns assumptions about
  provider resolution, profiles, session schema/identity and approval policy.
  OMNI-X must remain authoritative for OmniRoute free-first routing, FREE mode,
  credentials, spending limits, content preferences, desktop IPC and Windows
  process ownership.
- Architecture documentation now records the component-by-component reuse
  plan. No Hermes runtime replacement was made in this change.

## Windows Code Integrity validation

- Read-only inspection of `Microsoft-Windows-CodeIntegrity/Operational`
  identified Smart App Control event 3118 and Code Integrity events 3033/3077
  for the installer. The applicable policy is `VerifiedAndReputableDesktop`,
  policy GUID `{0283ac0f-fff1-49ae-ada1-8a933130cad6}`, with policy ID
  `27555.1000.240208` and policy hash
  `2668895A5B233A80432D00D67251D7B7F52686A3FB13780F4B242C5A1F937A01`
  recorded by Windows.
- Installer evidence: `OMNI-X_0.1.0_x64-setup.exe`, SHA-256
  `CCB3F53BF60A0E7A1B3E1B70251ADBAC2E52FC2E86601773FF28C9E72E38D99E`,
  Authenticode `NotSigned`, publisher and issuer unavailable. Event 3077
  reports requested signing level 2 and validated signing level 1; event 3089
  reports zero signatures and publisher/issuer `Unknown`.
- The blocked process was the Codex-hosted `pwsh.exe` attempting to load the
  NSIS installer. Earlier events independently blocked `cargo.exe` loading
  unsigned Rust build scripts (`thiserror` and `proc-macro2`) under the same
  policy. No event proves that the packaged Tauri executable or PyInstaller
  sidecar was launched; those stages remain unvalidated here.
- No AppLocker EXE/DLL events were found for these attempts. No policy was
  disabled, modified or bypassed. Approved validation routes are an enterprise
  allowlisting decision by the device owner for the exact signed build, or an
  isolated Windows 11 test VM governed by an equivalent approved policy.
- No local VM or secondary Windows test machine is available. WSL is present but
  is not a Windows desktop environment. The Windows Actions workflow now runs a
  clean install, launches the installed OMNI-X executable, verifies the managed
  `omnix-backend.exe` process, closes the app, checks the sidecar exits, and
  performs a silent uninstall on the hosted runner. This validates packaging
  and lifecycle only; it does not provide live OmniRoute inference.

Hosted run `44538461275` installed the package with installer exit code 0,
passed an authenticated direct probe of the packaged backend and launched the
desktop with its child sidecar. It failed because the diagnostic probe process
was still included in the global post-shutdown process check. Commit `702e69d`
corrected probe cleanup and exact desktop-owned PID checks; hosted run
`44541511158` passed the complete lifecycle.

The extended integration run `44554580840` did not pass. It verified package
installation, direct packaged-backend health, desktop launch, authenticated
communication, FREE mode, model policy, preferences and stop signaling, then
failed during hosted sidecar validation: one attempt reached crash recovery
without observing a replacement child, and a later attempt observed no desktop
sidecar after launch. The smoke launch now preserves the normal inherited
Windows environment while injecting only the test IPC token; rerun is pending.

The desktop integration milestone now includes an authenticated session-read
endpoint used by the Tauri shell to restore SQLite-backed conversation messages
after restart. Hosted smoke coverage also checks unauthenticated rejection,
FREE mode (`allow_paid=false`), model policy reporting, all three content
preferences, unknown approval rejection, stop signaling and controlled
owned-backend crash recovery. Live chat remains conditional on an eligible
OmniRoute route being available on the hosted runner.

Supervisor hardening adds bounded startup retries, explicit restart-attempt
tracking, authenticated ownership checks and terminal recovery diagnostics.
Deterministic Rust state-machine tests cover missing children, unexpected exit,
live children and shutdown suppression. Hosted run `44554580840` still failed
before validation completed, so Windows crash recovery remains pending hosted
confirmation.

Run `44559468651` supplied precise supervisor evidence: captured child PID
`2852` exited while authenticated `/v1/health` continued returning PID `696`
on the same loopback port. Recovery correctly refused to spawn over that
listener but did not remove the stale same-token backend. The next correction
uses the authenticated token plus reported PID to terminate only that exact
owned orphan before spawning a replacement; hosted confirmation is pending.

The first rerun after that correction reached a replacement process but failed
at the smoke harness's immediate post-recovery health request with connection
refused. The process-name/PID observation preceded authenticated readiness.
The harness now requires the replacement PID and matching authenticated health
PID in one bounded polling loop.

Runs `44562479141` and `44562458199` reproduced the same stale-listener
pattern: initial startup passed, but recovery saw another authenticated backend
PID after termination. The harness was terminating only the named process, not
its owned Windows process tree. It now uses exact-PID `taskkill /PID /T /F`,
matching the runtime's safe orphan-cleanup boundary.

## Phase 3 desktop foundation

## Brain incremental validation

- Persistent canvas storage is implemented additively in SQLite (`brain_canvas`)
  with bounded nodes/edges, authenticated API access and a Tauri bridge. The
  desktop state loads and saves layouts; a polished visual canvas panel remains
  in progress.
- Local feature-hash semantic search is available without network access.
  Optional neural embeddings are supported only through an already-present
  `sentence-transformers` model directory with offline loading. OMNI-X never
  downloads model weights implicitly. Neural execution is not validated on this
  machine.

- Created `feat/windows-desktop` from the merged Phase 2 `main` tip.
- Tauri 2/React/TypeScript/Vite/Tailwind shell is implemented with OMNI-X
  branding, navigation sections and backend connection status.
- Authenticated loopback `omnix.desktop_server` and native Tauri status command
  are implemented; Python, credentials and SQLite remain backend-owned.
- The native layer owns the backend child, prevents duplicate instances,
  monitors crashes, restarts only the captured child, and performs graceful
  shutdown before escalation. These paths are implemented but still require a
  successful Windows binary launch test.
- Authenticated chat, stop and shutdown bridge commands call the real
  `AgentRuntime`; the bridge returns session, model and recorded usage data.
  Sensitive actions create backend-owned, scoped, 60-second approval requests
  surfaced in the native Tools & Skills UI and remain denied by default.
- Tauri single-instance protection, owned-child monitoring/restart and
  shutdown-on-window-close are implemented in the native layer, pending the
  Windows runner build for compilation validation.
- `npm install`, `npm run typecheck` and `npm run build` pass from `desktop/`.
- Python desktop bridge test passes as part of the full suite.
- Rust/Tauri compilation is not yet validated because Windows Application
  Control blocks `cargo.exe` in this environment. The installer and packaged
  backend are not complete.
- Run `44523509586` reached Rust compilation and failed because the required
  `desktop/src-tauri/icons/icon.ico` was absent. The icon is now generated from
  the tracked OMNI-X SVG before packaging. The first hosted Tauri run reached the Windows build step but failed schema
  validation; that NSIS configuration and the Tauri package-version mismatch
  are fixed in the current branch. Local compilation then reached Rust
  dependency build scripts and was blocked by the same enterprise Code
  Integrity policy (`thiserror`/`proc-macro2`, event 3077). The next hosted run
  is the authoritative compilation result. The workflow now builds a
  PyInstaller `omnix-backend.exe` sidecar and bundles it as an NSIS resource;
  hosted run `44525198666` passed and produced `OMNI-X_0.1.0_x64-setup.exe`.
  The artifact was downloaded locally, but Windows Application Control blocked
  launching the installer before installation, so clean-install launch,
  sidecar startup and persistence remain unvalidated on this host.
- Added backend-owned content preferences: Standard, Creative (default) and
  Open. They affect OMNI-X system prompting only and remain separate from tool,
  browser, terminal, filesystem and provider permissions.

## Phase 2 release-candidate classification

This is a Phase 2 development baseline, not a production-readiness claim.

### Fully validated on this Windows 11 machine

- OmniRoute free text inference with recorded model, token and latency data.
- Real read-only and isolated file-tool execution when the provider emits a supported textual call format.
- Hermes-managed browser startup, navigation, screenshot, shutdown and restart recovery through the installed backend.
- FREE-mode rejection of paid-only routes, zero estimated cost recording, credential gating and inherited child policy snapshots.
- Owned Windows subprocess cancellation boundaries and SQLite persistence/recovery.

### Deterministic validation only

- Scheduling, background workers, cancellation, recovery, permission inheritance, delegation ledger transitions and parser formats are covered by local tests.
- Native structured tool-call handling is covered by injected deterministic responses, but the selected live free model did not return a native `tool_calls` field.
- Reduced-context prompt telemetry and skill filtering are covered by deterministic tests and one bounded live measurement.

### Experimental or requiring live provider validation

- Live multi-agent AI execution through OmniRoute remains experimental. A previous attempt timed out before child creation; no passing live parent/child benchmark is claimed.
- Live tool calling depends on upstream textual formatting variability. `[list_directory]` and other non-executable prose are safely rejected.
- Provider health and fallback ranking are implemented, but reliability scores remain route-specific and require more live samples over time.

### Known external limitations

- OmniRoute's free upstream routes may return textual descriptions instead of native function calls, time out, rate-limit or change availability.
- The UncloseAI free route previously returned HTTP 401 because its public beta was closed.

### Hosted Windows recovery investigation — 2026-11-19

- Runs `44562479141` and `44562458199` failed at the same recovery assertion;
  installation, launch, authenticated health, ownership and FREE-mode checks
  passed before controlled backend termination.
- Follow-up run `6140943` isolated the packaging-specific cause: the PyInstaller
  one-file launcher PID and authenticated Python server PID are different
  Windows processes. Exact PID equality rejected the valid descendant.
- The correction validates the authenticated health PID through the Windows
  process-parent chain against the desktop-owned launcher, while rejecting
  unrelated PIDs and retaining tree-scoped termination. Launcher/backend PIDs
  are recorded separately, and the smoke harness uses the same ownership rule.
- Hosted runs `44608021605` and `44608041204` on `6637caf` passed the complete
  packaged lifecycle twice: NSIS installation, managed backend probe, desktop
  launch, authenticated health and ownership, controlled crash recovery with a
  new launcher/backend PID pair, clean shutdown and installer artifact upload.
  The hosted runner had no OmniRoute gateway, so live desktop inference and
  SQLite-after-live-chat restoration were explicitly skipped, not simulated.
- Hosted validation of `f0025b9` compiled and launched the packaged app but
  stopped in the smoke harness because its helper parameter `$pid` collided
  with PowerShell's read-only `$PID` variable. This is corrected by using
  neutral parameter names; no application failure was observed in that run.

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
- Model-level free-route health is now persisted in SQLite (`model_health`): catalogue upstream, context and declared tool capability are retained alongside tested/available state, auth/rate-limit/timeout/provider-error counts, tool-call verification, token totals, and latency samples with average/p50/p95 values. FREE routing prefers verified tool-capable models and excludes tested-unavailable models.
- A real `auto/best-free` autonomous repair completed: read project files, wrote the fix, ran tests, inspected output, retried/corrected, reran tests, and finished with all five tests passing.

## Not yet verified or complete

### Task lifecycle Stage 1

- `TaskService` adds SQLite-backed schedules, jobs and delegation records without replacing existing tables.
- One-shot ISO schedules and recurring interval schedules execute persistently; schedule advancement occurs before dispatch and running jobs recover to queued after restart.
- Evidence: Windows `py -m pytest tests/test_task_service.py` passed 3/3, covering scheduled execution, restart recovery, child lifecycle records and cancellation persistence.
- Hermes reuse: managed `cron/jobs.py::parse_schedule` is used when available. Hermes `cron/scheduler.py` is not allowed to launch a second agent runtime.

### Background workers Stage 2

- `omnix worker` runs the durable SQLite queue in a separate Windows process; `omnix background run` starts it detached.
- Atomic job claiming, bounded concurrency, cancellation state, idle shutdown and restart recovery are implemented.
- Evidence: the task-service suite is now 4/4, including a second worker host reclaiming queued work after the first host closes.
- Hermes reference modules: `persistence/workers/executions.py` for registered/running/terminal lifecycle semantics and `agent/managed_worker.py` for bounded worker supervision. OMNI-X does not start Hermes's gateway worker or a second agent runtime.
- Hard process termination is implemented for owned command/browser trees; graceful cancellation is attempted first and unrelated processes/OmniRoute are outside the scope.

### Delegation Stage 3

- Parent/child jobs, specialist roles, concurrent isolated children, failure propagation and result aggregation are implemented in `TaskService`.
- Child jobs inherit the parent's persisted `FREE`, paid-route, spending-limit and tool-policy snapshot; a child cannot select a broader policy.
- Evidence: the task-service suite is 5/5, including a Windows end-to-end schedule → background job → delegated specialist → approved file tool → persisted history → reopened SQLite check.
- Hermes reuse boundary: `tools/delegate_tool.py` and `persistence/workers/delegations.py` were inspected for lifecycle semantics, but direct invocation would construct Hermes `AIAgent` children and violate the unified-runtime requirement. OMNI-X adapts the ledger shape while executing every child through `AgentRuntime`/`TaskService`.

- No direct provider credentials were used. The live inference used OmniRoute's available free route; upstream availability and quotas remain subject to change.
- The first live request exercised fallback failures (missing Chromium and a closed UncloseAI public beta), then succeeded after installing OmniRoute's supported Chromium dependency.
- Provider pricing and free-tier metadata are not yet persisted in a model registry; estimated cost is currently recorded as zero until verified pricing is added.
- SMART routing is a bounded provider-order fallback with bounded transient retries, not yet a quota/latency/success-rate optimizer.
- Tool-result caching, prompt caching, semantic context deduplication, and reusable task-result storage are not implemented.
- The bounded `omnix models probe` command performs real minimal inference and read-only tool probes against a small subset of explicitly free OmniRoute models. It does not mark a model reliable merely because it is advertised.
- MCP lifecycle management, durable detached worker supervision, full delegated aggregation, marketplace, desktop application, and research citation workflow remain incomplete.
- Hermes browser execution and skills loading are integrated through the managed install; OMNI-X scheduling, background workers and delegated child jobs are implemented through the unified `TaskService` adapter. Hermes-owned cron/worker processes are intentionally not embedded. Live model-backed parent/child validation remains incomplete.
- Hermes skills are now directly reusable from an explicitly configured source checkout with an allowlist for optional skills. Browser automation has a thin adapter to Hermes `tools/browser_use_cli.py`; it reports unavailable when the Hermes browser runtime or dependencies are not installed.
- The pinned Hermes Windows installer is validated on this machine: commit `4ae451d4126327c871fd084e60c045dec0c85911`, managed Python 3.14, Chromium, browser-harness, Node/npm and bundled skills installed under `%LOCALAPPDATA%\\hermes`; automatic discovery works without `OMNIX_HERMES_SOURCE`.
- Opt-in live browser validation passed through the actual Hermes implementation: startup, navigation from example.com to IANA, page inspection, screenshot capture, shutdown, and clean restart recovery.
- Live `auto/best-free` inference through OmniRoute still succeeds after the adapter change: one completed call returned the recorded verification response at estimated cost `$0.00`.
- Long-run quota/latency optimization remains future work. The live repair trace records transient provider failures and retries without hiding them; the complete local suite includes task lifecycle and owned-process cancellation tests.
- OmniRoute upstream's changing free catalogue is treated as advisory. OMNI-X requires a reachable `/v1/models` response with explicit free metadata before auto-configuring a model.
- Hermes source remains an external inspection checkout; the adapted execution boundary is attributed in `THIRD_PARTY_NOTICES.md` and is not presented as the full Hermes backend.

### Hermes-primary migration branch — initial slice

- Branch `feat/hermes-primary-runtime` starts from merged desktop baseline
  `e1bfe92`.
- Current Hermes source was inspected at `edd11438db3b99558f71ca58f2b93e6c804cf20b`.
  It is MIT licensed and contains the production `run_agent.AIAgent`, split
  conversation loop, structured tool registry, SQLite session persistence,
  memory manager, browser/CDP lifecycle, cron scheduler, managed workers and
  delegation context.
- Added an opt-in `omnix hermes probe` that invokes the actual Hermes
  `AIAgent` in the installer-managed Hermes Python environment through the
  configured OmniRoute endpoint. The first slice is text-only with Hermes tools,
  memory and persistence disabled; FREE mode, explicit free-model selection and
  zero spending are enforced before process launch.
- Deterministic tests cover paid/ambiguous-route rejection and missing managed
  installation handling. Live Hermes-through-OmniRoute execution remains
  pending because OmniRoute was unavailable locally at branch creation.
- The default OMNI-X desktop/CLI runtime is unchanged. Tool, permission,
  session/memory, browser, scheduling, worker and delegation replacement remain
  gated on dedicated adapters and live evidence.
- Final validation status: hard cancellation is implemented and tested for owned command trees; browser lifecycle is live-tested, but live browser cancellation and a fully successful live parent/child OmniRoute workflow remain outstanding. Do not mark PR #2 fully integrated or merge-ready on simulated lifecycle tests.
- Tool reliability status: native calls, Hermes XML/JSON calls, explicit `Tool call: name(...)` calls and exact bare function-call text are normalized into the existing ToolRegistry; schema-invalid calls and children without tool-result events cannot be treated as successful execution.
- Latest bounded live probe (2026-11-18) found `auto/best-free` and `auto/coding:free` available for text inference through OmniRoute (`owned_by=combo`, 400000 context), but neither emitted an executable `list_directory` call in the lightweight tool probe. `unc/turboderp/Qwen3.8-27B-exl3` returned HTTP 401 because UncloseAI's public beta is closed and key registration is closed. These routes are therefore not recorded as verified tool-capable; no paid fallback is permitted.
- Controlled raw-response investigation found OmniRoute/upstream `zai-org/glm-5.2` returned `finish_reason=stop`, `tool_calls=null`, and textual `tool_call({...})` or `tool_calls: [...]` content despite a native tools request. The bridge now normalizes those exact JSON-validated formats. A real read-only invocation and an isolated write/read task then produced verified tool-result events. Native structured function calling is still not demonstrated for this free route.
- Prompt-size optimization is implemented and measured: unrelated skill-body matching was removed, explicit skill-name matching retained, per-step prompt component telemetry added, and parent/child history remains isolated. The comparable fixture reduced provider prompt usage from approximately 16k tokens per call to 2,004/2,165 and then 524 tokens after the final skill-name-only filter. A final rerun returned non-executable `[list_directory]` prose, so it was correctly not counted as a live tool success.
- Parent/child timeout budgets are now independent and bounded; child jobs persist a 60–180 second deadline and parent waits are bounded to 45–180 seconds. Live delegation remains externally blocked by the previously recorded OmniRoute timeout before child creation.

### Hermes-primary runtime — 2026-11-19

- The real installer-managed Hermes `run_agent.AIAgent` now has a bounded, opt-in probe through OmniRoute. A live FREE request using `auto/coding:free` returned `HERMES-PRIMARY-OK`: 1 API call, 1,425 input tokens, 58 output tokens, 1,483 total tokens and 24,361 ms latency at estimated cost `$0.00`. Hermes reported `served_model=None`, so no upstream identity is guessed.
- `HermesToolAdapter` maps OMNI-X schemas and calls to Hermes-compatible function contracts while retaining OMNI-X validation, workspace containment and approval gates. Deterministic tests cover schema parity, read-only execution, unknown calls and denied writes.
- Live Hermes tool dispatch through this adapter, Hermes session/memory migration, direct primary-runtime browser/skills execution, scheduling, background workers and delegated agents remain incomplete. Existing OMNI-X CLI/desktop runtime remains the default and fallback.
- The managed Hermes probe is connected at the pinned runtime's actual `model_tools.get_tool_definitions` and `model_tools.handle_function_call` boundaries, and reuses `omnix.hermes_bridge.extract_tool_calls` during Hermes response normalization for anchored textual formats. Deterministic tests prove OMNI-X schema, validation, workspace and approval enforcement. Live tool execution remains unverified: the route previously narrated a call without dispatch and bounded retries produced no verified tool event. No narrated action was counted as execution.

### Unified integrations and skills management — 2026-11-19

- Added `SkillsManager` for read-only browsing of Hermes bundled/optional and
  OMNI-X custom `SKILL.md` sources, explicit reviewed local installation,
  disabled-by-default activation, metadata inspection and CLI enable/disable.
  Unreviewed or automatically downloaded skills are not installed or executed.
- Added `CredentialManager` over the existing Windows DPAPI secret store. It
  scopes credentials by integration, supports revocation and returns metadata
  without values; child callers can be restricted to an integration allowlist.
- Current inventory: OmniRoute and direct provider adapters are implemented;
  OmniRoute free discovery is usable with the local gateway credential; direct
  providers require their own API keys/accounts. Hermes browser and bundled
  skills are installed and selectively discoverable; optional skills remain
  disabled unless explicitly allowlisted/reviewed. SQLite sessions/memory and
  task lifecycle remain OMNI-X-owned. RTK/Caveman is represented by the tested
  deterministic compressor; no external RTK/Caveman binary is bundled.
- Not yet integrated: MCP server lifecycle, OAuth flows, external API service
  adapters, Hermes-native session/memory persistence, and Hermes-primary
  scheduling/delegation. No integration is described as live without evidence.

### Hermes manager bridge — 2026-11-19

- Hermes `AIAgent` now receives only relevant, enabled and reviewed OMNI-X skill
  instructions through its supported `ephemeral_system_prompt` field. Declared
  permissions, credentials and executable dependencies are checked first;
  disabled or ineligible skills are excluded and reported as skipped metadata.
- Completed Hermes probe turns are copied to the existing OMNI-X SQLite
  `sessions`/`messages` tables through an additive `HermesSessionBridge`.
  Hermes-native session and memory stores are not yet the source of truth.
- `IntegrationRegistry` provides declarative metadata for API, MCP, skill and
  custom-tool integrations, including credentials, permissions, endpoints,
  dependencies, OS support, installation state and fail-closed health checks.

### Hermes session, memory and skill audit slice — 2026-11-19

- Added additive SQLite migrations for `hermes_session_map` and `skill_events`.
  Hermes session IDs map to existing OMNI-X sessions, while prompts and answers
  remain in the existing `sessions`/`messages` tables.
- Added `HermesMemoryAdapter`, which uses OMNI-X's existing SQLite `memories`
  table rather than introducing a second memory store.
- Skill load and skip decisions now produce audit records. Deterministic tests
  cover enabled/relevant loading, permission/dependency filtering, session
  mapping, memory persistence and audit behavior.
- Hermes-native persistence and memory managers are inspected but not yet made
  authoritative; live skill execution remains unverified.
- Controlled raw-response evidence (2026-11-19) shows one direct free-route request returned `tool_calls=null`, `finish_reason=stop`, empty content, model `deepseek-ai/deepseek-r1-distill-qwen-32b`, and 406 total tokens. There was no valid call for Hermes to lose or reject; this is recorded as a provider/model limitation. No additional parser formats were added.
- Current catalogue sweep tested four free `combo` auto routes with native tools requested. All served `deepseek-ai/deepseek-r1-distill-qwen-32b` and returned no `tool_calls`; the declared-tool UncloseAI route returned 401 because registration is closed. No reliable free tool route is currently available, so live Hermes tool execution remains unverified and testing has stopped rather than consuming repeated tokens.

### Hermes task lifecycle bridge — 2026-11-19

- Added `omnix.hermes_task_bridge`, a fail-closed boundary around Hermes
  `cron.jobs.parse_schedule`, normalising one-shot and interval syntax into the
  existing SQLite scheduler and supporting cron only when `croniter` is present.
- `TaskService` remains the sole scheduler, worker host and delegated-job
  executor. Hermes `cron.scheduler`, managed workers and `delegate_tool` are
  not started for execution.
- Deterministic task tests continue to cover recurring schedules, restart
  reclamation, cancellation, inherited FREE policy, child aggregation and
  persistence. Actual Hermes-native worker IPC, Hermes-owned cron persistence
  and live model-backed delegated children remain incomplete.

### Hermes runtime selector — 2026-11-19

- Added controlled `Settings.runtime` selection. OMNI-X remains the default;
  Hermes is explicit or can be selected through bounded `auto` fallback.
- Background and child jobs can now invoke the real Hermes `AIAgent` probe
  through `TaskService`, with inherited FREE/zero-spend/tool policy snapshots,
  persisted usage and runtime events.
- Hermes probe cancellation terminates only its owned subprocess tree.
- Deterministic tests passed for Hermes child dispatch, usage persistence,
  parent/child settlement and auto fallback. No live Hermes child inference or
  live Hermes delegation is claimed; provider/tool instability remains the
  external blocker.

### Live Hermes child validation — 2026-11-19

- OmniRoute discovery succeeded using the existing gateway credential and
  reported nine explicitly free catalogue models.
- One bounded real child attempt selected Hermes `AIAgent` for
  `auto/coding:free` under FREE/zero-spend policy. The child timed out after
  30 seconds before receiving a response; parent/child IDs and the failure are
  persisted, with no usage or tool event falsely recorded.
- Hermes is therefore not ready to become the default runtime. The existing
  OMNI-X runtime remains default and `auto` fallback remains available.

### Hermes timeout and live child validation — 2026-11-19

- Timeout configuration is split into provider request, agent execution, child
  task and parent orchestration budgets; all are positive and bounded.
- A real Hermes child completed a minimal text-only task through
  `auto/best-free` in FREE mode with zero cost. The response was
  `HERMES-TIMING-OK`, using `1,488` total tokens and `28,736 ms` probe latency.
- Instrumentation measured `13 ms` process startup and `21,969 ms` Hermes agent
  runtime. The prior 30-second failure was upstream/provider latency beyond
  the old budget, not a parent/child lifecycle failure.
- Live tool execution remains unverified. Hermes remains experimental and is
  not ready to replace the default OMNI-X runtime.

## Optional integrations — 2026-11-23

- Implemented: persistent, audited, disabled-by-default integration lifecycle
  in `IntegrationRegistry` and SQLite, including metadata-only install,
  configuration, enable/disable, revocation and gated health checks.
- Research complete: ten requested projects are recorded in
  `docs/INTEGRATION_COMPATIBILITY.md` and `MASTER_INTEGRATIONS.md`.
- Not implemented: third-party installation, OpenWhispr/VoiceStudio/Chatwoot/
  OpenClaw/OpenSEO/Cap service connections, MCP execution and media generation.

## Evidence policy

Automated tests use local servers or injected test clients where needed and are labelled as such. They demonstrate code behavior, not external provider availability. Live results above record only actual provider responses, usage metadata, and failure behavior without exposing secrets. The recorded autonomous repair gate and browser validation passed; live multi-agent completion remains an explicit outstanding gate.

## Security and compliance hardening baseline — 2026-11-19

- Added the supplied handbook unchanged under `docs/security/` and project
  operating instructions in `AGENTS.md`.
- Added a threat model, security architecture, test plan, release gate, risk
  register and incident-response runbook.
- Added CI definitions for Python SAST/dependency/licence checks, secret
  scanning, npm audit, RustSec audit and a Python SBOM artifact.
- Added deterministic regression coverage for narrative tool-call rejection,
  credential scoping/revocation and disabled-skill exclusion.
- This branch does not claim legal compliance, production readiness, complete
  prompt-injection detection, sandboxed subprocesses, live Hermes tools, or live
  desktop inference. Owner/legal decisions and external-provider assessments
  remain required.
## GODMOD3 reference and Council — 2026-11-23

- **Implemented and deterministic-tested:** independent `CouncilService` using the existing Router; Standard/Council/Advanced/Research modes; bounded parallel calls; model groups; deterministic response scoring and ranking; best-response synthesis; adaptive bounded generation parameters; token and latency aggregation; free-only and zero-spend enforcement; explicit authorisation gate for robustness testing.
- **Reviewed only:** `MSL135/GODMOD3` is an AGPL-3.0 reference architecture. No GODMOD3 source, telemetry, public dataset publishing, jailbreak prompts or safeguard-circumvention mechanisms are included.
- **Not claimed:** live multi-model provider validation, provider-specific capability benchmarks, or generative answer synthesis through an extra model. The current synthesis deliberately selects the highest-ranked verified response to avoid hidden calls and uncontrolled token use.

### Council desktop path — 2026-11-23

- **Implemented and deterministic-tested:** authenticated `/v1/council` backend endpoint, bounded model identifier validation, SQLite task/usage/event records, and a desktop Council panel exposing Standard, Council, Advanced and Research selection plus per-model score, latency and token metrics.
- **Preserved:** existing Tauri IPC authentication, OMNI-X Router/provider credentials, FREE mode, zero-spend policy and default chat runtime. The UI cannot grant tools, credentials or paid inference.
- **Not claimed:** live multi-model inference or production Windows installer validation for this new panel; those require hosted Windows CI and an eligible authorised free route.

### Desktop model catalogue — 2026-11-23

- **Implemented and deterministic-tested:** authenticated model discovery through the existing OmniRoute catalogue, explicit FREE-model display, backend-validated model selection, and a desktop Models panel showing provider ownership, free eligibility, context length and capability metadata.
- **Security boundary:** the settings endpoint applies the same default FREE configuration used by chat/discovery and rejects undiscovered paid identifiers in FREE mode. Credentials remain backend-only.
- **Not claimed:** live gateway availability or installer validation for this panel.

### Tasks and Agents desktop path — 2026-11-23

- **Implemented and deterministic-tested:** authenticated task listing, enqueue, cancellation and task-detail endpoints backed by the existing durable `TaskService`; the desktop Tasks and Agents views now display real SQLite job states and results.
- **Preserved:** one scheduler/worker authority, persisted policies, cancellation and existing runtime selection. Agent activity is a view over TaskService, not a second agent engine.
- **Not claimed:** hosted Windows packaging for this UI or live Hermes child-agent execution.

### Brain Markdown vault — 2026-11-23

- **Implemented and deterministic-tested:** local Markdown vault storage, strict path containment, `.md` type enforcement, size limits, atomic writes, note listing/reading/search, authenticated desktop note endpoints and a basic Brain note editor/list view.
- **Not claimed:** graph, canvas, embeddings, document extraction or hosted Windows installer validation for the Brain panel.

### Desktop SkillsManager path — 2026-11-23

- **Implemented and deterministic-tested:** authenticated desktop browsing of the existing SkillsManager catalogue and enable/disable operations for reviewed skills, including source, installation state, declared permissions, credentials and dependencies.
- **Preserved:** skills remain disabled by default; installation still requires explicit review in the backend; no credentials or skill contents are exposed to the frontend; Hermes/OMNI-X runtime boundaries are unchanged.
- **Not claimed:** automatic third-party skill installation, live skill execution through Hermes, or MCP lifecycle management.

### Brain graph and search path — 2026-11-23

- **Implemented and deterministic-tested:** local lexical Brain search, bounded Markdown wikilink graph generation, backlinks and deterministic document inspection (headings and counts), exposed through authenticated desktop endpoints and the Memory view.
- **Preserved:** Markdown remains the source of truth with strict vault containment and size limits; no embedding service or external document processor is invoked.
- **Not claimed:** semantic embeddings, infinite-canvas persistence, OCR/document extraction or AI-generated memory.

### MCP client boundary — 2026-11-24

- **Implemented and deterministic-tested:** a real minimal MCP JSON-RPC client for stdio and HTTP transports, initialize/tool discovery/tool execution, bounded requests, cancellation, explicit tool allowlisting, permission callbacks, revocation-ready connection management and redacted audit events.
- **Preserved:** IntegrationRegistry remains authoritative; connections require a registered MCP interface that is explicitly configured and enabled. No catalogue entry is auto-connected and credential values are supplied only by the caller boundary.
- **Not claimed:** production MCP compatibility across every transport/authentication variant, desktop connection persistence, or live third-party MCP execution.

#### MCP security hardening

- **Corrected:** stdio servers now require explicit executable authorisation; HTTP MCP endpoints require an explicit hostname allowlist, reject URL credentials and redirects, cap response size, and use generic errors without response-body leakage.
- **Corrected:** discovered tool arguments are checked against basic object schemas before permission callbacks and dispatch. Regression tests cover unauthorised commands and unallowlisted HTTP destinations.
- **Remaining risk:** remote MCP use remains unvalidated against a third-party server and still requires an owner-controlled network policy; resolver pinning is per connection, not a full enterprise network control.

### Brain attachments and recovery — 2026-11-24

- **Implemented and deterministic-tested:** bounded, atomically written Brain attachments, authenticated attachment listing, and SQLite online backup/verified restore helpers that preserve existing conversations and task data.
- **Preserved:** attachments remain inside the Brain vault; encoded payloads are size-limited and path-contained; restore writes to a separate destination and performs integrity checks.
- **Not claimed:** encrypted attachment storage, cloud synchronisation, OCR or automated backup scheduling.

### Local voice boundary — 2026-11-24

- **Implemented and deterministic-tested:** local capability detection and permission-gated adapters for optional `faster-whisper` STT, `pyttsx3` TTS and `sounddevice` input-device discovery; authenticated desktop capability reporting and a Voice screen.
- **Preserved:** no remote audio upload, no implicit package installation, bounded input/text sizes and explicit microphone/audio-output permission callbacks.
- **Not claimed:** live dictation, push-to-talk, wake-word support or audio-device execution on this host; optional engines remain unconfigured unless installed and reviewed by the owner.

### Workflow execution boundary — 2026-11-24

- **Implemented and deterministic-tested:** bounded workflow steps for agent and integration callbacks, conditional execution, dependency validation, approval steps, parallel-ready execution, retries, cancellation and audit events.
- **Preserved:** TaskService remains the durable scheduler/worker authority; the runner has no provider, credential or tool authority of its own and must receive policy-bound callbacks.
- **Not claimed:** visual workflow persistence/editor, third-party integration actions or live Hermes workflow execution.

### Desktop workflow editor — 2026-11-24

- **Implemented and deterministic-tested:** persistent workflow definitions in SQLite, authenticated desktop listing/saving, a native node-style editor with draggable nodes and step types for agent, integration and approval actions.
- **Preserved:** TaskService remains the execution authority; workflow definitions do not execute arbitrary commands or grant credentials.
- **Not claimed:** live workflow execution, visual edge editing, schedule triggers, execution-history UI or third-party integration actions.

### Brain history and conversation notes — 2026-11-24

- **Implemented and deterministic-tested:** portable Markdown note history, exclusion of history snapshots from the active vault, authenticated history listing and conversation-to-note conversion from existing SQLite sessions.
- **Preserved:** existing session data is read-only during conversion; note writes remain atomic and contained.
- **Not claimed:** AI-generated suggestions, automatic linking, PDF/DOCX extraction or OCR.

### Brain document intelligence — 2026-11-24

- **Implemented and deterministic-tested:** contained TXT/Markdown, DOCX XML and local PDF text extraction with 25 MB bounds, authenticated desktop extraction endpoint and no remote processing.
- **Preserved:** extraction is read-only and source files remain in the workspace; OCR remains opt-in and unavailable unless a reviewed local engine is installed.
- **Not claimed:** OCR, embeddings, semantic search or AI-generated memory suggestions.

#### Security correction

- Hosted Security run 95 identified Bandit `B314` on XML parsing. Replaced stdlib ElementTree with `defusedxml`, added DOCX entry/count/uncompressed-size limits, capped PDF pages and normalised parser failures. Added ZIP-bomb regression coverage; hosted revalidation is pending on the new commit.

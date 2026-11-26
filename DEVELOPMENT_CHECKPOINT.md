# OMNI-X Development Checkpoint

Updated: 2026-11-24

## Current state — Critical Product Overhaul

- Updated: 2026-11-25.
- Branch: `codex/critical-overhaul`; current starting head: `6d4529d3` (`fix: drain command output during execution`).
- The user authorised continuous implementation, build, testing, commits and pushes on the overhaul branch. Do not merge or publish a production release.
- Unrelated untracked directories `BotNest/` and `artifacts/` are preserved and must not be staged.
- The earlier alpha-candidate notes below describe historical work and are not completion evidence for the current overhaul head.

## Overhaul acceptance checklist

- [ ] Reproduce and diagnose Windows startup, chat freeze/crash and relaunch failures; validate recovery, cancellation, timeouts, offline/no-provider startup and safe process cleanup.
- [ ] Remove remaining Hermes runtime dependencies, including browser and skill paths, while preserving OMNI-X capabilities and security boundaries.
- [ ] Redesign the desktop as a compact, premium, agent-first workspace with the existing capabilities accessible and no placeholder controls.
- [ ] Implement real incremental provider/runtime streaming, tool/task events, cancellation, persistence and error recovery.
- [ ] Use the canonical website logo consistently, including app, splash, installer, favicon and release assets; provide reduced-motion branded boot screen without artificial delay.
- [ ] Measure packaged cold/warm startup, interactivity, backend readiness, idle CPU/memory and task/chat responsiveness; target interactive within three seconds.
- [ ] Build/install the Windows app and run repeated launches plus offline, no-credential, chat failure, streaming/cancel, tool/task, Brain, workflow, recovery and shutdown scenarios; capture genuine UI/splash screenshots.
- [ ] Record current-head tests, installer checksum/signing status and unresolved limitations. Continue independent work after each commit until criteria are met or remaining tasks are genuinely blocked.

## Overhaul continuation — 25 November 2026

- Resumed from `43c4a65`. Hosted CI, Windows Desktop and security workflows all passed for that head (runs `45521357856`, `45521357930`, `45521358032`); these do not validate subsequent changes.
- Added incremental OpenAI-compatible SSE parsing, fragmented tool-call reconstruction, bounded stream sizes, route failure handling after partial output, and authenticated per-request desktop polling. Only completed responses are persisted; provisional output is cleared on completion or failure. Anthropic remains one-shot; cancellation cannot interrupt a socket stalled inside a read; live provider and packaged UI testing remain outstanding. Streaming acceptance is not complete.
- The splash previously stayed visible indefinitely when backend status failed. It now dismisses after the first status result and leaves automatic status retries active; packaged offline/recovery validation remains outstanding.
- Began the compact workspace redesign with grouped navigation and revised chat layout. The frontend production build passes, but visual inspection, accessibility and complete screen-by-screen redesign remain outstanding.
- Native chat now uses the existing SkillsManager enabled-state and permission/dependency checks for new sessions, instead of injecting every matching discovered skill. Existing stored session instructions are unchanged.
- Status, approval polling and Stop now use blocking workers; quick requests have a five-second read timeout and polling is serialised. This addresses identifiable UI-thread stalls but does not establish that all reported desktop crashes are fixed.
- Local validation for this slice: full Python suite 136 passed, 3 skipped. An earlier run under concurrent Rust compilation had one 0.2-second MCP fixture startup timeout (135 passed, 3 skipped); the full rerun without compilation passed. Frontend production build and `cargo check --locked` passed (the latter used a temporary previously built sidecar solely as a required build resource). No current-head installer has been tested.
- Two generated sidecar binaries remain untracked under `desktop/src-tauri/binaries/`: automatic approval review rejected their removal. Do not stage them. The earlier unrelated `BotNest/` and `artifacts/` remain untouched.
- At `3f63b2b`, hosted CI passed (`45523632538`); Windows Desktop (`45523632669`) and security (`45523632798`) were in progress when checked. A local Chrome preview showed the Chat and Settings layouts and navigation; it is not a packaged Windows screenshot or functional inference test.
- A local loopback provider fixture now verifies that real SSE output reaches the authenticated desktop polling endpoint before completion and that the final response is persisted in the session. This is deterministic local integration coverage, not a live provider test.
- Chat polling now includes the current runtime step and tool name without tool arguments or results. Event history remains in the existing SQLite task event store; live task-event and packaged UI checks are still required.
- Skill discovery no longer scans an installed Hermes tree automatically or reads `OMNIX_HERMES_SOURCE`/`OMNIX_HERMES_SKILLS`. To continue using an inspected skill tree, point `OMNIX_SKILLS_DIR` at that directory and enable the required skills through the existing manager. No skill files or stored state are migrated or removed. The Hermes browser adapter remains outstanding.
- After the tool-status and native skill-root changes, local full Python regression passed: 138 passed, 3 skipped; the frontend production build passed. The `3f63b2b` hosted Windows job was still building its installer when checked, while its security and CI jobs had passed.
- Regenerated Tauri icons from `desktop/src/assets/website-logo.png`, added the matching desktop favicon and updated CI to use the same source. Standalone branding SVG compositions now embed an export of the same mark; their text and layout remain editable but the mark is raster, not a vector. The frontend production build passed and the SVG documents parse; packaged appearance and release asset visual review remain outstanding.
- Fixed a Memory UI approval defect: editing a suggestion no longer approves it on blur; only the Approve button sends the edited value. The frontend production build passes. An interactive packaged regression for edit-then-reject remains outstanding.
- Applied common control, approval-card, list and workflow-node styling across workspace panels; the frontend production build passes. Screen-by-screen visual and accessibility checks are still needed.
- The desktop now uses a 256px export of the canonical logo for its visible mark. Vite reports 13.28 kB for this asset versus 610.77 kB previously; this measures bundle size only, not packaged startup time.
- The startup overlay now yields to the workspace on the next animation frame rather than waiting for backend health. The status indicator continues to report readiness or failure. The production frontend builds; first-frame splash appearance and actual interactivity timings still require packaged measurement.
- Hosted Windows run `45523632669` passed installation, launch, authenticated readiness, managed sidecar crash recovery, shutdown and uninstall for `3f63b2b`; live inference was skipped because the runner had no OmniRoute service. The Windows workflow now reports installer SHA-256/signature status, first window handle and backend readiness timings, and a limited desktop-process idle sample. These do not yet measure actual interactivity, child-process resources, warm startup or the complete scenario matrix.
- Settings and chat usage now display the actual backend-reported provider and routing mode and refresh settings after a backend reconnect, rather than always labelling the route OmniRoute/FREE. Frontend production build passes; packaged reconnect verification remains open.
- The hosted Windows smoke test now always exercises a second authenticated launch, including when no inference route is present, and checks that both original and crash-replacement sidecar launchers exit. Workflow YAML and PowerShell syntax parse locally; the new smoke sequence still needs a hosted run. It does not simulate a network outage.
- Hosted CI run `45525497017` failed one Windows 3.13 scheduling test: its polling helper repeatedly reopened and initialised SQLite, and the job was completed by the final diagnostic read. The helper now uses one observer connection, a monotonic bounded deadline and a final state check. The focused TaskService suite passes locally (10 tests); hosted verification remains pending.
- Replaced the default predictable PID/time loopback token with 32 random bytes from the operating system; the explicit test override remains. `getrandom` 0.3.4 was already transitive in the lockfile and is now a direct Rust dependency. Local Rust tests passed (6/6); the existing security model and same-user process limitations still apply.
- Hosted CI for the scheduling-poll fix `06a9a21` passed (`45526108745`); the latest local full Python regression also passed (138 passed, 3 skipped). The connection banner now presents a concise retry state while retaining details in its tooltip; the frontend production build passes.
- Hosted runs for `c0514d1` passed: CI `45526386329`, security `45526386259`, Windows `45526386235`. The Windows installer SHA-256 was `09E766D0D30FD5ECE108163B536F8469F412057F19C576F085B66E31329DEC67`, signature status `NotSigned`, artifact `14983176759`. First window handle was observed at 124 ms; authenticated backend readiness at 11,567 ms including polling overhead; desktop process alone used 0.03125 CPU seconds over a two-second sample and 5,505,024 private bytes. These are hosted-runner observations, not interactive readiness or whole-app resource measurements. Live inference was unavailable. The workflow verified backend recovery, a second authenticated launch and shutdown.
- An experimental attempt to interrupt a stalled provider socket read failed its Windows regression test and was removed. Cancellation during connection establishment or a stalled provider read remains unresolved; do not claim prompt cancellation is complete.
- Hosted `bc67eee` passed CI (`45530691164`), security (`45530691289`) and Windows (`45530691270`), including no-provider chat failure followed by healthy backend, controlled sidecar recovery, relaunch and shutdown. Installer SHA-256 `2F9F2AE0838A041E051DA316AED4D3B929B79C8AE9E8FC004114AA4318022BED`, `NotSigned`, artifact `14985321456`. On that runner, first window handle was 124 ms, observed backend readiness 12,511 ms, and desktop-process-only idle sample was 0 CPU seconds over two seconds and 5,267,456 private bytes. Live inference, whole-app resource use and actual interactivity were not measured.
- Background workers now close their per-job and runtime SQLite connections, and delegation polling reuses the TaskService-owned store rather than opening a new one every 100 ms. The focused TaskService suite passed (11 tests); the full local suite passed (139 passed, 3 skipped). Other desktop endpoint connection lifetimes still need review; these changes do not establish the reported crash's root cause.
- Desktop HTTP handlers now reuse one request-owned SQLite store and close it when the request finishes; the existing shared TaskService store remains the chat authority. Endpoint and TaskService tests passed (27 tests), and the full local suite passed (140 passed, 3 skipped). Packaged stress and crash reproduction are still outstanding.
- A chat cancelled while waiting for tool approval now stops waiting and removes the pending request, without authorising the action. Targeted desktop/tool/runtime tests passed (30 tests); the full local suite passed (141 passed, 3 skipped). Background-task approvals and blocked provider reads still need cancellation review.
- Desktop TaskService now passes cancellation into background-agent and workflow approval waits; a cancelled workflow approval clears its pending request. Workflow agent steps also close their temporary SQLite store. Targeted tests passed (32 tests) and the full local suite passed (142 passed, 3 skipped). A non-desktop custom approver without cancellation support can still block; provider connection/stalled-read cancellation remains open.
- TaskService shutdown now signals active job and workflow cancellation before waiting for workers. A pending workflow approval is cleared and the run is recorded cancelled in the local regression test. Targeted workflow/task tests passed (16 tests); the full suite passed (143 passed, 3 skipped). Blocking provider connections and custom non-cancellable callbacks can still delay shutdown.
- A worker claiming a job after shutdown begins now marks it cancelled rather than executing it; the focused TaskService suite passes (14 tests).
- The Windows smoke workflow attempts a bounded native-window capture and uploads it for review. Hosted run `45579114739` for `59e24af` produced artifact `15006341615`; visual inspection showed the actual Windows Chat window with connected status and the canonical logo in the title bar and sidebar. It is not a splash capture, an interaction test or evidence for later heads.
- Hosted Linux Python 3.13 CI for `28ae158` (`45578852611`) segfaulted in the new request-store test: the test queried a SQLite connection concurrently with the handler closing it. The test now waits for handler cleanup before checking the closed connection. It passed five local repetitions and the full local suite passed (144 passed, 3 skipped). The corrected hosted run is still required; this test race is not proof of the original packaged Windows crash's cause.
- The native execution loop now lives in `agent_backend.py`, with the old `HermesExecutionBackend` import retained as a compatibility alias. Schedule-service documentation now reflects native parsing. The full local suite passed (144 passed, 3 skipped) before the added compatibility-import test, which passed with the runtime tests. The Hermes-compatible tool-call parser and optional browser adapter remain; this rename does not complete native browser replacement.
- Provider HTTP error bodies and URL-level errors are no longer copied into health records and returned errors; provider URLs reject user information, queries and fragments. This may require reconfiguring custom endpoints that used those URL components. Targeted provider/routing/runtime tests passed (18 tests) and the full local suite passed (149 passed, 3 skipped) before a cosmetic fixture-only update.
- Three local, in-process `DesktopServer` initialisations against fresh temporary data directories took 75.63, 61.46 and 66.42 ms. This excludes process launch, PyInstaller extraction, WebView, installed data and network; it does not explain the hosted packaged readiness delay or prove the three-second target.
- Hosted CI for `1e5a214` (`45584540043`) failed one Windows 3.11 mocked-chat test on its two-second client timeout. The trace does not identify the server-side delay. The functional test now uses a ten-second timeout and passes locally; a new hosted run is required. This is not an interactivity benchmark.
- Corrected desktop wording that called a fixed five-second recording “push-to-talk” and described workflows and agents using stale implementation language. The frontend production build passes; actual audio capture and live workflow execution still need packaged validation.
- The desktop supervisor now allows a 30-second monotonic startup window, polls more frequently, bounds shutdown requests, and attempts Windows tree termination only for its verified live child process before falling back to its owned handle. Rust tests pass (6/6); the new startup and forced-cleanup paths still require current-head packaged testing. This mitigates a plausible slow-start failure but does not prove the original crash cause or reduce backend readiness time.
- A Windows Rust regression now starts a dedicated hidden test process and verifies that owned-child cleanup terminates it; the local Rust suite passes (7/7). Packaged process-tree cleanup after an actual stalled backend remains unverified.
- A deterministic streaming regression now feeds fragmented provider tool-call arguments through the native Router and runtime, verifies the actual read-only tool result reaches the next provider turn, and checks final response persistence and activity notification. Provider tests pass (7 tests); the full local suite passes (150 passed, 3 skipped). Live provider and packaged streaming tests remain open.
- The desktop now records elapsed time to the first frontend animation-frame callback in the existing supervisor log, and the Windows smoke workflow reports it if available. This marker does not measure input responsiveness. Frontend build, local Rust tests (7/7), workflow YAML and PowerShell syntax checks pass; a packaged measurement for this change is pending.
- TaskService now stops scanning when shutdown starts and safely handles an executor-shutdown submission race, preserving an unclaimed job as queued for recovery. Targeted TaskService tests passed (15 tests); the full local suite passed (151 passed, 3 skipped). The earlier hosted interpreter-shutdown traceback followed a failed test, so this is a race mitigation rather than proof of a production crash cause.
- Hosted CI, security and Windows workflows passed for `7117be5` (`45585764434`, `45585764416`, `45585764485`). The current Windows smoke script also adds Brain note readback, workflow approval cancellation and note/workflow persistence across relaunch using isolated runner data. Its YAML and PowerShell syntax parse locally; these new checks await hosted execution and do not exercise the UI controls.
- Resumed from `3efe0a5` on `codex/critical-overhaul`; the older exact-next-action and starting-head notes below are historical.
- Added cancellation and deadline checks after a provider response and before each tool call. This prevents dispatch after the runtime observes cancellation or expiry; it does not interrupt a blocked provider request or an already executing tool.
- Writes, commands and the legacy browser adapter now recheck cancellation after approval, preventing an approval arriving after Stop from starting those actions. Targeted tool, runtime and browser-manager tests: 16 passed.
- Added regression coverage for cancellation during a provider request and between tool calls. Full local Python suite: 130 passed, 3 skipped. Desktop production build passed. These tests do not establish packaged desktop crash recovery or live inference.
- Enabled the existing Windows Desktop workflow on pushes to `codex/critical-overhaul`; its isolated installer smoke test must be checked on the resulting commit.
- Hosted CI for `548c3f4` passed; Windows Desktop and security runs were still in progress when last checked. A local Python 3.15 PyInstaller sidecar build succeeded, but the isolated execution probe was rejected by automatic approval review, so no local packaged health or shutdown result is claimed.
- Native browser and skill paths still depend on Hermes; chat remains one-shot. Streaming, visual redesign, branding verification, performance measurement and current-head installer scenarios remain outstanding. No overhaul checklist item is considered complete on this evidence.

## Verified at starting head

- Local history records targeted command-output drain tests at `6d4529d`; this does not diagnose the reported desktop crash or satisfy the overhaul acceptance criteria.
- Current UI still uses one-shot chat responses and an artificial three-second splash fallback; these are outstanding.
- Existing Windows packaging/lifecycle evidence in the older checkpoint is for prior alpha-candidate heads and must not be attributed to this branch.

## Verified in this session

- Handbook read from `docs/security/SOFTWARE_SECURITY_LEGAL_COMPLIANCE_HANDBOOK.pdf`.
- Python Council, Brain vault and desktop endpoint tests pass.
- React/TypeScript production build passes.
- Full Python suite passes with existing skips.
- Council endpoint uses the existing authenticated loopback bridge, SQLite task/usage/event tables, Router, credentials and FREE policy.
- Desktop model discovery and FREE-only model selection are implemented and deterministic-tested.
- Brain Markdown vault, authenticated note endpoints and basic note editor are implemented and deterministic-tested.
- Tasks and Agents screens now use authenticated TaskService queue/status/cancellation endpoints.
- SkillsManager-backed authenticated desktop endpoints now expose reviewed skill metadata and enable/disable state; installation remains an explicit reviewed backend action.
- Targeted desktop server, manager and frontend build validation passes after the SkillsManager endpoint slice.
- The existing IntegrationRegistry catalogue is now visible through an authenticated desktop Integrations view; lifecycle actions remain explicit and metadata-only.
- Brain now includes deterministic lexical search, Markdown wikilinks, backlinks and document inspection in the authenticated desktop Memory view.
- Hosted validation for `b0d2c42`: Windows Desktop run 96, CI run 196 and Security/compliance run 61 all passed.
- A real minimal MCP JSON-RPC client now passes local stdio integration tests with permission, cancellation and registry-gating controls.
- Brain attachment writes and verified SQLite backup/restore now pass deterministic tests without replacing the live database.
- Local-first voice capability reporting and permission-gated optional STT/TTS adapters now pass deterministic tests; no audio engine is claimed live.
- A bounded workflow runner now passes deterministic tests for approvals, retries, dependencies and cancellation without becoming a second scheduler.
- MCP security hardening is now regression-tested: explicit stdio command authorisation, HTTP host allowlisting/no redirects, bounded responses and basic tool-schema validation.
- Persistent workflow definitions and a draggable desktop node editor now pass authenticated endpoint and SQLite persistence tests.
- Brain note history and authenticated conversation-to-note conversion now pass deterministic tests.
- Brain document extraction now passes deterministic TXT, DOCX and PDF tests through a contained read-only path.
- Hosted Security run 95 found unsafe DOCX XML parsing; the fix uses defusedxml with ZIP/PDF resource limits and added regression coverage.
- The local Brain semantic index now persists deterministic feature-hash vectors in SQLite, ranks note results locally and is exposed through the authenticated desktop API; it is not a neural embedding service.
- Voice input now validates bounded WAV fixtures and requires an explicitly local faster-whisper model directory with offline loading; no implicit model download or remote audio upload is permitted.
- Focused Brain branch commits: `827d801` adds bounded persistent canvas storage and Tauri bridge state; `dcfaae3` adds optional offline-only neural embedding support; `e13dfd7` adds opt-in bounded OCR; `6815578` adds governed memory suggestions with explicit approval/rejection/deletion; `b2cd8c5` connects saved workflows to TaskService execution and SQLite run history.
- The Memory desktop screen now exposes semantic search, pending-memory approval/edit/reject/delete controls, draggable canvas cards, two-note connections, zoom controls and authenticated layout saving. The UI build and targeted backend tests pass.
- Brain desktop controls now include bounded canvas panning, rendered SVG connections, layout zooming and explicit local OCR inspection controls. OCR remains disabled unless the user enables it and the optional local engines are installed.
- Voice desktop controls now expose authenticated local transcription, speech output and input-device enumeration through approval-gated Tauri commands; model paths and audio files remain local and bounded. Workflow screens now expose run and persisted history controls through TaskService.
- Voice capture now supports bounded local WAV recording/voice notes through an approval-gated `sounddevice` path; official Telegram, Discord, Slack and WhatsApp HTTP adapters plus SMTP email are implemented as credential-supplied, host-policy-gated transports with local fixture tests. They remain disabled until IntegrationRegistry authorisation and credentials are provided.
- Hosted validation for `3f05632`: CI run 238 completed successfully; Windows Desktop run 117 remains in progress; Security/compliance run 103 has passed Python security, secret scan and SBOM while Rust audit remains in progress.
- A read-only Codex Security Standard scan was started for this head (scan `63065c13-7b43-4926-89b1-6610de5df075`); findings are not available yet and PR readiness is therefore still pending.
- Security scan `51568aee-c1a5-45da-b4a7-24fc81d0c69e` remains stuck in threat modelling with zero reported findings; it has not been treated as a completed review.
- Replacement consolidated-candidate scan `3e8ad111-2ab4-4794-8325-46aa6148da48` is running read-only. Full Python regression and desktop Vite build pass; local Cargo test is blocked by the OneDrive build-script output-path permission error.
- The alpha workflow-trigger commit `07689ea` exposed a Python 3.11 Windows regression: the chat test stalled while opening a second SQLite store during an HTTP request. The fix in `836116e` reuses the DesktopServer-owned TaskService store for chat persistence, with a fallback for the lightweight test server. The focused regression and full local suite pass.
- Messaging and external-service adapters now reject HTTP redirects using a no-redirect opener, preventing a validated HTTPS host from forwarding requests to another endpoint. Focused adapter tests pass.
- Hosted CI for `5f155cf` passed as run `45508609612`. Security/compliance `45508609668` and Windows Desktop `45508610044` remain in progress; no installer artifact or completed current-head security result is available yet.
- Local `npm audit --audit-level=high --omit=dev` reports zero vulnerabilities. Local `pip-audit` cannot audit the editable `omnix` distribution; the hosted security workflow is the authoritative Python dependency audit.
- Hosted security run `45510089307` passed all jobs, including Bandit after the B608 remediation, secret scanning, Rust audit and SBOM generation. Hosted CI run `45510089397` passed. Hosted Windows Desktop run `45510089296` passed installation, launch, managed sidecar startup, authenticated health, crash recovery, shutdown and silent uninstall, and uploaded artifact `14974788456`.
- Local Cargo compilation and NSIS packaging succeed when `CARGO_TARGET_DIR` is set outside OneDrive. The exact local installer for `6346f4e` is `C:\Users\jibad\AppData\Local\Temp\omnix-cargo-target-3\release\bundle\nsis\OMNI-X_0.1.0_x64-setup.exe`, 15,408,331 bytes, SHA-256 `F7AE343212CC46A5190336652FD7674AA8F2F98BD1882295F62CA87F715D07E4`, unsigned. It installed and launched locally; the owned backend exited cleanly and unauthenticated health returned 401.
- Current-head Codex Security scan `259f6166-f5a0-4216-a7e6-333bdbec6399` is running read-only against `6346f4e`; it has no final findings yet and is not represented as complete.
- Repository presentation assets are now included under `branding/`, with editable monochrome SVGs, a brand guide, contribution/community templates, accurate alpha installation/release notes and an undelivered website content package. No external website or GitHub settings were changed.
- Hosted runs for docs/branding head `061662d` (`45512694462`, `45512694558`, `45512694485`) all passed. Run `45511210844` had an intermittent failure after observing a desktop-owned sidecar while authenticated `27451/v1/health` refused connections; `ecd4195` changes the smoke test to require both ownership and authenticated readiness, with bounded polling and diagnostics.
- The Tauri icon set was regenerated from `branding/svg/omnix-symbol.svg` and wired through the existing Tauri icon configuration. Favicon, splash, README, social, Discord and release-card vectors are in `branding/svg/`.

## Known limitations

- Live multi-model inference remains unverified.
- The new Council and Brain panels have deterministic and hosted workflow coverage, but live desktop inference remains unverified.
- The SkillsManager catalogue is backend-complete for browse/enable/disable, but the desktop screen still needs its dedicated skill-list presentation.
- Optional integrations are catalogue/lifecycle interfaces only; no external service adapter, MCP connection or third-party software installation is claimed.
- Neural embeddings, infinite-canvas persistence, OCR execution and AI-generated memory remain incomplete. Local feature-hash semantic-style search is implemented and tested.
- Live microphone capture, local engine execution, push-to-talk and TTS remain unverified; deterministic permission and synthetic-WAV boundary tests pass.
- Third-party MCP connectivity and desktop connection persistence remain unverified; no external MCP endpoint was contacted.
- Full JSON Schema validation and DNS/IP pinning remain open remote-MCP risks requiring owner-controlled network policy.
- MCP now uses `jsonschema` Draft 2020-12 validation and pins resolved host addresses for the lifetime of a connection; live remote validation remains outstanding.
- Local Cargo requires an external target directory and a locally generated sidecar for packaging; no security policy was changed. The sidecar and generated spec were moved back out of the repository after packaging.
- Hermes live tool execution and delegated workflows remain experimental.
- Optional external integrations remain disabled/configuration-dependent.
- Brain graph and document extraction are implemented; persistent canvas, OCR execution and AI memory suggestions remain incomplete.
- Live Hermes tool execution and delegated workflows remain experimental.
- Voice execution controls and live inference remain incomplete rather than represented as working integrations. External adapters are executable but not live-validated and remain disabled until explicit IntegrationRegistry enablement and scoped credentials.
- Physical capture and live speech engines remain unverified; messaging adapters have no live account validation and do not connect by default. Workflow cancellation and scheduling UI remain incomplete.
- Workflow runs now have durable asynchronous start/cancel endpoints, desktop Stop/history controls and workflow-specific scheduling through TaskService.
- Workflow-specific scheduling is now exposed through an additive `schedules.workflow_id` migration, the TaskService scheduling loop, an authenticated backend endpoint and a desktop Schedule control. Existing prompt schedules remain compatible.
- Scoped external adapters now cover GitHub, Supabase, Salesforce, Google Workspace, Microsoft 365, OpenSEO, OpenProject, Cal.diy, Chatwoot, AppFlowy, Cap and ComfyUI through one bounded HTTPS/credential transport. Local fixture tests pass; no external account was contacted.
- Token optimisation now includes bounded context selection, token estimation, terminal compression and an exact-request in-process cache. A fixed local fixture measured 95.66% context reduction, 6.298 ms selection latency and 26,240 bytes peak allocation; this is not provider billing evidence.
- `codex/alpha-candidate` is a linear consolidation of the focused Brain, voice, messaging and workflow branches plus external adapters and optimisation. It has been pushed without merging into `main`.

## Exact next action

The current head is `ecd4195`; await its hosted Windows and security workflows,
complete the current-head Codex Security scan, and obtain authorised
repository write access before creating the consolidated alpha pull request.
Hosted Windows validation and an unsigned installer artifact are available for
the preceding code head; live provider inference and signed-release readiness
remain unverified.

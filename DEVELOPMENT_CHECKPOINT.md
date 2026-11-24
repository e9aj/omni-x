# OMNI-X Development Checkpoint

Updated: 2026-11-24

## Current state

- Branch: `codex/alpha-candidate`
- Head: `836116e`.
- Consolidated alpha branch is pushed at `836116e`; PR creation via the current GitHub integration returned HTTP 403 (`Resource not accessible by integration`) and requires repository write permission through another authorised route.
- Draft PR: [#7](https://github.com/e9aj/omni-x/pull/7).
- Unrelated untracked directories `BotNest/` and `artifacts/` are preserved and must not be staged.

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
- Local `cargo check` reaches the Tauri build script but is blocked because the CI-generated target-specific backend sidecar is absent from this checkout; no security policy was changed.
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

Await hosted validation for `836116e`, complete the current-head security scan,
and obtain authorised repository write access before creating the consolidated
alpha pull request. No live provider, external integration, installer artifact,
or signed release is claimed until the corresponding hosted evidence exists.

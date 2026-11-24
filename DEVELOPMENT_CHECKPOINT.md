# OMNI-X Development Checkpoint

Updated: 2026-11-23

## Current state

- Branch: `feat/modular-integrations-framework-clean`
- Head: `b0d2c42`.
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

## Known limitations

- Live multi-model inference remains unverified.
- The new Council and Brain panels have deterministic and hosted workflow coverage, but live desktop inference remains unverified.
- The SkillsManager catalogue is backend-complete for browse/enable/disable, but the desktop screen still needs its dedicated skill-list presentation.
- Optional integrations are catalogue/lifecycle interfaces only; no external service adapter, MCP connection or third-party software installation is claimed.
- Brain embeddings, infinite-canvas persistence, OCR/document extraction and AI-generated memory remain incomplete.
- Third-party MCP connectivity and desktop connection persistence remain unverified; no external MCP endpoint was contacted.
- Local `cargo check` reaches the Tauri build script but is blocked because the CI-generated target-specific backend sidecar is absent from this checkout; no security policy was changed.
- Hermes live tool execution and delegated workflows remain experimental.
- Optional external integrations remain disabled/configuration-dependent.
- Brain graph, canvas, embeddings and document extraction remain incomplete.
- Live Hermes tool execution and delegated workflows remain experimental.

## Exact next action

Add deterministic SQLite backup/recovery and attachment handling, then continue
with local-first voice capability detection without claiming unavailable audio
hardware support.

# OMNI-X Development Checkpoint

Updated: 2026-11-23

## Current state

- Branch: `feat/modular-integrations-framework-clean`
- Head: `4e37e10` before the current uncommitted desktop Council slice.
- Draft PR: [#7](https://github.com/e9aj/omni-x/pull/7).
- Unrelated untracked directories `BotNest/` and `artifacts/` are preserved and must not be staged.

## Verified in this session

- Handbook read from `docs/security/SOFTWARE_SECURITY_LEGAL_COMPLIANCE_HANDBOOK.pdf`.
- Python Council and desktop endpoint tests pass.
- React/TypeScript production build passes.
- Full Python suite passes with existing skips.
- Council endpoint uses the existing authenticated loopback bridge, SQLite task/usage/event tables, Router, credentials and FREE policy.
- Desktop model discovery and FREE-only model selection are implemented and deterministic-tested.

## Known limitations

- Live multi-model inference remains unverified.
- The new Council panel has not yet passed hosted Windows installer validation.
- Local `cargo check` reaches the Tauri build script but is blocked because the CI-generated target-specific backend sidecar is absent from this checkout; no security policy was changed.
- Hermes live tool execution and delegated workflows remain experimental.
- Optional external integrations remain disabled/configuration-dependent.

## Exact next action

Run full Python regression tests, inspect the desktop diff, commit and push the
Council/model desktop slice, then use hosted Windows CI to validate the packaged
panels before starting the next P2/P3 slice.

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
| Scheduling/background tasks | Deferred adapter | Requires lifecycle and persistence migration design. |
| Multi-agent delegation | Deferred adapter | Must map Hermes worker isolation to OMNI-X approval/audit boundaries. |
| Error recovery | Adapt incrementally | Current bounded retry/health tracking is compatible; Hermes recovery is a later slice. |
| Provider interface | Reuse compatible wire contract now | OmniRoute already speaks OpenAI-compatible chat completions; no provider replacement needed. |

## Data and branding rules

No existing SQLite tables are removed. `provider_health` is additive and
backward-compatible. Public commands remain `omnix`; public product language
remains OMNI-X. Required Hermes attribution is in `THIRD_PARTY_NOTICES.md`.

## Latest source reuse assessment

The inspected Hermes source revision is `da9c2bd62fa567ed0006866de022939ac14582cf`.
The current reuse boundary is explicit: the execution loop and tool dispatch are
adapted into `HermesExecutionBackend`; session/memory state remains OMNI-X SQLite;
skills are directly loaded from an operator-selected Hermes source tree; browser
automation is delegated to Hermes `browser_use_cli` through a thin approved
subprocess adapter. Hermes cron/scheduler, background review, and delegated
workers require their own durable lifecycle and identity model and remain
incomplete. Terminal execution is retained in OMNI-X because its containment and
approval policy is a security boundary.

The reproducible Windows installer pins Hermes to
`4ae451d4126327c871fd084e60c045dec0c85911` and uses Hermes's own
`scripts/install.ps1`, locked Python environment, Chromium and browser-harness
artifacts. The installed source is discovered under `%LOCALAPPDATA%\hermes`;
normal OMNI-X operation does not require a manual clone or source environment
variable.

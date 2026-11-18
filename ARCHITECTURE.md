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
| Skills | Retain OMNI-X reviewed `SKILL.md` loader; map to Hermes conventions later | Prevent unreviewed skill installation. |
| Terminal execution | Retain OMNI-X containment/approval tools behind the Hermes executor boundary | Hermes execution semantics are reused without bypassing OMNI-X approvals. |
| Browser automation | Deferred adapter | Requires Playwright/session policy review and adds significant dependencies. |
| Scheduling/background tasks | Deferred adapter | Requires lifecycle and persistence migration design. |
| Multi-agent delegation | Deferred adapter | Must map Hermes worker isolation to OMNI-X approval/audit boundaries. |
| Error recovery | Adapt incrementally | Current bounded retry/health tracking is compatible; Hermes recovery is a later slice. |
| Provider interface | Reuse compatible wire contract now | OmniRoute already speaks OpenAI-compatible chat completions; no provider replacement needed. |

## Data and branding rules

No existing SQLite tables are removed. `provider_health` is additive and
backward-compatible. Public commands remain `omnix`; public product language
remains OMNI-X. Required Hermes attribution is in `THIRD_PARTY_NOTICES.md`.

# OMNI-X security architecture

## Authority model

OMNI-X owns request identity, runtime selection, FREE-mode and spending policy,
credentials, permissions, task ownership, SQLite migrations, execution history,
cancellation and recovery. Hermes is an opt-in execution engine behind an
adapter; OmniRoute is a provider gateway, not a policy authority.

The existing OMNI-X runtime remains the fallback until Hermes has equivalent
live evidence. The desktop UI can request actions but cannot approve or execute
tools directly.

## Data and control flow

1. Tauri sends an authenticated, origin-checked request to the loopback Python
   backend.
2. The backend resolves the session and runtime, applies content preference and
   provider policy, and constructs the minimum prompt/tool context.
3. The selected Hermes or OMNI-X runtime receives only approved tools, relevant
   skills and scoped credentials.
4. Tool calls are schema-validated and permission-gated in the backend. Narrated
   actions are not evidence of execution.
5. Results, usage, provider/model identifiers, approvals and failures are
   recorded in SQLite without secrets.
6. Owned subprocesses are cancelled or terminated by identity and ownership;
   unrelated processes and shared infrastructure are not targeted.

## Security invariants

- Default deny for sensitive tools and integrations.
- DPAPI-backed secret values; metadata is scoped and revocable.
- No credential values in frontend state, prompts, logs, fixtures or commits.
- Workspace containment for filesystem tools.
- Child tasks inherit, and cannot expand, parent policy.
- FREE mode rejects paid/unknown routes and uses a zero spending limit.
- Skills are reviewed, explicitly enabled, dependency-checked and audited.
- Browser, terminal, filesystem, MCP and external API access are separate
  permission domains.
- Loopback authentication is not replaced by CORS/origin checks alone.

## Third-party boundaries

Hermes MIT source and notices are recorded in `THIRD_PARTY_NOTICES.md`.
OmniRoute and providers remain independently governed by their licences, terms,
retention, training, quota and residency policies. The integration register is
authoritative for accept/defer/reject decisions.

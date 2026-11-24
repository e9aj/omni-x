# Security Model

The supplied UK Software Security, Legal & Compliance Handbook is preserved at
`docs/security/SOFTWARE_SECURITY_LEGAL_COMPLIANCE_HANDBOOK.pdf` and is the
project baseline. The handbook is general guidance, not legal advice or a
compliance certification. OMNI-X-specific controls and evidence are documented
in `docs/security/`.

## Current controls

- API keys are stored with Windows DPAPI. Non-Windows fallback encryption requires an `OMNIX_MASTER_KEY`, integrity-checks ciphertext, and restricts the secret file to the owner.
- Secrets are never included in provider errors, task events, or source control.
- Relative and absolute tool paths must remain inside the configured workspace.
- File writes and command execution require an approval callback; dangerous command patterns are rejected before approval.
- Tool calls are schema-checked and malformed JSON fails the task instead of executing.
- Tasks have bounded steps and timeouts and can be cancelled.
- Skills are read as instructions only; OMNI-X does not automatically execute code discovered in a skill or repository.
- MCP stdio servers require explicit executable authorisation; HTTP MCP
  endpoints require an explicit host allowlist, reject redirects and URL
  credentials, cap response size, and validate discovered tool arguments.
- Hermes is opt-in and cannot override OMNI-X routing, credentials, permissions,
  SQLite ownership or audit policy. OmniRoute is not trusted to enforce FREE
  mode on OMNI-X's behalf.
- Child agents inherit the parent's tool, workspace, credential, spending and
  runtime restrictions and cannot broaden them.
- The desktop UI cannot execute or approve tools directly; approvals are
  enforced by the authenticated Python backend.

## Known limitations

- The fallback secret store is intended for development on platforms without DPAPI; use a platform keyring before production deployment.
- Approval is interactive in the CLI and is not yet a durable policy engine.
- Prompt-injection detection, network egress restrictions, TruffleHog integration, and sandboxed subprocess execution remain roadmap work. Dependency auditing, secret scanning, Rust auditing and SBOM generation are enforced in the hosted security workflow.
- Live Hermes tool calling and delegated execution remain experimental when the
  selected free provider emits no executable function call.
- Never run untrusted repository code through `run_command` without reviewing it and approving the operation.

Report vulnerabilities privately to the repository owner rather than opening a public issue with exploit details.

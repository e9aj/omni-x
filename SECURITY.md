# Security Model

## Current controls

- API keys are stored with Windows DPAPI. Non-Windows fallback encryption requires an `OMNIX_MASTER_KEY`, integrity-checks ciphertext, and restricts the secret file to the owner.
- Secrets are never included in provider errors, task events, or source control.
- Relative and absolute tool paths must remain inside the configured workspace.
- File writes and command execution require an approval callback; dangerous command patterns are rejected before approval.
- Tool calls are schema-checked and malformed JSON fails the task instead of executing.
- Tasks have bounded steps and timeouts and can be cancelled.
- Skills are read as instructions only; OMNI-X does not automatically execute code discovered in a skill or repository.

## Known limitations

- The fallback secret store is intended for development on platforms without DPAPI; use a platform keyring before production deployment.
- Approval is interactive in the CLI and is not yet a durable policy engine.
- Prompt-injection detection, network egress restrictions, dependency scanning, TruffleHog integration, and sandboxed subprocess execution remain roadmap work.
- Never run untrusted repository code through `run_command` without reviewing it and approving the operation.

Report vulnerabilities privately to the repository owner rather than opening a public issue with exploit details.

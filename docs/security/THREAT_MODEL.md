# OMNI-X threat model

Status: engineering assessment; not a penetration-test report or compliance
determination. Review on every material architecture, provider, skill, desktop
packaging or legal-scope change.

## Scope and trust boundaries

| Boundary | Assets crossing it | Primary controls |
|---|---|---|
| User ↔ Tauri UI | prompts, sessions, approvals, preferences | authenticated loopback IPC; backend authority; no secrets in UI |
| Tauri ↔ Python sidecar | commands, status, shutdown, tool approvals | bearer token, allowed origin, owned-process supervision, request validation |
| OMNI-X ↔ Hermes | prompts, tool schemas/results, sessions, skills | opt-in runtime selector; adapter; OMNI-X permission and credential policy |
| OMNI-X ↔ OmniRoute/providers | minimised prompts, model output, usage | FREE-mode allowlist, zero spend, routing health, bounded timeouts; provider terms review |
| Agent ↔ tools | filesystem, terminal, browser, delegation | schema validation, workspace containment, approval gates, cancellation, audit |
| Skills/MCP ↔ runtime | instructions, dependencies, credentials | reviewed provenance, explicit enablement, manifests, pinning, isolation |
| Runtime ↔ SQLite | conversations, memory, jobs, schedules, audit events | parameterised access, additive migrations, retention/backup decisions |
| Installer/update ↔ Windows | binaries, sidecar, user data | signed/provenance review, least privilege, SAC/App Control compatibility, rollback |

## Assets and threat cases

- Credentials and session tokens: disclosure, credential confusion, child-agent
  escalation. Mitigate with DPAPI, scoped access, revocation, redaction and no
  inheritance except explicit policy.
- User files and commands: path traversal, destructive execution, prompt
  injection. Mitigate with schemas, workspace containment, dangerous-command
  rejection, approvals and backend enforcement.
- Model/provider traffic: paid-route selection, data leakage, provider error
  confusion, rate-limit denial of service. Mitigate with FREE-mode fail-closed
  routing, model eligibility checks, bounded retries and minimisation.
- Persistent memory and SQLite: poisoning, cross-session leakage, corruption.
  Mitigate with ownership/session checks, provenance-aware memory, transactions,
  migration tests, backup and recovery procedures.
- Browser and external integrations: navigation to unsafe targets, credential
  misuse and data exfiltration. Mitigate with approval, scoped credentials,
  reviewed skills, origin/endpoint policy and audit events.
- Desktop/sidecar: spoofed local caller, orphaned or unrelated-process
  termination, crash-loop. Mitigate with authenticated loopback, process identity
  and ownership checks, bounded recovery and shutdown fencing.
- Scheduling, workers and delegation: runaway concurrency, child privilege
  escalation, missed cancellation. Mitigate with inherited policy, quotas,
  bounded concurrency, durable state, cancellation and failure propagation.
- Supply chain: malicious skill, dependency or installer. Mitigate with pinned
  dependencies, licence/provenance review, secret/dependency scans, SBOM and
  release evidence.

## Residual risks and verification

| Risk | Severity | Current state | Required evidence/owner |
|---|---|---|---|
| Free provider tool calling is unstable | Medium | Hermes live tool/delegation remains experimental | provider capability evidence; runtime owner |
| Prompt-injection detection is not a complete classifier | High | structural controls exist; model text is untrusted | security owner review and adversarial tests |
| Interactive approval is not a full enterprise policy engine | Medium | backend approval gates exist | product/security owner decision |
| External-provider retention/residency varies | High | not globally determined | owner/provider legal review before sensitive data |
| Installer/update signing and reputation | High | hosted packaging tested; development signing may be blocked | release owner and authorised Windows validation |
| UK GDPR/PECR applicability and retention | High | fact-dependent; not determined here | controller/legal owner assessment |

Verification is tracked in `SECURITY_TEST_PLAN.md`, `RISK_REGISTER.md` and the
implementation status. No residual risk is silently treated as accepted.

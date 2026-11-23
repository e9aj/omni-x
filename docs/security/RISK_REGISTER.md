# OMNI-X security and compliance risk register

Owner and due dates are intentionally `TBD` until the project owner supplies
the operating entity, target markets, data categories and launch scope.

| ID | Risk | Severity | Status | Mitigation/evidence | Owner |
|---|---|---|---|---|---|
| R-001 | Prompt injection causes unsafe model-directed action | High | Open | backend schemas, approvals, untrusted-content rules; adversarial tests needed | TBD |
| R-002 | Provider or model receives confidential/personal data | High | Open | prompt minimisation and provider policy; DPIA/terms review needed | TBD |
| R-003 | Child agent expands credentials or tool permissions | High | Controlled | inherited policy and isolation tests | Runtime owner |
| R-004 | Paid route selected in FREE mode | High | Controlled | explicit free catalogue, zero spend, fail-closed tests | Routing owner |
| R-005 | Malicious/unreviewed skill or MCP integration executes code | High | Controlled | review, explicit enablement, manifests, pinning; sandbox remains incomplete | Integrations owner |
| R-006 | Desktop IPC spoofing or sidecar mis-ownership | High | Controlled | bearer token, origin check, process identity/ownership tests | Desktop owner |
| R-007 | SQLite memory poisoning or retention breach | Medium | Open | session ownership and additive migrations; retention/deletion decision needed | Data owner |
| R-008 | Installer/update is unsigned or blocked by Windows reputation policy | High | Open | hosted packaging evidence; signing and authorised test environment required | Release owner |
| R-009 | Licence/attribution or model terms are incomplete | Medium | Open | register and notices; per-release review required | Legal owner |
| R-010 | No incident owner or breach process | High | Open | incident runbook added; named contacts required before launch | Owner |

No item is marked accepted merely because a mitigation exists.

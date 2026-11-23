# OMNI-X security test plan

Tests are evidence, not a certification. Use synthetic data and authorised
local/CI environments only.

## Automated gates

- Python unit/integration suite and Windows matrix.
- Frontend typecheck/build and Tauri packaging on an authorised Windows runner.
- Secret scanning; dependency vulnerability and licence checks; Python SAST;
  npm audit; Rust audit; SBOM generation.
- Security regression tests for authentication, origin checks, schema validation,
  narrative tool-call rejection, workspace containment, approval expiry,
  credential isolation/revocation, FREE-mode rejection, child-policy inheritance,
  cancellation and owned-process shutdown.

## Manual or controlled validation

- Inspect Hermes/OmniRoute revisions, licences and provider terms before changes.
- Validate installer signature/provenance, sidecar ownership, recovery and clean
  uninstall on an authorised Windows 11 environment.
- Run bounded live inference only with an eligible free route; record provider,
  model, tokens, latency, tool evidence and failure reason.
- Review SQLite migration, retention, backup/restore and sensitive-data paths.
- Review accessibility, privacy notice, PECR/cookie scope and international
  transfers when the product facts are supplied by the owner.

## Evidence rules

“Not run” and “blocked” are not passed. Simulated model responses do not prove
live inference. A narrated tool description does not prove tool execution.
Sanitise logs and never record credentials or personal data unnecessarily.

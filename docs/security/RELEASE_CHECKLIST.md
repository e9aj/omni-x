# OMNI-X security release checklist

This is a gate, not a release approval. A qualified owner must decide whether
the product may ship.

- [ ] Scope, data flows, threat model and trust boundaries reviewed.
- [ ] Authentication, origin validation and server-side authorisation tested.
- [ ] Tool schemas, path containment, approvals, cancellation and child limits tested.
- [ ] FREE mode, zero spend and paid-route exclusion verified.
- [ ] Secrets scan clean; no credentials in source, logs, fixtures or bundles.
- [ ] Dependencies, licences, Hermes/OmniRoute notices and SBOM reviewed.
- [ ] Python, TypeScript, Rust and Windows packaging checks passed.
- [ ] Installer provenance/signing, update, rollback and uninstall evidence recorded.
- [ ] SQLite migration, backup/restore, retention and deletion decisions recorded.
- [ ] Provider retention, training, residency and subprocessors reviewed for data sent.
- [ ] Privacy notice, UK GDPR/DPA 2018, PECR, accessibility and consumer scope assessed.
- [ ] Monitoring, incident contacts, disclosure route and escalation owner assigned.
- [ ] Residual risks, exceptions and owner approvals documented.

Live desktop inference and live Hermes tools must be labelled separately from
deterministic or mocked tests.

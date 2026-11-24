# Contributing to OMNI-X

Before making a substantial change, read `AGENTS.md`, `SECURITY.md` and the
security documents under `docs/security/`. Run `python -m pytest`; for desktop
changes run `npm run typecheck` and `npm run build` from `desktop/`.

Never commit credentials, private data, generated sidecars, installer binaries
or unreviewed third-party code. Keep provider routing, FREE mode, credential
storage, permissions, SQLite persistence and audit history under OMNI-X control.
Distinguish deterministic tests from live provider evidence and explain
migrations, dependencies, security impact and rollback in pull requests.

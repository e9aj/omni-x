# OMNI-X Project Boundary

This directory is the standalone OMNI-X repository. Do not mix files, credentials, configuration, or implementation work from other projects into this workspace.

- Repository: `https://github.com/e9aj/omni-x`
- Active development branch: `phase-2-real-world-testing`
- Current delivery: PR #1
- Runtime: Python CLI-first autonomous agent
- Preferred gateway: OmniRoute, when locally installed and verified
- FREE mode: must fail closed unless a model is explicitly verified as free and usable
- Credentials: use OMNI-X secure credential management only; never commit or log secrets
- Authoritative integration register: `MASTER_INTEGRATIONS.md`
- Current implementation record: `IMPLEMENTATION_STATUS.md`
- Provider instructions: `PROVIDER_SETUP.md`
- Security rules: `SECURITY.md`
- Phase roadmap: `ROADMAP.md`

All future changes in this directory must preserve the existing provider abstraction, avoid force-pushes, and distinguish mocked/local tests from live provider evidence.

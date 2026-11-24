# OMNI-X

[![CI](https://github.com/e9aj/omni-x/actions/workflows/ci.yml/badge.svg)](https://github.com/e9aj/omni-x/actions/workflows/ci.yml)
[![Security](https://github.com/e9aj/omni-x/actions/workflows/security.yml/badge.svg)](https://github.com/e9aj/omni-x/actions/workflows/security.yml)
[![Windows Desktop](https://github.com/e9aj/omni-x/actions/workflows/desktop.yml/badge.svg)](https://github.com/e9aj/omni-x/actions/workflows/desktop.yml)

![OMNI-X](branding/svg/omnix-readme-banner.svg)

> One Agent. Every AI. Infinite Possibilities.

OMNI-X is a free, open-source autonomous AI agent runtime with a Windows-first CLI. The first implementation focuses on a working, inspectable agent loop: direct provider calls, OmniRoute-compatible routing, SQLite sessions and memory, permission-gated tools, and secure local credential storage.

The Windows alpha desktop lives in [`desktop/`](desktop/README.md). It is a
Tauri 2 + React + TypeScript + Vite shell that supervises the Python runtime
through an authenticated loopback bridge. The CLI and backend remain the
authoritative policy boundary for routing, credentials, permissions, SQLite
state and audit history.

## Alpha status

The hosted Windows workflow validates NSIS installation, application launch,
managed sidecar startup, authenticated health, crash recovery, shutdown and
uninstallation. The current development installer is unsigned. Live provider
inference, Hermes tool execution/delegation and credentialed external services
are experimental or configuration-dependent and are not represented as
guaranteed features.

## Quick start

```powershell
py -m pip install -e .
omnix config set provider openai
omnix config set model gpt-4o-mini
omnix config set-key OPENAI_API_KEY
omnix chat
```

Useful commands also include `omnix run`, `omnix memory`, `omnix skills`, `omnix tools`, `omnix doctor`, and `omnix config`.

For gateway-first free setup, install and start OmniRoute separately, then run `omnix discover` followed by `omnix onboard`. OMNI-X will probe the local `/v1/models` endpoint and configure only explicitly verified free models. It will explain when the gateway requires a provider account or key; it never invents credentials or silently selects paid inference.

`omnix config set-key` reads a key without echoing it and stores it using Windows DPAPI when available. On other platforms it requires `OMNIX_MASTER_KEY` and stores an authenticated encrypted value with restrictive file permissions.

The default tool policy is read-only. Shell execution and file writes require an explicit approval at the time of use. OMNI-X never silently changes providers or falls back to paid inference.

## Development

```powershell
py -m pytest
omnix doctor
```

See [`MASTER_INTEGRATIONS.md`](MASTER_INTEGRATIONS.md) for the authoritative third-party integration register and decision record.

See [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md),
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and the
[`branding/`](branding/) guide before contributing.

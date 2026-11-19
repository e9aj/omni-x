# OMNI-X

OMNI-X is a free, open-source autonomous AI agent runtime with a Windows-first CLI. The first implementation focuses on a working, inspectable agent loop: direct provider calls, OmniRoute-compatible routing, SQLite sessions and memory, permission-gated tools, and secure local credential storage.

The Phase 3 desktop foundation lives in [`desktop/`](desktop/README.md). It is a Tauri 2 + React + TypeScript + Vite + Tailwind shell that supervises the existing Python runtime through an authenticated loopback health bridge. The CLI remains the validated primary interface while desktop chat and management surfaces are connected incrementally.

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

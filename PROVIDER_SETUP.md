# Provider Setup

OMNI-X reads credentials from its encrypted local store first, then from environment variables. Credentials are never printed or written to logs.

## Configure a provider

```powershell
omnix config set provider groq
omnix config set model llama-3.3-70b-versatile
omnix config set mode FREE
omnix config set-key GROQ_API_KEY
omnix run "List the files in this workspace"
```

Supported provider IDs are `openai`, `omniroute`, `openrouter`, `groq`, `cerebras`, `gemini`, `mistral`, `together`, `deepseek`, and `anthropic`. OpenAI-compatible providers use `/chat/completions`; Anthropic uses `/v1/messages`.

`omniroute` defaults to `http://127.0.0.1:20128/v1`. Use `omnix config set base_url URL` for a compatible gateway endpoint.

## OmniRoute onboarding

OmniRoute is the preferred gateway when installed locally. Upstream documents `npm install -g omniroute` followed by `omniroute`, a dashboard at `http://localhost:20128`, and an OpenAI-compatible API at `/v1`. OMNI-X does not install or start it silently; use the upstream installer, review its install scripts, then run:

```powershell
omnix discover
omnix onboard
```

OMNI-X probes `/v1/models` using the gateway credential if one is already configured, or without a key for a legitimate keyless local endpoint. It selects only model entries explicitly marked free (`free: true`, zero pricing metadata, or a clearly `:free` model ID). A reachable gateway with no explicit free model is reported as unavailable for FREE mode.

OmniRoute advertises a large, changing free-tier catalogue, but its upstream documentation says the catalogue is assembled from third-party accounts and that a fresh install may have no eligible keyless targets. Catalogue entries are not treated as authorization or proof of current availability. Providers such as Pollinations may be listed as no-key, while others require account setup, API keys, approval, region checks, or a payment method. OMNI-X never bypasses those requirements.

OmniRoute exposes `/v1/models` and documents `/v1/models/query` for richer model discovery. OMNI-X currently uses the standard `/v1/models` contract and preserves the gateway's routing/fallback behavior behind the existing provider abstraction.

## Modes

- `FREE` rejects providers not marked free-eligible and rejects OpenRouter models unless the model name contains `:free`.
- `SMART` tries the requested route and then a bounded set of configured free-eligible fallbacks.
- `PERFORMANCE` uses the requested route and does not silently add fallback routes.

These are safety filters, not proof that a provider's current quota or pricing is free. Verify provider terms and model eligibility before use. OMNI-X does not automatically activate paid inference.

When OmniRoute is active, OMNI-X does not apply its own RTK/Caveman-inspired terminal compression a second time; this avoids duplicate compression on gateway-managed requests. Direct providers continue to use OMNI-X's local deterministic compressor.

## Health and discovery

The provider client exposes model listing and health checks. A future CLI command will surface these directly; currently they are covered by the provider module and tests. No live connection is claimed without credentials.

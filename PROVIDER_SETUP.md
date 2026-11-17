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

## Modes

- `FREE` rejects providers not marked free-eligible and rejects OpenRouter models unless the model name contains `:free`.
- `SMART` tries the requested route and then a bounded set of configured free-eligible fallbacks.
- `PERFORMANCE` uses the requested route and does not silently add fallback routes.

These are safety filters, not proof that a provider's current quota or pricing is free. Verify provider terms and model eligibility before use. OMNI-X does not automatically activate paid inference.

## Health and discovery

The provider client exposes model listing and health checks. A future CLI command will surface these directly; currently they are covered by the provider module and tests. No live connection is claimed without credentials.

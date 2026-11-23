# OMNI-X integration compatibility review

Reviewed 23 November 2026 from the official repositories and primary project
documentation. This is an integration decision record, not permission to copy
source code or install third-party software.

| Project | Official repository | Licence | Relevant interface/capability | Windows / dependency notes | Decision |
|---|---|---|---|---|---|
| OpenClaw | [openclaw/openclaw](https://github.com/openclaw/openclaw) | MIT | Local gateway, channels, plugins and MCP client | Windows installer; Node/pnpm workspace; host tools require careful sandboxing | Defer code reuse; accept channel/API adapter patterns only |
| Open Higgsfield | No canonical repository verified; [higgsfield-ai/higgsfield](https://github.com/higgsfield-ai/higgsfield) is archived GPU orchestration | MIT metadata on archived repository | The verified repository is not a media-generation studio | Ubuntu/SSH/cloud-node requirements; archived | Reject for now; name is ambiguous and the verified repository is unrelated |
| VoiceStudio | [debpalash/VoiceStudio](https://github.com/debpalash/VoiceStudio) | AGPL-3.0 | Local speech, transcription, voice and dubbing workflows | Large local model/runtime footprint; Windows support requires project-specific validation | Defer isolated adapter pending legal approval; do not bundle code |
| OpenSEO | [every-app/open-seo](https://github.com/every-app/open-seo) | MIT | SEO audits, crawling and MCP tools | Node/pnpm; self-hosted service; some features require DataForSEO/OpenRouter credentials | Candidate optional MCP/HTTP adapter; disabled by default |
| AppFlowy | [AppFlowy-IO/AppFlowy](https://github.com/AppFlowy-IO/AppFlowy) | AGPL-3.0 | Workspace, wiki and collaboration concepts | Flutter desktop/mobile; self-hosting and service dependencies | Defer; licence and large overlap prevent bundled reuse |
| OpenWhispr | [OpenWhispr/openwhispr](https://github.com/OpenWhispr/openwhispr) | MIT | Local or BYOK speech-to-text dictation | Cross-platform; local model/GPU requirements vary; cloud mode needs user credentials | First adapter candidate; local service/CLI contract only, no automatic install |
| OpenProject | [opf/openproject](https://github.com/opf/openproject) | GPL-3.0 | REST API v3 and MCP server for project management | Ruby/PostgreSQL service; MCP requires API token or OAuth scope | Optional external MCP/API adapter only; no code bundling |
| Cal.diy | [calcom/cal.diy](https://github.com/calcom/cal.diy) | MIT | Self-hosted scheduling, REST/tRPC/OAuth ecosystem | Node, PostgreSQL and service configuration; Windows development notes exist | Defer; overlaps OMNI-X TaskService and must not create a second scheduler |
| Chatwoot | [chatwoot/chatwoot](https://github.com/chatwoot/chatwoot) | NOASSERTION in GitHub metadata | Omnichannel support, REST APIs, webhooks and integrations | Ruby/PostgreSQL/Redis service; operational footprint is substantial | Defer pending licence-file review and processor/privacy assessment |
| Cap | [CapSoftware/Cap](https://github.com/CapSoftware/Cap) | NOASSERTION in GitHub metadata | Screen capture, recording, transcripts and self-hosted storage | Tauri/Rust/Next.js; capture and media permissions are sensitive | Defer pending licence review; adapter must remain approval-gated |

## Architecture decision

OMNI-X remains the authority for runtime selection, OmniRoute routing, FREE
mode, credentials, permissions, approvals, SQLite persistence, task ownership,
cancellation and audit history. Each external project is represented as an
optional declarative registry entry. Entries are disabled and unconfigured by
default. Registration does not download, import, connect to or execute a
project.

The first implementation slice is the persistent `IntegrationRegistry` state
and audit model, plus a research catalogue. It supports explicit metadata-only
installation, configuration state, enablement, disablement, revocation and
health checks. Secret values remain in `CredentialManager`; the registry stores
only scopes and lifecycle state.

No OpenWhispr, VoiceStudio, Chatwoot, OpenClaw, OpenSEO or media-generation
runtime is claimed as executable yet. The next safe implementation is a small
OpenWhispr local-service/CLI adapter after its exact protocol and permission
boundary are verified.
## GODMOD3 reference architecture and OMNI-X Council

| Candidate | Licence | Reviewed finding | OMNI-X decision |
|---|---|---|---|
| [MSL135/GODMOD3](https://github.com/MSL135/GODMOD3) | AGPL-3.0 | Useful reference patterns for parallel model opinions, evaluation, ranking, adaptive parameters, metrics and bounded robustness research. The repository also contains behaviours OMNI-X must not inherit, including telemetry, optional public dataset publishing and dual-use safeguard-circumvention prompts. | Reference only. No GODMOD3 code is imported or bundled. |

OMNI-X now provides an independent `CouncilService` over the existing `Router`. It supports Standard (one model and the default), Council (three), Advanced (five) and Research (an explicit bounded model group), with bounded concurrency, free-only enforcement, response scoring, deterministic best-response synthesis, adaptive generation parameters, token/latency capture and an explicit authorisation gate for robustness tests. Provider credentials, FREE policy, permissions and spending limits remain OMNI-X-owned.

Local models are compatible only through an already configured OMNI-X-compatible provider route; the Council does not install or expose a new local server. Live multi-model inference remains unvalidated until an eligible authorised route is available.

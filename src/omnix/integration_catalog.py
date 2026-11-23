"""Research-backed optional integration catalogue.

The catalogue is metadata only. It does not install, import, connect to, or
enable any third-party project. Integrations remain disabled until an explicit
host action records installation, configuration and enablement.
"""

from __future__ import annotations

from .integrations import IntegrationRegistry, IntegrationSpec


CATALOGUE_VERSION = "2026-11-23"


def register_researched_integrations(registry: IntegrationRegistry) -> IntegrationRegistry:
    specs = (
        IntegrationSpec(
            "openclaw-channels", "channel-adapter", credentials=("channel token",),
            permissions=("messaging.receive", "messaging.send"),
            dependencies=("OpenClaw-compatible channel API",),
            endpoints=("https://github.com/openclaw/openclaw",),
            operating_systems=("windows", "linux", "macos"), version=CATALOGUE_VERSION,
            interface="gateway-api",
        ),
        IntegrationSpec(
            "openwhispr", "speech-to-text", credentials=("provider API key (optional)",),
            permissions=("microphone.capture", "filesystem.write:audio-cache"),
            dependencies=("OpenWhispr local service or reviewed local adapter",),
            endpoints=("https://github.com/OpenWhispr/openwhispr",),
            version=CATALOGUE_VERSION, interface="local-service-or-cli",
        ),
        IntegrationSpec(
            "voicestudio", "text-to-speech", credentials=(),
            permissions=("filesystem.read:model-assets", "audio.play"),
            dependencies=("VoiceStudio runtime",),
            endpoints=("https://github.com/debpalash/VoiceStudio",),
            version=CATALOGUE_VERSION, interface="local-service-or-cli",
        ),
        IntegrationSpec(
            "open-seo", "seo-audit", credentials=("DATAFORSEO_API_KEY", "OPENROUTER_API_KEY"),
            permissions=("network.outbound:approved-hosts", "filesystem.write:reports"),
            dependencies=("OpenSEO service or MCP endpoint",),
            endpoints=("https://github.com/every-app/open-seo",),
            version=CATALOGUE_VERSION, interface="mcp-or-http-api",
        ),
        IntegrationSpec(
            "chatwoot", "messaging", credentials=("Chatwoot API token",),
            permissions=("network.outbound:approved-hosts", "messaging.read", "messaging.send"),
            dependencies=("Chatwoot instance",),
            endpoints=("https://github.com/chatwoot/chatwoot",),
            version=CATALOGUE_VERSION, interface="rest-api-or-webhook",
        ),
        IntegrationSpec(
            "openproject", "project-management", credentials=("OpenProject API token or OAuth",),
            permissions=("network.outbound:approved-hosts", "project.read", "project.write"),
            dependencies=("OpenProject instance with API/MCP enabled",),
            endpoints=("https://github.com/opf/openproject",),
            version=CATALOGUE_VERSION, interface="rest-api-or-mcp",
        ),
        IntegrationSpec(
            "cal-diy", "scheduling", credentials=("Cal.diy OAuth credentials",),
            permissions=("network.outbound:approved-hosts", "calendar.read", "calendar.write"),
            dependencies=("Cal.diy instance and PostgreSQL",),
            endpoints=("https://github.com/calcom/cal.diy",),
            version=CATALOGUE_VERSION, interface="http-api-or-oauth",
        ),
        IntegrationSpec(
            "appflowy", "workspace", credentials=("AppFlowy service credentials",),
            permissions=("network.outbound:approved-hosts", "workspace.read", "workspace.write"),
            dependencies=("AppFlowy client/service",),
            endpoints=("https://github.com/AppFlowy-IO/AppFlowy",),
            version=CATALOGUE_VERSION, interface="service-api",
        ),
        IntegrationSpec(
            "cap", "screen-recording", credentials=("Cap service credentials (optional)",),
            permissions=("screen.capture", "microphone.capture", "filesystem.write:recordings"),
            dependencies=("Cap desktop or self-hosted service",),
            endpoints=("https://github.com/CapSoftware/Cap",),
            operating_systems=("windows", "linux", "macos"), version=CATALOGUE_VERSION,
            interface="desktop-api-or-service",
        ),
        # No canonical upstream was verified for the name supplied by the
        # request. The archived higgsfield-ai/higgsfield repository is a GPU
        # orchestration framework, not a media-generation service.
        IntegrationSpec(
            "open-higgsfield", "media-generation", credentials=("provider API key",),
            permissions=("network.outbound:approved-hosts", "filesystem.write:media"),
            dependencies=("canonical upstream and provider terms not verified",),
            endpoints=("https://github.com/higgsfield-ai/higgsfield",),
            version=CATALOGUE_VERSION, interface="unresolved",
        ),
    )
    for spec in specs:
        registry.register(spec)
    return registry

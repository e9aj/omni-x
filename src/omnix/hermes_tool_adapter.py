"""Compatibility surface between Hermes tool calls and OMNI-X permissions.

Hermes owns the model-facing execution loop, but OMNI-X remains the authority
for which tools exist and whether they may run.  This adapter is intentionally
small: it translates OpenAI/Hermes function schemas and sends calls through
the existing :class:`ToolRegistry`, including its approval and workspace
checks.  It does not import or shadow Hermes' registry handlers.
"""

from __future__ import annotations

from typing import Any


class HermesToolAdapter:
    """Expose an OMNI-X ``ToolRegistry`` using Hermes-compatible contracts."""

    def __init__(self, registry: Any):
        self.registry = registry

    def schemas(self) -> list[dict[str, Any]]:
        """Return function definitions in the format expected by Hermes."""
        return list(self.registry.schemas())

    def call(self, name: str, arguments: Any) -> str:
        """Validate, approve and execute one model call through OMNI-X."""
        if name not in self.registry.tools:
            return f"Tool error: unknown tool {name}"
        normalized = self.registry.normalize_arguments(name, arguments)
        return self.registry.call(name, normalized)

    def as_hermes_toolset(self) -> list[str]:
        """Return a stable allow-list for a Hermes session configuration."""
        return sorted(self.registry.tools)

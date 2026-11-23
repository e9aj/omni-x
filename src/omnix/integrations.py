"""Declarative registry for optional skills, tools, APIs and MCP services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class IntegrationSpec:
    name: str
    kind: str
    credentials: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    endpoints: tuple[str, ...] = ()
    operating_systems: tuple[str, ...] = ("windows", "linux", "macos")
    installed: bool = False
    health_check: Callable[[], dict] | None = field(default=None, repr=False, compare=False)


class IntegrationRegistry:
    def __init__(self):
        self._items: dict[str, IntegrationSpec] = {}

    def register(self, spec: IntegrationSpec) -> None:
        if not spec.name or not spec.kind:
            raise ValueError("integration name and kind are required")
        self._items[spec.name] = spec

    def list(self) -> list[IntegrationSpec]:
        return sorted(self._items.values(), key=lambda item: item.name)

    def get(self, name: str) -> IntegrationSpec | None:
        return self._items.get(name)

    def health(self, name: str) -> dict:
        spec = self.get(name)
        if spec is None:
            return {"name": name, "healthy": False, "error": "unknown integration"}
        if spec.health_check is None:
            return {"name": name, "healthy": bool(spec.installed), "status": "installed" if spec.installed else "not installed"}
        try:
            return {"name": name, **spec.health_check()}
        except Exception as exc:
            return {"name": name, "healthy": False, "error": type(exc).__name__}

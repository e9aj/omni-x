"""Declarative registry for optional skills, tools, APIs and MCP services."""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import replace
from typing import Any, Callable

from .store import Store


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
    version: str = ""
    interface: str = "api"
    enabled: bool = False
    revoked: bool = False
    configured: bool = False
    health_check: Callable[[], dict] | None = field(default=None, repr=False, compare=False)


class IntegrationRegistry:
    """Persistent, deny-by-default registry for optional integrations.

    Registration is declarative only. It never installs software, connects to a
    service, reads secret values, or enables an integration implicitly.
    """

    def __init__(self, store: Store | None = None):
        self._items: dict[str, IntegrationSpec] = {}
        self.store = store

    def register(self, spec: IntegrationSpec) -> None:
        if not spec.name or not spec.kind:
            raise ValueError("integration name and kind are required")
        self._items[spec.name] = spec

    def list(self) -> list[IntegrationSpec]:
        return sorted((self._view(item) for item in self._items.values()), key=lambda item: item.name)

    def get(self, name: str) -> IntegrationSpec | None:
        item = self._items.get(name)
        return self._view(item) if item else None

    def _view(self, spec: IntegrationSpec) -> IntegrationSpec:
        if self.store is None:
            return spec
        state = self.store.integration_state(spec.name)
        if not state:
            return spec
        return replace(spec, installed=bool(state["installed"]), enabled=bool(state["enabled"]),
                       revoked=bool(state["revoked"]), configured=bool(state["configured"]),
                       version=state.get("version") or spec.version)

    def _audit(self, name: str, event: str, detail: str = "") -> None:
        if self.store is not None:
            self.store.record_integration_event(name, event, detail)

    def _set(self, spec: IntegrationSpec, **changes: Any) -> IntegrationSpec:
        if self.store is None:
            self._items[spec.name] = replace(spec, **changes)
        else:
            self.store.set_integration_state(spec.name, version=spec.version, **changes)
        return self.get(spec.name) or spec

    def install(self, name: str, version: str | None = None) -> IntegrationSpec:
        spec = self._items.get(name)
        if spec is None:
            raise KeyError(f"unknown integration: {name}")
        if self.store is None:
            self._items[name] = replace(spec, installed=True, version=version or spec.version)
        else:
            self.store.set_integration_state(name, installed=True, version=version or spec.version)
        self._audit(name, "installed", "metadata only; no software was installed")
        return self.get(name) or spec

    def enable(self, name: str) -> IntegrationSpec:
        spec = self.get(name)
        if spec is None:
            raise KeyError(f"unknown integration: {name}")
        if not spec.installed:
            raise RuntimeError("integration must be explicitly installed before enablement")
        if spec.revoked:
            raise PermissionError("revoked integration cannot be enabled")
        result = self._set(spec, enabled=True)
        self._audit(name, "enabled", "explicit user action required")
        return result

    def disable(self, name: str) -> IntegrationSpec:
        spec = self.get(name)
        if spec is None:
            raise KeyError(f"unknown integration: {name}")
        result = self._set(spec, enabled=False)
        self._audit(name, "disabled")
        return result

    def revoke(self, name: str) -> IntegrationSpec:
        spec = self.get(name)
        if spec is None:
            raise KeyError(f"unknown integration: {name}")
        result = self._set(spec, enabled=False, revoked=True, configured=False)
        self._audit(name, "revoked", "credentials and connections must be re-authorised")
        return result

    def set_configured(self, name: str, configured: bool) -> IntegrationSpec:
        spec = self.get(name)
        if spec is None:
            raise KeyError(f"unknown integration: {name}")
        if not configured and spec.enabled:
            raise RuntimeError("disable integration before clearing configuration")
        result = self._set(spec, configured=configured)
        self._audit(name, "configured" if configured else "configuration-cleared")
        return result

    def health(self, name: str) -> dict:
        spec = self.get(name)
        if spec is None:
            return {"name": name, "healthy": False, "error": "unknown integration"}
        if spec.revoked:
            return {"name": name, "healthy": False, "status": "revoked"}
        if not spec.enabled:
            return {"name": name, "healthy": False, "status": "disabled"}
        if spec.health_check is None:
            return {"name": name, "healthy": False, "status": "enabled-unchecked"}
        try:
            return {"name": name, **spec.health_check()}
        except Exception as exc:
            return {"name": name, "healthy": False, "error": type(exc).__name__}

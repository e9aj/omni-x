import pytest

from omnix.integration_catalog import register_researched_integrations
from omnix.integrations import IntegrationRegistry
from omnix.store import Store


def test_researched_catalogue_is_disabled_by_default(tmp_path):
    registry = register_researched_integrations(IntegrationRegistry(Store(tmp_path / "state.sqlite3")))
    items = registry.list()
    assert len(items) == 11
    assert all(not item.enabled and not item.installed for item in items)
    assert registry.health("openwhispr")["status"] == "disabled"
    assert registry.get("godmod3-council-reference").enabled is False


def test_integration_lifecycle_is_explicit_and_audited(tmp_path):
    store = Store(tmp_path / "state.sqlite3")
    registry = register_researched_integrations(IntegrationRegistry(store))
    with pytest.raises(RuntimeError):
        registry.enable("openwhispr")
    registry.install("openwhispr", version="test-version")
    registry.set_configured("openwhispr", True)
    enabled = registry.enable("openwhispr")
    assert enabled.enabled and enabled.configured
    assert registry.health("openwhispr")["status"] == "enabled-unchecked"
    revoked = registry.revoke("openwhispr")
    assert revoked.revoked and not revoked.enabled
    assert registry.health("openwhispr")["status"] == "revoked"
    assert [event["event"] for event in store.integration_events("openwhispr")] == [
        "installed", "configured", "enabled", "revoked"
    ]


def test_disabled_integration_does_not_call_health_check(tmp_path):
    called = []
    registry = IntegrationRegistry(Store(tmp_path / "state.sqlite3"))
    from omnix.integrations import IntegrationSpec
    registry.register(IntegrationSpec("local", "service", health_check=lambda: called.append(True) or {"healthy": True}))
    assert registry.health("local")["status"] == "disabled"
    assert called == []

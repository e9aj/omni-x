from pathlib import Path
from types import SimpleNamespace

from omnix.credentials import CredentialManager
from omnix.integrations import IntegrationRegistry, IntegrationSpec
from omnix.hermes_memory import HermesMemoryAdapter
from omnix.hermes_browser import HermesBrowserAdapter
from omnix.hermes_sessions import HermesSessionBridge
from omnix.skills_manager import SkillsManager
from omnix.store import Store


def test_enabled_skill_context_is_relevant_and_dependency_checked(tmp_path: Path):
    root = tmp_path / "workspace"
    skill = root / ".omnix" / "skills" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("description: Review\npermissions: filesystem.read\nReview safely.", encoding="utf-8")
    events = []
    manager = SkillsManager(root, audit=lambda *item: events.append(item))
    manager.state_path = tmp_path / "skills-state.json"
    manager.state = {"review": {"enabled": True, "installed": True}}
    text, loaded, skipped = manager.relevant_context("please review this", allowed_permissions={"filesystem.read"}, credentials=CredentialManager(tmp_path / "creds.json"))
    assert "Review safely." in text
    assert loaded == ["review"]
    assert skipped == []
    assert events == [("review", "loaded", "relevant enabled skill")]


def test_integration_registry_is_declarative_and_health_is_fail_closed():
    registry = IntegrationRegistry()
    registry.register(IntegrationSpec("demo", "api", credentials=("DEMO_KEY",), permissions=("network.read",)))
    assert registry.health("demo")["healthy"] is False
    assert registry.health("missing")["healthy"] is False


def test_hermes_session_memory_adapters_preserve_sqlite(tmp_path: Path):
    store = Store(tmp_path / "omnix.sqlite3")
    sessions = HermesSessionBridge(store)
    session_id = sessions.begin()
    sessions.record_turn(session_id, "remember this", "stored")
    sessions.bind(session_id, "hermes-session-1")
    memory = HermesMemoryAdapter(store)
    memory.remember("test-key", "test-value")
    assert sessions.history(session_id)[-1]["content"] == "stored"
    assert store.hermes_session(session_id) == "hermes-session-1"
    assert memory.recall("test-key")[0]["value"] == "test-value"
    assert store.skill_events() == []
    store.db.close()


def test_hermes_browser_adapter_requires_omnix_approval(tmp_path: Path):
    source = tmp_path / "hermes"
    (source / "tools").mkdir(parents=True)
    (source / "tools" / "browser_use_cli.py").write_text("", encoding="utf-8")
    adapter = HermesBrowserAdapter(source=source, approver=lambda _: False)
    assert "denied" in adapter.execute("open('https://example.com')").lower()

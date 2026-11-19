from pathlib import Path
from types import SimpleNamespace

from omnix.credentials import CredentialManager
from omnix.integrations import IntegrationRegistry, IntegrationSpec
from omnix.skills_manager import SkillsManager


def test_enabled_skill_context_is_relevant_and_dependency_checked(tmp_path: Path):
    root = tmp_path / "workspace"
    skill = root / ".omnix" / "skills" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("description: Review\npermissions: filesystem.read\nReview safely.", encoding="utf-8")
    manager = SkillsManager(root)
    manager.state_path = tmp_path / "skills-state.json"
    manager.state = {"review": {"enabled": True, "installed": True}}
    text, loaded, skipped = manager.relevant_context("please review this", allowed_permissions={"filesystem.read"}, credentials=CredentialManager(tmp_path / "creds.json"))
    assert "Review safely." in text
    assert loaded == ["review"]
    assert skipped == []


def test_integration_registry_is_declarative_and_health_is_fail_closed():
    registry = IntegrationRegistry()
    registry.register(IntegrationSpec("demo", "api", credentials=("DEMO_KEY",), permissions=("network.read",)))
    assert registry.health("demo")["healthy"] is False
    assert registry.health("missing")["healthy"] is False

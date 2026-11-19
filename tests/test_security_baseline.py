from pathlib import Path

from omnix.credentials import CredentialManager
from omnix.hermes_bridge import extract_tool_calls
from omnix.skills_manager import SkillsManager


def test_narrative_action_is_not_executable():
    calls, _ = extract_tool_calls("I will read_file(path='secret.txt')")
    assert calls == []


def test_credentials_are_scoped_and_revocable(tmp_path: Path):
    manager = CredentialManager(tmp_path / "metadata.json")
    manager.put("provider-a", "API_KEY", "synthetic-secret")
    assert manager.get("provider-a", "API_KEY", allowed_integrations={"provider-a"}) == "synthetic-secret"
    assert manager.get("provider-a", "API_KEY", allowed_integrations={"provider-b"}) is None
    assert manager.revoke("provider-a", "API_KEY")
    assert manager.get("provider-a", "API_KEY") is None


def test_disabled_skill_is_not_loaded(tmp_path: Path):
    skill = tmp_path / ".omnix" / "skills" / "disabled"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("description: Disabled\nNever load this", encoding="utf-8")
    manager = SkillsManager(tmp_path)
    manager.state_path = tmp_path / "skills-state.json"
    manager.state = {"disabled": {"enabled": False, "installed": True}}
    text, loaded, skipped = manager.relevant_context("use disabled", allowed_permissions=set(), credentials=CredentialManager(tmp_path / "creds.json"))
    assert text == ""
    assert loaded == []
    assert skipped == []

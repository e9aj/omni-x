from pathlib import Path

import pytest

from omnix.credentials import CredentialManager
from omnix.skills_manager import SkillsManager


def test_skills_manager_browse_install_enable_and_permissions(tmp_path: Path):
    source = tmp_path / "reviewed-skill"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "description: Review code\npermissions: filesystem.read,terminal.read\ncredentials: GITHUB_TOKEN\n",
        encoding="utf-8",
    )
    manager = SkillsManager(tmp_path / "workspace")
    manager.state_path = tmp_path / "state.json"
    with pytest.raises(PermissionError):
        manager.install(source)
    record = manager.install(source, reviewed=True)
    assert record.installed is True
    assert record.enabled is False
    assert record.credentials == ("GITHUB_TOKEN",)
    enabled = manager.set_enabled(record.name, True)
    assert enabled.enabled is True


def test_credential_manager_scopes_and_revokes_without_listing_values(tmp_path: Path, monkeypatch):
    values = {}
    monkeypatch.setattr("omnix.credentials.set_secret", lambda name, value: values.__setitem__(name, value))
    monkeypatch.setattr("omnix.credentials.get_secret", lambda name: values.get(name))
    manager = CredentialManager(tmp_path / "credentials.json")
    manager.put("github", "token", "secret-value")
    assert manager.get("github", "token") == "secret-value"
    assert manager.get("github", "token", allowed_integrations={"stripe"}) is None
    assert all("secret-value" not in item.values() for item in manager.list())
    assert manager.revoke("github", "token") is True
    assert manager.get("github", "token") is None

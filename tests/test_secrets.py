from pathlib import Path

from omnix import secrets


def test_fallback_secret_round_trip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OMNIX_MASTER_KEY", "test-only-master-key")
    monkeypatch.setattr(secrets, "_dpapi_protect", lambda value: None)
    monkeypatch.setattr(secrets, "_dpapi_unprotect", lambda value: None)
    secrets.set_secret("TEST_KEY", "secret-value")
    assert secrets.get_secret("TEST_KEY") == "secret-value"

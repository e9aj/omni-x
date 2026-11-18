from pathlib import Path

from omnix.store import Store


def test_sessions_messages_and_memory(tmp_path: Path):
    store = Store(tmp_path / "state.sqlite3")
    session = store.new_session("test")
    store.add_message(session, "user", "hello")
    assert store.messages(session) == [{"role": "user", "content": "hello"}]
    store.remember("project", "OMNI-X")
    assert store.recall("omni") == [{"key": "project", "value": "OMNI-X"}]


def test_provider_health_is_additive_and_persistent(tmp_path: Path):
    store = Store(tmp_path / "state.sqlite3")
    store.record_provider_health("omniroute", True, 42.5)
    store.record_provider_health("omniroute", False, 81.0, "rate limit")
    row = store.provider_health("omniroute")["omniroute"]
    assert row["healthy"] == 0
    assert row["successes"] == 1
    assert row["failures"] == 1
    assert row["last_error"] == "rate limit"

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


def test_provider_failure_categories_are_persistent(tmp_path: Path):
    store = Store(tmp_path / "failures.sqlite3")
    store.record_provider_failure("omniroute", "502", "bad gateway", 123.4)
    store.record_provider_failure("omniroute", "401", "credential required", 20.0)
    rows = store.db.execute("SELECT category,latency_ms FROM provider_failures ORDER BY id").fetchall()
    assert [(row["category"], row["latency_ms"]) for row in rows] == [("502", 123.4), ("401", 20.0)]

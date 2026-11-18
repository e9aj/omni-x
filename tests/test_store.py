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


def test_model_health_records_probe_evidence_and_percentiles(tmp_path: Path):
    store = Store(tmp_path / "models.sqlite3")
    store.record_model_probe({"model": "free-a", "upstream": "gateway", "available": True, "tool_verified": True, "successes": 1, "latency_ms": 20, "input_tokens": 4, "output_tokens": 5})
    store.record_model_probe({"model": "free-a", "upstream": "gateway", "available": True, "tool_verified": True, "successes": 1, "latency_ms": 40, "input_tokens": 6, "output_tokens": 7})
    row = store.model_health("free-a")["free-a"]
    assert row["tested"] == 1
    assert row["available"] == 1
    assert row["tool_verified"] == 1
    assert row["successes"] == 2
    assert row["input_tokens"] == 10
    assert row["output_tokens"] == 12
    assert row["p50_latency_ms"] == 40
    assert row["p95_latency_ms"] == 40

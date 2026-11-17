from pathlib import Path

from omnix.store import Store


def test_sessions_messages_and_memory(tmp_path: Path):
    store = Store(tmp_path / "state.sqlite3")
    session = store.new_session("test")
    store.add_message(session, "user", "hello")
    assert store.messages(session) == [{"role": "user", "content": "hello"}]
    store.remember("project", "OMNI-X")
    assert store.recall("omni") == [{"key": "project", "value": "OMNI-X"}]

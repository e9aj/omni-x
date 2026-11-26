import io
import json
import threading
import urllib.error
from types import SimpleNamespace

import pytest

from omnix.config import Settings
from omnix.providers import ModelClient, ProviderError, _validate_http_url
from omnix.runtime import AgentRuntime
from omnix.store import Store


def event(value):
    return b"data: " + json.dumps(value).encode() + b"\n\n"


def test_stream_delivers_deltas_and_reassembles_tool_calls(monkeypatch):
    payload = (event({"model": "model-free", "choices": [{"index": 0, "delta": {"content": "Hello "}}]})
               + event({"choices": [{"index": 0, "delta": {"content": "world", "tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "read_", "arguments": '{"path":'}}]}}]})
               + event({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"name": "file", "arguments": '"x"}'}}]}}], "usage": {"prompt_tokens": 2}})
               + b"data: [DONE]\n\n")
    sent = []
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: SimpleNamespace(open=lambda request, timeout: sent.append(json.loads(request.data)) or io.BytesIO(payload)))
    deltas = []
    result = ModelClient(Settings(provider="omniroute")).stream([], on_delta=deltas.append)
    assert sent[0]["stream"] is True
    assert deltas == ["Hello ", "world"]
    assert result["choices"][0]["message"]["tool_calls"][0]["function"] == {"name": "read_file", "arguments": '{"path":"x"}'}
    assert result["usage"]["prompt_tokens"] == 2


def test_stream_rejects_truncation_and_honours_cancellation(monkeypatch):
    payload = event({"choices": [{"delta": {"content": "partial"}}]})
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: SimpleNamespace(open=lambda *args, **kwargs: io.BytesIO(payload)))
    client = ModelClient(Settings(provider="omniroute"))
    with pytest.raises(ProviderError, match="before completion"):
        client.stream([])
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(RuntimeError, match="Task cancelled"):
        client.stream([], cancel_event=cancelled)


def test_provider_errors_do_not_expose_upstream_body(monkeypatch):
    def fail(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad request", {}, io.BytesIO(b"private-response-sentinel"))

    monkeypatch.setattr("urllib.request.build_opener", lambda *_: SimpleNamespace(open=fail))
    client = ModelClient(Settings(provider="omniroute", retry_limit=0))
    with pytest.raises(ProviderError) as error:
        client.complete([])
    assert str(error.value) == "Provider HTTP 400"


@pytest.mark.parametrize("url", ["https://userinfo@example.test/v1", "https://example.test/v1?parameter=value", "https://example.test/v1#fragment"])
def test_provider_urls_reject_embedded_credentials_and_query(url):
    with pytest.raises(ProviderError, match="must not contain"):
        _validate_http_url(url)


def test_streamed_tool_call_runs_through_native_runtime(monkeypatch, tmp_path):
    (tmp_path / "note.txt").write_text("verified content", encoding="utf-8")
    streams = [
        event({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "read_file", "arguments": '{"path":'}}]}}]})
        + event({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"note.txt"}'}}]}}]}) + b"data: [DONE]\n\n",
        event({"choices": [{"delta": {"content": "Verified content."}}]}) + b"data: [DONE]\n\n",
    ]
    requests = []

    def open_stream(request, timeout):
        requests.append(json.loads(request.data))
        return io.BytesIO(streams.pop(0))

    monkeypatch.setattr("omnix.providers.get_secret", lambda _: None)
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: SimpleNamespace(open=open_stream))
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path / "data"))
    settings = Settings(provider="omniroute", mode="FREE", model="local-free", free_models=["local-free"])
    store = Store(tmp_path / "state.sqlite3")
    runtime = AgentRuntime(settings, store, tmp_path)
    chunks, events = [], []
    answer, session = runtime.run("Read the note", on_delta=chunks.append, on_event=events.append)
    assert answer == "Verified content."
    assert "Running tool: read_file" in events
    assert "Verified content." in chunks
    assert any(message.get("role") == "tool" and "verified content" in message.get("content", "") for message in requests[1]["messages"])
    assert store.messages(session)[-1]["content"] == answer

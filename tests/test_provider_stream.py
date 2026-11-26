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


def test_anthropic_stream_reconstructs_tool_calls_and_history(monkeypatch):
    payload = (event({"type": "message_start", "message": {"model": "claude-fixture", "usage": {"input_tokens": 8}}})
               + event({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Checking"}})
               + event({"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "call-1", "name": "read_file", "input": {}}})
               + event({"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"path":'}})
               + event({"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '"note.txt"}'}})
               + event({"type": "message_delta", "usage": {"output_tokens": 3}})
               + event({"type": "message_stop"}))
    sent = []
    monkeypatch.setattr("omnix.providers.get_secret", lambda _: "fixture-only")
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: SimpleNamespace(open=lambda request, timeout: sent.append(json.loads(request.data)) or io.BytesIO(payload)))
    client = ModelClient(Settings(provider="anthropic"))
    messages = [{"role": "user", "content": "read"}, {"role": "assistant", "content": "", "tool_calls": [{"id": "old", "function": {"name": "read_file", "arguments": '{"path":"old.txt"}'}}]}, {"role": "tool", "tool_call_id": "old", "content": "old content"}]
    deltas = []
    result = client.stream(messages, on_delta=deltas.append)
    assert deltas == ["Checking"]
    assert result["choices"][0]["message"]["tool_calls"][0]["function"] == {"name": "read_file", "arguments": '{"path":"note.txt"}'}
    assert result["usage"] == {"prompt_tokens": 8, "completion_tokens": 3}
    assert sent[0]["stream"] is True
    assert sent[0]["messages"][1]["content"][0]["type"] == "tool_use"
    assert sent[0]["messages"][2]["content"][0]["tool_use_id"] == "old"


def test_anthropic_stream_rejects_truncated_response(monkeypatch):
    monkeypatch.setattr("omnix.providers.get_secret", lambda _: "fixture-only")
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: SimpleNamespace(open=lambda *args, **kwargs: io.BytesIO(event({"type": "ping"}))))
    with pytest.raises(ProviderError, match="before completion"):
        ModelClient(Settings(provider="anthropic")).stream([])


def test_anthropic_streamed_tool_call_runs_through_runtime(monkeypatch, tmp_path):
    (tmp_path / "note.txt").write_text("local fixture content", encoding="utf-8")
    tool_stream = (event({"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "call-1", "name": "read_file", "input": {}}})
                   + event({"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"path":"note.txt"}'}})
                   + event({"type": "message_stop"}))
    final_stream = (event({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Verified."}})
                    + event({"type": "message_stop"}))
    streams, requests = [tool_stream, final_stream], []
    def open_stream(request, timeout):
        requests.append(json.loads(request.data))
        return io.BytesIO(streams.pop(0))
    monkeypatch.setattr("omnix.providers.get_secret", lambda _: "fixture-only")
    monkeypatch.setattr("omnix.routing.get_secret", lambda _: "fixture-only")
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: SimpleNamespace(open=open_stream))
    monkeypatch.setenv("OMNIX_DATA_DIR", str(tmp_path / "data"))
    settings = Settings(provider="anthropic", mode="SMART", allow_paid=True, model="fixture")
    store = Store(tmp_path / "state.sqlite3")
    runtime = AgentRuntime(settings, store, tmp_path)
    chunks = []
    answer, session = runtime.run("Read the note", on_delta=chunks.append)
    assert answer == "Verified."
    assert "Verified." in chunks
    assert any(block.get("type") == "tool_result" and "local fixture content" in block.get("content", "")
               for message in requests[1]["messages"] if isinstance(message["content"], list)
               for block in message["content"])
    assert store.messages(session)[-1]["content"] == answer


def test_provider_errors_do_not_expose_upstream_body(monkeypatch):
    def fail(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad request", {}, io.BytesIO(b"private-response-sentinel"))

    monkeypatch.setattr("urllib.request.build_opener", lambda *_: SimpleNamespace(open=fail))
    client = ModelClient(Settings(provider="omniroute", retry_limit=0))
    with pytest.raises(ProviderError) as error:
        client.complete([])
    assert str(error.value) == "Provider HTTP 400"


def test_one_shot_provider_response_is_bounded_and_validated(monkeypatch):
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: SimpleNamespace(open=lambda *args, **kwargs: io.BytesIO(b"x" * 8_000_001)))
    client = ModelClient(Settings(provider="omniroute", retry_limit=0))
    with pytest.raises(ProviderError, match="size limit"):
        client.complete([])
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: SimpleNamespace(open=lambda *args, **kwargs: io.BytesIO(b"not-json")))
    with pytest.raises(ProviderError, match="invalid JSON"):
        client.complete([])


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

import io
import json
import threading
from types import SimpleNamespace

import pytest

from omnix.config import Settings
from omnix.providers import ModelClient, ProviderError


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

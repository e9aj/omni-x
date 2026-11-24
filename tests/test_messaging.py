import json

import pytest

from omnix.messaging import DiscordAdapter, MessageRequest, MessagingError, TelegramAdapter


class Response:
    headers = {"Content-Length": "15"}

    def __enter__(self): return self
    def __exit__(self, *_): return None
    def read(self, _limit): return json.dumps({"ok": True}).encode()


def test_telegram_fixture_uses_official_endpoint_and_never_logs_token(monkeypatch):
    seen = {}
    class Opener:
        def open(self, request, timeout):
            seen.update(url=request.full_url, body=request.data)
            return Response()
    monkeypatch.setattr("omnix.messaging.urllib.request.build_opener", lambda *_: Opener())
    result = TelegramAdapter(credential="secret-token", allowed_hosts={"api.telegram.org"}).send(MessageRequest("", "hello", "123"))
    assert result == {"ok": True}
    assert seen["url"].startswith("https://api.telegram.org/bot")
    assert b"secret-token" not in seen["body"]


def test_discord_rejects_unallowlisted_host():
    adapter = DiscordAdapter(credential="token", allowed_hosts={"example.invalid"})
    with pytest.raises(MessagingError, match="not authorised"):
        adapter.send(MessageRequest("channel", "hello", "unused"))

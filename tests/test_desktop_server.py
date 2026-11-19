import json
import os
import threading
import urllib.error
import urllib.request
from contextlib import closing
from http.server import ThreadingHTTPServer
from socket import socket

from omnix.desktop_server import Handler


def test_desktop_server_requires_loopback_token(monkeypatch):
    monkeypatch.setenv("OMNIX_IPC_TOKEN", "unit-test-token")
    with closing(socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/health", timeout=2)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("unauthenticated desktop request was accepted")
        request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/health", headers={"Authorization": "Bearer unit-test-token"})
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        assert payload["status"] == "ok"
    finally:
        server.shutdown()
        thread.join(timeout=2)

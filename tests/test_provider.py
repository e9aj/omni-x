import json
import threading
import pytest
from http.server import BaseHTTPRequestHandler, HTTPServer

from omnix.config import Settings
from omnix.providers import ModelClient, ProviderError


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        size = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(size))
        body = {"choices": [{"message": {"role": "assistant", "content": payload["messages"][-1]["content"]}}]}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


def test_openai_compatible_provider(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("TEST_PROVIDER_KEY", "test-key")
    monkeypatch.setattr("omnix.providers.PROVIDERS", {"test": __import__("omnix.providers", fromlist=["Provider"]).Provider("test", f"http://127.0.0.1:{server.server_port}", "TEST_PROVIDER_KEY")})
    try:
        client = ModelClient(Settings(provider="test", model="test-model"))
        result = client.complete([{"role": "user", "content": "hello"}])
        assert result["choices"][0]["message"]["content"] == "hello"
    finally:
        server.shutdown()


def test_provider_does_not_follow_redirects(monkeypatch):
    reached = threading.Event()

    class Destination(BaseHTTPRequestHandler):
        def do_GET(self):
            reached.set()
            self.send_response(200)
            self.end_headers()
        def log_message(self, *_):
            pass

    destination = HTTPServer(("127.0.0.1", 0), Destination)
    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{destination.server_port}/target")
            self.end_headers()
        def log_message(self, *_):
            pass

    source = HTTPServer(("127.0.0.1", 0), Redirect)
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (source, destination)]
    for thread in threads:
        thread.start()
    monkeypatch.setattr("omnix.providers.get_secret", lambda _: None)
    try:
        client = ModelClient(Settings(provider="omniroute", base_url=f"http://127.0.0.1:{source.server_port}", retry_limit=0))
        with pytest.raises(ProviderError, match="HTTP 302"):
            client.list_models()
        assert not reached.is_set()
    finally:
        for server in (source, destination):
            server.shutdown()
        for thread in threads:
            thread.join(2)
        for server in (source, destination):
            server.server_close()

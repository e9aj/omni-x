import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from omnix.config import Settings
from omnix.providers import ModelClient


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

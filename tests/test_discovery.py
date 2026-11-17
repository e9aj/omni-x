import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from omnix.config import Settings
from omnix.discovery import choose_free_model, discover_omniroute


class DiscoveryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"data": [{"id": "free-coder", "free": True, "context_length": 32000}, {"id": "paid-model", "pricing": {"prompt": "1", "completion": "1"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def test_discovery_only_selects_explicitly_free_models():
    server = HTTPServer(("127.0.0.1", 0), DiscoveryHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        settings = Settings(base_url=f"http://127.0.0.1:{server.server_port}/v1", request_timeout_seconds=2)
        result = discover_omniroute(settings)
        assert result.reachable is True
        assert [model["id"] for model in result.free_models] == ["free-coder"]
        assert choose_free_model(result)["id"] == "free-coder"
    finally:
        server.shutdown()

"""Loopback-only SSE provider used by isolated packaged desktop smoke tests."""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if self.path != "/v1/chat/completions" or length <= 0 or length > 1_000_000:
            self.send_error(400)
            return
        payload = json.loads(self.rfile.read(length))
        if not payload.get("stream"):
            self.send_error(400)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for text in ("fixture ", "response"):
            event = {"model": "fixture-free", "choices": [{"index": 0, "delta": {"content": text}}]}
            self.wfile.write(b"data: " + json.dumps(event).encode() + b"\n\n")
            self.wfile.flush()
            if text == "fixture ":
                time.sleep(5)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *_args: object) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

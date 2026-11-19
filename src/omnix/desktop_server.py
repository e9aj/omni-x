"""Authenticated loopback service used by the Tauri desktop shell."""
from __future__ import annotations

import argparse, hmac, json, os, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__


class Handler(BaseHTTPRequestHandler):
    server: "DesktopServer"
    def do_GET(self) -> None:
        expected = os.environ.get("OMNIX_IPC_TOKEN", "")
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if not expected or not hmac.compare_digest(supplied, expected):
            self.send_error(401, "authenticated loopback token required"); return
        if self.path != "/v1/health": self.send_error(404); return
        body = json.dumps({"status": "ok", "version": __version__, "pid": os.getpid()}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *_: object) -> None: pass


class DesktopServer(ThreadingHTTPServer):
    allow_reuse_address = False


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--port", type=int, required=True); args = parser.parse_args()
    server = DesktopServer(("127.0.0.1", args.port), Handler)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0


if __name__ == "__main__": raise SystemExit(main())

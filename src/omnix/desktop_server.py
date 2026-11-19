"""Authenticated loopback service used by the Tauri desktop shell."""
from __future__ import annotations

import argparse
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import __version__
from .config import load_settings
from .runtime import AgentRuntime
from .store import Store


class DesktopState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.cancel_event: threading.Event | None = None


class Handler(BaseHTTPRequestHandler):
    server: "DesktopServer"

    def _authorized(self) -> bool:
        expected = os.environ.get("OMNIX_IPC_TOKEN", "")
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        origin = self.headers.get("Origin", "")
        allowed = {"", "tauri://localhost", "https://tauri.localhost", "http://tauri.localhost"}
        if origin not in allowed or not expected or not hmac.compare_digest(supplied, expected):
            self._json(401, {"error": "authenticated loopback request required"})
            return False
        return True

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("request body too large")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("request body must be an object")
        return value

    def do_GET(self) -> None:
        if not self._authorized():
            return
        self._json(200, {"status": "ok", "version": __version__, "pid": os.getpid()}) if self.path == "/v1/health" else self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._authorized():
            return
        try:
            if self.path == "/v1/chat":
                self._chat(self._body())
            elif self.path == "/v1/stop":
                with self.server.state.lock:
                    event = self.server.state.cancel_event
                if event:
                    event.set()
                self._json(200, {"stopping": bool(event)})
            elif self.path == "/v1/shutdown":
                self._json(200, {"stopping": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._json(404, {"error": "not found"})
        except (ValueError, OSError, RuntimeError) as exc:
            self._json(400, {"error": str(exc)})

    def _chat(self, body: dict[str, Any]) -> None:
        prompt = body.get("prompt")
        session_id = body.get("session_id")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 100_000:
            raise ValueError("prompt must be a non-empty string under 100000 characters")
        if session_id is not None and (not isinstance(session_id, str) or len(session_id) > 200):
            raise ValueError("session_id is invalid")
        cancel = threading.Event()
        with self.server.state.lock:
            if self.server.state.cancel_event is not None:
                self._json(409, {"error": "another chat task is already running"})
                return
            self.server.state.cancel_event = cancel
        try:
            settings = load_settings()
            runtime = AgentRuntime(settings, Store(), Path.cwd(), approver=lambda _: False, cancel_event=cancel)
            answer, result_session = runtime.run(prompt, session_id)
            self._json(200, {"answer": answer, "session_id": result_session, "mode": settings.mode, "allow_paid": settings.allow_paid})
        except Exception as exc:
            self._json(502, {"error": str(exc)})
        finally:
            with self.server.state.lock:
                self.server.state.cancel_event = None

    def log_message(self, *_: object) -> None:
        pass


class DesktopServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], handler: type[Handler]) -> None:
        super().__init__(address, handler)
        self.state = DesktopState()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    server = DesktopServer(("127.0.0.1", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

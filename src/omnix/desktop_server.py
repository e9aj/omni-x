"""Authenticated loopback service used by the Tauri desktop shell."""
from __future__ import annotations

import argparse
import hmac
import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import __version__
from .config import Settings, config_path, load_settings, save_settings
from .runtime import AgentRuntime
from .hermes_primary import HermesPrimaryError, run_hermes_primary_probe
from .council import CouncilConfig, CouncilService, ModelRef
from .discovery import discover_omniroute
from .store import Store


class DesktopState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.cancel_event: threading.Event | None = None


class ApprovalManager:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.pending: dict[str, dict[str, Any]] = {}

    def request(self, action: str, timeout: float = 60.0) -> bool:
        ident = str(uuid.uuid4())
        event = threading.Event()
        item = {"id": ident, "action": action, "status": "pending", "expires_at": time.time() + timeout, "event": event}
        with self.lock:
            self.pending[ident] = item
        event.wait(timeout)
        with self.lock:
            current = self.pending.pop(ident, item)
        return current["status"] == "approved" and current["expires_at"] > time.time()

    def list(self) -> list[dict[str, Any]]:
        now = time.time()
        with self.lock:
            expired = [key for key, item in self.pending.items() if item["expires_at"] <= now]
            for key in expired:
                self.pending[key]["status"] = "expired"
            return [{key: value for key, value in item.items() if key != "event"} for item in self.pending.values()]

    def decide(self, ident: str, approved: bool) -> bool:
        with self.lock:
            item = self.pending.get(ident)
            if not item or item["expires_at"] <= time.time():
                return False
            item["status"] = "approved" if approved else "rejected"
            item["event"].set()
            return True


class Handler(BaseHTTPRequestHandler):
    server: "DesktopServer"

    def _authorized(self) -> bool:
        expected = os.environ.get("OMNIX_IPC_TOKEN", "")
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        origin = self.headers.get("Origin", "")
        allowed = {"tauri://localhost", "https://tauri.localhost", "http://tauri.localhost"}
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
        if self.path == "/v1/health":
            self._json(200, {"status": "ok", "version": __version__, "pid": os.getpid()})
        elif self.path == "/v1/approvals":
            self._json(200, {"approvals": self.server.approvals.list()})
        elif self.path == "/v1/settings":
            settings = load_settings()
            if not config_path().exists() and settings.provider == "openai":
                settings = Settings(provider="omniroute", model="auto/best-free", base_url="http://127.0.0.1:20128/v1", mode="FREE", allow_paid=False, max_cost_usd=0.0, tool_policy="ask")
            self._json(200, {"mode": settings.mode, "provider": settings.provider, "model": settings.model, "runtime": settings.runtime, "content_preference": settings.content_preference, "allow_paid": settings.allow_paid})
        elif self.path == "/v1/models":
            settings = load_settings()
            if not config_path().exists() and settings.provider == "openai":
                settings = Settings(provider="omniroute", model="auto/best-free", base_url="http://127.0.0.1:20128/v1", mode="FREE", allow_paid=False, max_cost_usd=0.0, tool_policy="ask")
            discovery = discover_omniroute(settings)
            models = [{"id": item.get("id"), "owned_by": item.get("owned_by", "unknown"), "free": item in discovery.free_models,
                       "context_length": item.get("context_length"), "capabilities": item.get("capabilities") or {}}
                      for item in discovery.models if isinstance(item, dict) and item.get("id")]
            self._json(200, {"reachable": discovery.reachable, "error": discovery.error, "latency_ms": discovery.latency_ms,
                             "provider": settings.provider, "selected": settings.model, "mode": settings.mode, "models": models})
        elif self.path.startswith("/v1/sessions/"):
            session_id = self.path.rsplit("/", 1)[-1]
            if not session_id or len(session_id) > 200 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in session_id):
                self._json(400, {"error": "session_id is invalid"})
                return
            rows = Store().messages(session_id)
            self._json(200, {"session_id": session_id, "messages": rows})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._authorized():
            return
        try:
            if self.path == "/v1/chat":
                self._chat(self._body())
            elif self.path == "/v1/council":
                self._council(self._body())
            elif self.path == "/v1/stop":
                with self.server.state.lock:
                    event = self.server.state.cancel_event
                if event:
                    event.set()
                self._json(200, {"stopping": bool(event)})
            elif self.path == "/v1/shutdown":
                self._json(200, {"stopping": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            elif self.path.startswith("/v1/approvals/"):
                ident = self.path.rsplit("/", 1)[-1]
                decision = self._body().get("decision")
                if decision not in {"approve", "reject"} or not self.server.approvals.decide(ident, decision == "approve"):
                    self._json(404, {"error": "approval is missing or expired"})
                else:
                    self._json(200, {"id": ident, "decision": decision})
            elif self.path == "/v1/settings":
                body = self._body()
                preference = body.get("content_preference")
                runtime = body.get("runtime")
                model = body.get("model")
                if preference is not None and preference not in {"standard", "creative", "open"}:
                    raise ValueError("content_preference must be standard, creative or open")
                if runtime is not None and runtime not in {"omnix", "hermes", "auto"}:
                    raise ValueError("runtime must be omnix, hermes or auto")
                if model is not None and (not isinstance(model, str) or not model.strip() or len(model) > 200):
                    raise ValueError("model must be a non-empty identifier under 200 characters")
                settings = load_settings()
                if not config_path().exists() and settings.provider == "openai":
                    settings = Settings(provider="omniroute", model="auto/best-free", base_url="http://127.0.0.1:20128/v1", mode="FREE", allow_paid=False, max_cost_usd=0.0, tool_policy="ask")
                if preference is not None:
                    settings.content_preference = preference
                if runtime is not None:
                    settings.runtime = runtime
                if model is not None:
                    if settings.mode == "FREE" and model not in settings.free_models and ":free" not in model.lower() and not model.lower().endswith("-free") and not model.lower().startswith("auto/"):
                        raise ValueError("FREE mode only permits a discovered free model")
                    settings.model = model.strip()
                save_settings(settings)
                self._json(200, {"content_preference": settings.content_preference, "runtime": settings.runtime, "model": settings.model})
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
            if not config_path().exists() and settings.provider == "openai":
                settings = Settings(provider="omniroute", model="auto/best-free", base_url="http://127.0.0.1:20128/v1", mode="FREE", allow_paid=False, max_cost_usd=0.0, tool_policy="ask")
            store = Store()
            approver = self.server.approvals.request if hasattr(self.server, "approvals") else (lambda _: False)
            hermes_result = None
            if settings.runtime in {"hermes", "auto"} and settings.mode == "FREE" and not settings.allow_paid and settings.max_cost_usd == 0:
                try:
                    hermes_result = run_hermes_primary_probe(settings, prompt, timeout=settings.agent_execution_timeout_seconds, cancel_event=cancel)
                except HermesPrimaryError:
                    if settings.runtime == "hermes":
                        raise
            if hermes_result is not None:
                answer = hermes_result["answer"]
                result_session = hermes_result.get("omnix_session_id") or session_id
                task_id = None
                h_usage = hermes_result.get("usage", {})
                usage = [{"provider": h_usage.get("provider", settings.provider),
                          "model": h_usage.get("served_model") or hermes_result.get("model", settings.model),
                          "input_tokens": h_usage.get("input_tokens", 0),
                          "output_tokens": h_usage.get("output_tokens", 0),
                          "estimated_cost": h_usage.get("estimated_cost_usd", 0.0)}]
                tool_events = []
                self._json(200, {"answer": answer, "session_id": result_session, "mode": settings.mode, "runtime": "hermes", "allow_paid": settings.allow_paid, "model": usage[-1]["model"], "provider": usage[-1]["provider"], "usage": usage, "tool_events": tool_events})
                return
            runtime = AgentRuntime(settings, store, Path.cwd(), approver=approver, cancel_event=cancel)
            answer, result_session = runtime.run(prompt, session_id)
            task_id = getattr(runtime, "last_task_id", None)
            usage = []
            tool_events = []
            if task_id:
                usage = [dict(row) for row in store.db.execute("SELECT provider, model, input_tokens, output_tokens, estimated_cost FROM usage WHERE task_id=? ORDER BY id", (task_id,)).fetchall()]
                tool_events = [dict(row) for row in store.db.execute("SELECT kind, detail, created FROM events WHERE task_id=? AND kind LIKE 'tool_%' ORDER BY id", (task_id,)).fetchall()]
            actual_model = usage[-1]["model"] if usage else settings.model
            actual_provider = usage[-1]["provider"] if usage else settings.provider
            self._json(200, {"answer": answer, "session_id": result_session, "mode": settings.mode, "runtime": "omnix", "allow_paid": settings.allow_paid, "model": actual_model, "provider": actual_provider, "usage": usage, "tool_events": tool_events})
        except Exception as exc:
            self._json(502, {"error": str(exc)})
        finally:
            with self.server.state.lock:
                self.server.state.cancel_event = None

    def _council(self, body: dict[str, Any]) -> None:
        prompt = body.get("prompt")
        mode = body.get("mode", "standard")
        raw_models = body.get("models", [])
        session_id = body.get("session_id")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 100_000:
            raise ValueError("prompt must be a non-empty string under 100000 characters")
        if mode not in {"standard", "council", "advanced", "research"}:
            raise ValueError("mode must be standard, council, advanced or research")
        if not isinstance(raw_models, list) or len(raw_models) > 5 or any(not isinstance(item, str) or not item.strip() or len(item) > 200 for item in raw_models):
            raise ValueError("models must contain at most five model identifiers")
        settings = load_settings()
        if not config_path().exists() and settings.provider == "openai":
            settings = Settings(provider="omniroute", model="auto/best-free", base_url="http://127.0.0.1:20128/v1", mode="FREE", allow_paid=False, max_cost_usd=0.0, tool_policy="ask")
        models = tuple(ModelRef(settings.provider, item.strip()) for item in raw_models)
        config = CouncilConfig(mode=mode, models=models, free_only=True, max_cost_usd=0.0,
                               max_models=5, max_concurrency=min(5, max(1, int(body.get("max_concurrency", 3)))))
        store = Store()
        result_session = session_id if isinstance(session_id, str) and session_id else store.new_session("Council session")
        task_id = store.start_task(result_session)
        try:
            result = CouncilService(settings).run([{"role": "user", "content": prompt}], config)
            store.add_message(result_session, "user", prompt)
            store.add_message(result_session, "assistant", result.answer)
            for candidate in result.candidates:
                store.record_usage(task_id, candidate.provider, candidate.model, candidate.input_tokens, candidate.output_tokens, 0.0)
                store.event(task_id, "council_candidate", json.dumps({"provider": candidate.provider, "model": candidate.model, "score": candidate.score, "latency_ms": candidate.latency_ms, "error": candidate.error}, sort_keys=True))
            store.event(task_id, "council_completed", json.dumps({"mode": result.mode, "latency_ms": result.latency_ms, "errors": result.errors}, sort_keys=True))
            store.update_task(task_id, "completed")
            self._json(200, {"answer": result.answer, "session_id": result_session, "task_id": task_id, "mode": result.mode,
                             "candidates": [{"provider": item.provider, "model": item.model, "score": item.score, "latency_ms": item.latency_ms, "input_tokens": item.input_tokens, "output_tokens": item.output_tokens, "error": item.error} for item in result.candidates],
                             "usage": [{"provider": item.provider, "model": item.model, "input_tokens": item.input_tokens, "output_tokens": item.output_tokens, "estimated_cost": 0.0} for item in result.candidates]})
        except Exception as exc:
            store.update_task(task_id, "failed", str(exc))
            store.event(task_id, "council_failed", type(exc).__name__)
            raise

    def log_message(self, *_: object) -> None:
        pass


class DesktopServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], handler: type[Handler]) -> None:
        super().__init__(address, handler)
        self.state = DesktopState()
        self.approvals = ApprovalManager()


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

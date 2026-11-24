"""Authenticated loopback service used by the Tauri desktop shell."""
from __future__ import annotations

import argparse
import hmac
import json
import os
import threading
import time
import uuid
from urllib.parse import parse_qs, urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import __version__
from .config import Settings, config_path, load_settings, save_settings
from .runtime import AgentRuntime
from .hermes_primary import HermesPrimaryError, run_hermes_primary_probe
from .council import CouncilConfig, CouncilService, ModelRef
from .discovery import discover_omniroute
from .brain import MarkdownVault
from .task_service import TaskService
from .skills_manager import SkillsManager
from .integrations import IntegrationRegistry
from .integration_catalog import register_researched_integrations
from .voice import VoiceService
from .document_intelligence import DocumentExtractor
from .store import Store
from .semantic_index import SemanticIndex


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
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # The desktop may stop/cancel a request while the backend is
            # finishing its response. Do not attempt a second error response
            # on a socket the client has already closed.
            return

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
        elif self.path == "/v1/brain/notes":
            self._json(200, {"notes": MarkdownVault(Path(os.environ.get("OMNIX_VAULT_DIR", str(Path.home() / "OMNI-X" / "Brain")))).list_notes()})
        elif self.path == "/v1/brain/graph":
            self._json(200, MarkdownVault(Path(os.environ.get("OMNIX_VAULT_DIR", str(Path.home() / "OMNI-X" / "Brain")))).graph())
        elif self.path == "/v1/brain/attachments":
            self._json(200, {"attachments": MarkdownVault(Path(os.environ.get("OMNIX_VAULT_DIR", str(Path.home() / "OMNI-X" / "Brain")))).list_attachments()})
        elif urlsplit(self.path).path == "/v1/brain/history":
            relative = parse_qs(urlsplit(self.path).query).get("path", [""])[0]
            self._json(200, {"history": MarkdownVault(Path(os.environ.get("OMNIX_VAULT_DIR", str(Path.home() / "OMNI-X" / "Brain")))).history(relative)})
        elif urlsplit(self.path).path == "/v1/brain/document":
            relative = parse_qs(urlsplit(self.path).query).get("path", [""])[0]
            self._json(200, DocumentExtractor(Path.cwd()).extract(relative))
        elif urlsplit(self.path).path == "/v1/brain/search":
            query = parse_qs(urlsplit(self.path).query).get("q", [""])[0]
            self._json(200, {"results": MarkdownVault(Path(os.environ.get("OMNIX_VAULT_DIR", str(Path.home() / "OMNI-X" / "Brain")))).search(query)})
        elif urlsplit(self.path).path == "/v1/brain/semantic-search":
            query = parse_qs(urlsplit(self.path).query).get("q", [""])[0]
            root = Path(os.environ.get("OMNIX_VAULT_DIR", str(Path.home() / "OMNI-X" / "Brain")))
            vault = MarkdownVault(root)
            index = SemanticIndex(Store(), root)
            index.rebuild(((str(item["path"]), vault.read(str(item["path"]))) for item in vault.list_notes()))
            results = index.search(query)
            for result in results:
                try:
                    result["snippet"] = vault.read(str(result["path"]))[:300]
                except (FileNotFoundError, OSError):
                    result["snippet"] = ""
            self._json(200, {"results": results, "method": "local-feature-hash"})
        elif self.path.startswith("/v1/brain/note"):
            query = parse_qs(urlsplit(self.path).query)
            relative = query.get("path", [""])[0]
            vault = MarkdownVault(Path(os.environ.get("OMNIX_VAULT_DIR", str(Path.home() / "OMNI-X" / "Brain"))))
            if urlsplit(self.path).path == "/v1/brain/note/inspect":
                self._json(200, vault.inspect(relative))
            elif urlsplit(self.path).path == "/v1/brain/note/backlinks":
                self._json(200, {"path": relative, "backlinks": vault.backlinks(relative)})
            else:
                self._json(200, {"path": relative, "content": vault.read(relative)})
        elif self.path == "/v1/tasks":
            self._json(200, {"tasks": self.server.tasks.status()})
        elif self.path == "/v1/skills":
            self._json(200, {"skills": [self.server.skill_payload(item) for item in self.server.skills.browse()]})
        elif self.path == "/v1/integrations":
            self._json(200, {"integrations": [self.server.integration_payload(item) for item in self.server.integrations.list()]})
        elif self.path == "/v1/voice/capabilities":
            self._json(200, {"capabilities": VoiceService().capabilities()})
        elif self.path == "/v1/workflows":
            self._json(200, {"workflows": Store().workflows()})
        elif self.path.startswith("/v1/workflows/") and self.path.endswith("/runs"):
            workflow_id = self.path.split("/")[3]
            self._json(200, {"runs": Store().workflow_runs(workflow_id)})
        elif self.path.startswith("/v1/tasks/"):
            task_id = self.path.rsplit("/", 1)[-1]
            task = self.server.tasks.status(task_id)
            if task is None:
                self._json(404, {"error": "task not found"})
            else:
                self._json(200, {"task": task, "delegations": self.server.tasks.store.delegations(task_id)})
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
            elif self.path == "/v1/brain/notes":
                body = self._body()
                vault = MarkdownVault(Path(os.environ.get("OMNIX_VAULT_DIR", str(Path.home() / "OMNI-X" / "Brain"))))
                self._json(200, {"path": vault.write(body.get("path", ""), body.get("content", ""))})
            elif self.path == "/v1/brain/attachments":
                body = self._body()
                vault = MarkdownVault(Path(os.environ.get("OMNIX_VAULT_DIR", str(Path.home() / "OMNI-X" / "Brain"))))
                self._json(200, {"path": vault.save_attachment(body.get("path", ""), body.get("data", ""))})
            elif self.path == "/v1/brain/from-session":
                body = self._body()
                session_id, relative = body.get("session_id"), body.get("path")
                if not isinstance(session_id, str) or not isinstance(relative, str) or len(session_id) > 200:
                    raise ValueError("session conversion request is invalid")
                messages = Store().messages(session_id)
                if not messages:
                    raise ValueError("session has no messages")
                content = "# Conversation note\n\n" + "\n\n".join(f"## {item['role'].title()}\n{item['content']}" for item in messages)
                vault = MarkdownVault(Path(os.environ.get("OMNIX_VAULT_DIR", str(Path.home() / "OMNI-X" / "Brain"))))
                self._json(200, {"path": vault.write(relative, content)})
            elif self.path == "/v1/workflows":
                body = self._body()
                name, definition = body.get("name"), body.get("definition")
                if not isinstance(name, str) or not name.strip() or len(name) > 200 or not isinstance(definition, dict):
                    raise ValueError("workflow definition is invalid")
                nodes = definition.get("nodes", [])
                if not isinstance(nodes, list) or len(nodes) > 100:
                    raise ValueError("workflow nodes are invalid")
                ident = Store().save_workflow(name.strip(), definition, body.get("id"))
                self._json(200, {"workflow_id": ident})
            elif self.path == "/v1/tasks":
                body = self._body()
                action = body.get("action", "enqueue")
                if action == "enqueue":
                    prompt = body.get("prompt")
                    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 100_000:
                        raise ValueError("task prompt is invalid")
                    task_id = self.server.tasks.enqueue(prompt, deadline_seconds=body.get("deadline_seconds"))
                    self._json(200, {"task_id": task_id})
                elif action == "schedule":
                    prompt, schedule = body.get("prompt"), body.get("schedule")
                    if not isinstance(prompt, str) or not isinstance(schedule, str) or not prompt.strip() or len(prompt) > 100_000:
                        raise ValueError("scheduled task is invalid")
                    self._json(200, {"schedule_id": self.server.tasks.schedule(prompt, schedule)})
                else:
                    raise ValueError("task action must be enqueue or schedule")
            elif self.path.startswith("/v1/tasks/"):
                task_id = self.path.rsplit("/", 1)[-1]
                if self._body().get("action") != "cancel":
                    raise ValueError("task action must be cancel")
                self.server.tasks.cancel(task_id)
                self._json(200, {"task_id": task_id, "cancelled": True})
            elif self.path.startswith("/v1/skills/"):
                name = self.path.rsplit("/", 1)[-1]
                body = self._body()
                action = body.get("action")
                if action not in {"enable", "disable"} or not name or len(name) > 120 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_ ." for char in name):
                    raise ValueError("skill action or name is invalid")
                record = self.server.skills.set_enabled(name, action == "enable")
                self._json(200, {"skill": self.server.skill_payload(record)})
            elif self.path.startswith("/v1/integrations/"):
                name = self.path.rsplit("/", 1)[-1]
                body = self._body()
                action = body.get("action")
                if action not in {"install", "enable", "disable", "revoke"} or not name or len(name) > 120 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in name):
                    raise ValueError("integration action or name is invalid")
                record = getattr(self.server.integrations, action)(name)
                self._json(200, {"integration": self.server.integration_payload(record)})
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
        settings = load_settings()
        if not config_path().exists() and settings.provider == "openai":
            settings = Settings(provider="omniroute", model="auto/best-free", base_url="http://127.0.0.1:20128/v1", mode="FREE", allow_paid=False, max_cost_usd=0.0, tool_policy="ask")
        self.tasks = TaskService(settings, Store(), Path.cwd(), approver=self.approvals.request)
        self.skills = SkillsManager(Path.cwd())
        self.integrations = register_researched_integrations(IntegrationRegistry(Store()))

    def server_close(self) -> None:
        self.tasks.close()
        super().server_close()

    @staticmethod
    def skill_payload(item: Any) -> dict[str, Any]:
        return {"name": item.name, "path": item.path, "source": item.source,
                "description": item.description, "permissions": list(item.permissions),
                "credentials": list(item.credentials), "dependencies": list(item.dependencies),
                "enabled": item.enabled, "installed": item.installed}

    def integration_payload(self, item: Any) -> dict[str, Any]:
        return {"name": item.name, "kind": item.kind, "interface": item.interface,
                "credentials": list(item.credentials), "permissions": list(item.permissions),
                "dependencies": list(item.dependencies), "endpoints": list(item.endpoints),
                "operating_systems": list(item.operating_systems), "installed": item.installed,
                "enabled": item.enabled, "revoked": item.revoked, "configured": item.configured,
                "version": item.version, "health": self.integrations.health(item.name)}


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

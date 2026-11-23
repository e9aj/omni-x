from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import subprocess
from dataclasses import replace
from pathlib import Path

from . import __version__
from .config import Settings, load_settings, save_settings
from .providers import PROVIDERS, ProviderError
from .runtime import AgentRuntime
from .secrets import set_secret
from .secrets import get_secret
from .discovery import discover_omniroute, choose_free_model
from .store import Store
from .task_service import TaskService


def _approve(question: str) -> bool:
    answer = input(f"OMNI-X approval required: {question} [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omnix", description="OMNI-X autonomous AI agent")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    chat = sub.add_parser("chat", help="interactive agent session")
    chat.add_argument("prompt", nargs="*")
    run = sub.add_parser("run", help="run one autonomous task")
    run.add_argument("prompt")
    config = sub.add_parser("config", help="manage local configuration")
    config.add_argument("action", choices=["show", "set", "set-key"])
    config.add_argument("name", nargs="?")
    config.add_argument("value", nargs="?")
    memory = sub.add_parser("memory", help="manage persistent memory")
    memory.add_argument("action", choices=["remember", "recall"])
    memory.add_argument("value", nargs="*")
    skills = sub.add_parser("skills", help="browse and manage reviewed skills")
    skills.add_argument("action", nargs="?", choices=["list", "inspect", "install", "enable", "disable"], default="list")
    skills.add_argument("value", nargs="?")
    skills.add_argument("--reviewed", action="store_true", help="confirm a local skill source was reviewed")
    sub.add_parser("tools", help="list built-in tools")
    models = sub.add_parser("models", help="discover models or check provider health")
    models.add_argument("action", choices=["list", "health", "probe"], nargs="?", default="health")
    sub.add_parser("onboard", help="discover and configure a verified free OmniRoute model")
    sub.add_parser("discover", help="show provider and free-model availability without exposing credentials")
    sub.add_parser("doctor", help="check local runtime readiness")
    hermes = sub.add_parser("hermes", help="install or inspect the managed Hermes backend")
    hermes.add_argument("action", choices=["install", "status", "probe"])
    schedule = sub.add_parser("schedule", help="manage persistent scheduled tasks")
    schedule.add_argument("action", choices=["add", "list"])
    schedule.add_argument("prompt", nargs="?")
    schedule.add_argument("when", nargs="?")
    background = sub.add_parser("background", help="manage durable background tasks")
    background.add_argument("action", choices=["run", "list", "status", "cancel"])
    background.add_argument("value", nargs="?")
    delegate = sub.add_parser("delegate", help="delegate isolated child jobs")
    delegate.add_argument("parent_job_id")
    delegate.add_argument("prompt", nargs="+")
    sub.add_parser("worker", help="run the durable background worker host")
    args = parser.parse_args(argv)

    if args.command == "onboard":
        settings = replace(load_settings(), mode="FREE", provider="omniroute")
        discovery = discover_omniroute(settings)
        selected = choose_free_model(discovery, "agent tool calling")
        if selected is None:
            if discovery.error:
                print(f"OmniRoute unavailable at {discovery.gateway}: {discovery.error}")
            elif discovery.auth_required:
                print("OmniRoute is reachable but requires its local gateway key; configure OMNIROUTE_API_KEY securely.")
            else:
                print("OmniRoute is reachable, but it returned no explicitly verified free models.")
            print("No live free endpoint was configured. Connect a provider account only when you choose to do so.")
            return 1
        settings = replace(settings, model=str(selected.get("id")), base_url=discovery.gateway, free_models=[str(model.get("id")) for model in discovery.free_models])
        save_settings(settings)
        print(f"Configured OmniRoute free model: {settings.model}")
        return 0

    if args.command == "discover":
        settings = load_settings()
        discovery = discover_omniroute(settings)
        print(f"OmniRoute: {'reachable' if discovery.reachable else 'unavailable'} ({discovery.gateway})")
        if discovery.error:
            print(f"  status: {discovery.error}")
        print(f"  explicitly verified free models: {len(discovery.free_models)}")
        for model in discovery.free_models:
            caps = model.get("capabilities") or {}
            pricing = model.get("pricing") or {}
            auth = model.get("authentication") or model.get("auth") or "gateway credential"
            print(f"  usable in FREE mode: {model.get('id')} | upstream={model.get('owned_by', 'unknown')} | tools={bool(caps.get('tool_calling'))} | context={model.get('context_length', 'unknown')} | pricing={pricing or 'free catalogue'} | auth={auth}")
        for name, provider in PROVIDERS.items():
            if name == "omniroute":
                continue
            key_available = bool(get_secret(provider.key_name) or __import__("os").environ.get(provider.key_name))
            print(f"{name}: {'credential available' if key_available else 'requires API key/account'}")
        return 0

    if args.command == "config":
        settings = load_settings()
        if args.action == "show":
            print(settings)
        elif args.action == "set":
            if args.name not in Settings.__dataclass_fields__ or args.value is None:
                parser.error("config set requires a supported name and value")
            current = getattr(settings, args.name)
            if isinstance(current, bool):
                value = args.value.lower() in {"1", "true", "yes", "on"}
            elif isinstance(current, int):
                value = int(args.value)
            elif isinstance(current, float):
                value = float(args.value)
            else:
                value = args.value
            if args.name == "mode" and value not in {"FREE", "SMART", "PERFORMANCE"}:
                parser.error("mode must be FREE, SMART, or PERFORMANCE")
            setattr(settings, args.name, value)
            save_settings(settings)
            print(f"Updated {args.name}")
        else:
            name = args.name or ""
            if not name:
                parser.error("config set-key requires a secret name")
            set_secret(name, getpass.getpass(f"Enter {name}: "))
            print(f"Stored {name} securely")
        return 0
    if args.command == "memory":
        store = Store()
        if args.action == "remember":
            if len(args.value) < 2:
                parser.error("memory remember requires KEY VALUE")
            store.remember(args.value[0], " ".join(args.value[1:]))
            print("Memory stored")
        else:
            for item in store.recall(" ".join(args.value)):
                print(f"{item['key']}: {item['value']}")
        return 0
    if args.command == "skills":
        from .skills_manager import SkillsManager
        manager = SkillsManager(Path(os.getcwd()))
        if args.action == "install":
            if not args.value:
                parser.error("skills install requires a local skill directory or SKILL.md")
            try:
                record = manager.install(Path(args.value), reviewed=args.reviewed)
            except (OSError, ValueError, PermissionError) as exc:
                print(f"omnix: {exc}", file=sys.stderr)
                return 1
            print(f"Installed reviewed skill: {record.name} (disabled by default)")
        elif args.action in {"enable", "disable"}:
            if not args.value:
                parser.error(f"skills {args.action} requires a skill name")
            try:
                record = manager.set_enabled(args.value, args.action == "enable")
            except KeyError as exc:
                print(f"omnix: {exc}", file=sys.stderr)
                return 1
            print(f"{record.name}: {'enabled' if record.enabled else 'disabled'}")
        elif args.action == "inspect":
            record = next((item for item in manager.browse() if item.name == args.value), None)
            if record is None:
                print(f"omnix: unknown skill {args.value}", file=sys.stderr)
                return 1
            print(json.dumps(record.__dict__, indent=2))
        else:
            for record in manager.browse():
                print(f"{record.name}: source={record.source} installed={record.installed} enabled={record.enabled} permissions={','.join(record.permissions) or 'none'} credentials={','.join(record.credentials) or 'none'}")
        return 0
    if args.command == "tools":
        from .tools import ToolRegistry
        for name in ToolRegistry().tools:
            print(name)
        return 0
    if args.command == "models":
        from .providers import ModelClient
        try:
            if args.action == "probe":
                from .model_probe import ModelProbe
                probe = ModelProbe(load_settings())
                discovery = probe.discover()
                if not discovery.reachable:
                    print(f"OmniRoute unavailable: {discovery.error}", file=sys.stderr)
                    return 1
                print(f"Catalogue: {len(discovery.models)} models; explicitly free: {len(discovery.free_models)}")
                for row in probe.probe_models(discovery.free_models):
                    status = "usable" if row["available"] else "unavailable"
                    tool = "tool-verified" if row.get("tool_verified") else "tool-unverified"
                    error = f"; {row['last_error']}" if row.get("last_error") else ""
                    print(f"{row['model']}: {status}, {tool}, {row['latency_ms']:.0f}ms{error}")
                return 0
            client = ModelClient(load_settings())
            if args.action == "health":
                print({**client.health_check(), "model_health": Store().model_health()})
            else:
                for model in client.list_models():
                    print(model.get("id", model))
            return 0
        except ProviderError as exc:
            print(f"omnix: {exc}", file=sys.stderr)
            return 1
    if args.command == "doctor":
        settings = load_settings()
        print(f"OMNI-X {__version__}")
        print(f"Python: {sys.version.split()[0]}")
        print(f"Provider: {settings.provider} ({'registered' if settings.provider in PROVIDERS else 'unknown'})")
        print("SQLite: available")
        print("Credentials: configured at runtime or via environment")
        return 0
    if args.command == "hermes":
        from .hermes_runtime import installed_hermes_source
        if args.action == "status":
            source = installed_hermes_source()
            print(f"Hermes backend: {'installed' if source else 'not installed'}")
            if source:
                print(f"Source: {source}")
            return 0 if source else 1
        if args.action == "probe":
            if os.environ.get("OMNIX_HERMES_PRIMARY") != "1":
                print("Hermes primary probe is opt-in; set OMNIX_HERMES_PRIMARY=1 to run it.", file=sys.stderr)
                return 2
            from .hermes_primary import HermesPrimaryError, run_hermes_primary_probe
            try:
                result = run_hermes_primary_probe(load_settings(), "Reply with exactly HERMES-PRIMARY-OK.")
            except HermesPrimaryError as exc:
                print(f"Hermes primary probe unavailable: {exc}", file=sys.stderr)
                return 1
            print(json.dumps(result))
            return 0
        if os.name != "nt":
            print("Hermes installer integration currently supports native Windows only.", file=sys.stderr)
            return 1
        script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "install-hermes.ps1"))
        import subprocess
        result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-NonInteractive"], check=False)
        return result.returncode
    if args.command in {"schedule", "background", "delegate"}:
        service = TaskService(load_settings(), workspace=os.getcwd(), approver=_approve)
        try:
            if args.command == "delegate":
                child_ids = service.delegate(args.parent_job_id, [{"role": "specialist", "prompt": value} for value in args.prompt])
                print("Children: " + ", ".join(child_ids))
            elif args.command == "schedule" and args.action == "add":
                if not args.prompt or not args.when:
                    parser.error("schedule add requires PROMPT and ISO_TIMESTAMP or INTERVAL")
                print(f"Scheduled: {service.schedule(args.prompt, args.when)}")
            elif args.command == "schedule":
                for row in service.store.db.execute("SELECT id,prompt,schedule,next_run_at,enabled,missed_runs FROM schedules ORDER BY next_run_at"):
                    print(dict(row))
            elif args.action == "run":
                if not args.value:
                    parser.error("background run requires PROMPT")
                job_id = service.enqueue(args.value)
                flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
                subprocess.Popen([sys.executable, "-m", "omnix.cli", "worker"], creationflags=flags, close_fds=True)
                print(f"Job: {job_id}")
            elif args.action == "list":
                for row in service.status(): print(row)
            elif args.action == "status":
                if not args.value: parser.error("background status requires JOB_ID")
                print(service.status(args.value))
            else:
                if not args.value: parser.error("background cancel requires JOB_ID")
                service.cancel(args.value); print(f"Cancelled: {args.value}")
        finally:
            service.close()
        return 0
    if args.command == "worker":
        # Detached workers cannot prompt.  Tool approval remains denied unless
        # a host explicitly embeds TaskService with an approval callback.
        TaskService(load_settings(), workspace=os.getcwd(), approver=lambda _: False).run_worker_forever()
        return 0
    settings = load_settings()
    if args.command in {"run", "chat"} and not (get_secret({"openai":"OPENAI_API_KEY","groq":"GROQ_API_KEY","cerebras":"CEREBRAS_API_KEY","gemini":"GEMINI_API_KEY","mistral":"MISTRAL_API_KEY","openrouter":"OPENROUTER_API_KEY","together":"TOGETHER_API_KEY","deepseek":"DEEPSEEK_API_KEY","anthropic":"ANTHROPIC_API_KEY","omniroute":"OMNIROUTE_API_KEY"}.get(settings.provider, "")) or __import__("os").environ.get({"openai":"OPENAI_API_KEY","groq":"GROQ_API_KEY","cerebras":"CEREBRAS_API_KEY","gemini":"GEMINI_API_KEY","mistral":"MISTRAL_API_KEY","openrouter":"OPENROUTER_API_KEY","together":"TOGETHER_API_KEY","deepseek":"DEEPSEEK_API_KEY","anthropic":"ANTHROPIC_API_KEY"}.get(settings.provider, ""))):
        candidate = replace(settings, mode="FREE", provider="omniroute")
        discovery = discover_omniroute(candidate)
        selected = choose_free_model(discovery, "agent tool calling")
        if selected:
            settings = replace(candidate, model=str(selected.get("id")), base_url=discovery.gateway, free_models=[str(model.get("id")) for model in discovery.free_models])
            save_settings(settings)
            print(f"Auto-configured verified OmniRoute free model: {settings.model}")
    try:
        runtime = AgentRuntime(settings, workspace=os.getcwd(), approver=_approve)
        if args.command == "run":
            answer, session_id = runtime.run(args.prompt)
            if answer:
                print(answer)
            print(f"Session: {session_id}")
        else:
            session_id = None
            initial = " ".join(args.prompt).strip()
            if initial:
                answer, session_id = runtime.run(initial, session_id)
                if answer:
                    print(answer)
            while True:
                try:
                    prompt = input("you> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if prompt.lower() in {"exit", "quit"}:
                    break
                if prompt:
                    answer, session_id = runtime.run(prompt, session_id)
                    if answer:
                        print(f"omnix> {answer}")
        return 0
    except (ProviderError, RuntimeError, ValueError) as exc:
        print(f"omnix: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

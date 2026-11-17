from __future__ import annotations

import argparse
import getpass
import os
import sys
from dataclasses import replace

from . import __version__
from .config import Settings, load_settings, save_settings
from .providers import PROVIDERS, ProviderError
from .runtime import AgentRuntime
from .secrets import set_secret
from .secrets import get_secret
from .discovery import discover_omniroute, choose_free_model
from .store import Store


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
    sub.add_parser("skills", help="list discovered skills")
    sub.add_parser("tools", help="list built-in tools")
    models = sub.add_parser("models", help="discover models or check provider health")
    models.add_argument("action", choices=["list", "health"], nargs="?", default="health")
    sub.add_parser("onboard", help="discover and configure a verified free OmniRoute model")
    sub.add_parser("discover", help="show provider and free-model availability without exposing credentials")
    sub.add_parser("doctor", help="check local runtime readiness")
    args = parser.parse_args(argv)

    if args.command == "onboard":
        settings = replace(load_settings(), mode="FREE", provider="omniroute")
        discovery = discover_omniroute(settings)
        selected = choose_free_model(discovery)
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
            print(f"  usable in FREE mode: {model.get('id')}")
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
        from .skills import discover_skills
        for skill in discover_skills(os.getcwd()):
            print(f"{skill.name}: {skill.description or skill.path}")
        return 0
    if args.command == "tools":
        from .tools import ToolRegistry
        for name in ToolRegistry().tools:
            print(name)
        return 0
    if args.command == "models":
        from .providers import ModelClient
        try:
            client = ModelClient(load_settings())
            if args.action == "health":
                print(client.health_check())
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
    settings = load_settings()
    if args.command in {"run", "chat"} and not (get_secret({"openai":"OPENAI_API_KEY","groq":"GROQ_API_KEY","cerebras":"CEREBRAS_API_KEY","gemini":"GEMINI_API_KEY","mistral":"MISTRAL_API_KEY","openrouter":"OPENROUTER_API_KEY","together":"TOGETHER_API_KEY","deepseek":"DEEPSEEK_API_KEY","anthropic":"ANTHROPIC_API_KEY","omniroute":"OMNIROUTE_API_KEY"}.get(settings.provider, "")) or __import__("os").environ.get({"openai":"OPENAI_API_KEY","groq":"GROQ_API_KEY","cerebras":"CEREBRAS_API_KEY","gemini":"GEMINI_API_KEY","mistral":"MISTRAL_API_KEY","openrouter":"OPENROUTER_API_KEY","together":"TOGETHER_API_KEY","deepseek":"DEEPSEEK_API_KEY","anthropic":"ANTHROPIC_API_KEY"}.get(settings.provider, ""))):
        candidate = replace(settings, mode="FREE", provider="omniroute")
        discovery = discover_omniroute(candidate)
        selected = choose_free_model(discovery)
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

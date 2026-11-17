from __future__ import annotations

import argparse
import getpass
import os
import sys

from . import __version__
from .config import Settings, load_settings, save_settings
from .providers import PROVIDERS, ProviderError
from .runtime import AgentRuntime
from .secrets import set_secret
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
    sub.add_parser("doctor", help="check local runtime readiness")
    args = parser.parse_args(argv)

    if args.command == "config":
        settings = load_settings()
        if args.action == "show":
            print(settings)
        elif args.action == "set":
            if args.name not in Settings.__dataclass_fields__ or args.value is None:
                parser.error("config set requires a supported name and value")
            current = getattr(settings, args.name)
            value = int(args.value) if isinstance(current, int) else args.value
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
    if args.command == "doctor":
        settings = load_settings()
        print(f"OMNI-X {__version__}")
        print(f"Python: {sys.version.split()[0]}")
        print(f"Provider: {settings.provider} ({'registered' if settings.provider in PROVIDERS else 'unknown'})")
        print("SQLite: available")
        print("Credentials: configured at runtime or via environment")
        return 0
    settings = load_settings()
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

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .hermes_runtime import installed_hermes_source


@dataclass(frozen=True)
class Skill:
    name: str
    path: Path
    description: str
    instructions: str


def skill_roots(workspace: Path | None = None) -> list[Path]:
    roots = []
    if workspace:
        roots.append(Path(workspace) / ".omnix" / "skills")
        roots.append(Path(workspace) / "skills")
    roots.append(Path(os.environ.get("OMNIX_SKILLS_DIR", Path.home() / ".omnix" / "skills")))
    # Hermes keeps skills as reviewed SKILL.md trees.  Reuse those trees only
    # when the operator explicitly points OMNI-X at an inspected Hermes source
    # checkout; never silently scan an arbitrary installation.
    explicit_source = os.environ.get("OMNIX_HERMES_SOURCE")
    source = Path(explicit_source).expanduser().resolve() if explicit_source else installed_hermes_source()
    if source:
        roots.extend((source / "skills", source / "optional-skills"))
    return roots


def discover_skills(workspace: Path | None = None) -> list[Skill]:
    found: list[Skill] = []
    seen: set[str] = set()
    for root in skill_roots(workspace):
        if not root.exists():
            continue
        for path in root.rglob("SKILL.md"):
            name = path.parent.name
            if name in seen:
                continue
            text = path.read_text(encoding="utf-8")
            # A Hermes source checkout can contain a very large optional skill
            # catalogue.  An explicit allowlist is required for those roots so
            # installing OMNI-X never activates arbitrary third-party skill
            # instructions by accident.
            if "optional-skills" in root.parts:
                allowed = {item.strip() for item in os.environ.get("OMNIX_HERMES_SKILLS", "").split(",") if item.strip()}
                if name not in allowed:
                    continue
            description = next((line.removeprefix("description:").strip() for line in text.splitlines() if line.lower().startswith("description:")), "")
            found.append(Skill(name, path, description, text[:20_000]))
            seen.add(name)
    return sorted(found, key=lambda skill: skill.name.lower())


def relevant_instructions(skills: list[Skill], prompt: str) -> str:
    stopwords = {"about", "after", "also", "because", "before", "being", "current", "does", "from", "have", "into", "just", "list", "only", "path", "read", "return", "that", "than", "then", "their", "there", "these", "this", "tool", "using", "with", "workspace", "your"}
    tokens = {token.lower().strip(".,:;!?()[]{}\"") for token in prompt.split() if len(token) > 3}
    tokens -= stopwords
    selected: list[Skill] = []
    for skill in skills:
        skill_tokens = set(re.split(r"[-_ ]+", skill.name.lower()))
        if skill.name.lower() in tokens or (tokens & skill_tokens):
            selected.append(skill)
    return "\n\n".join(f"## Skill: {skill.name}\n{skill.instructions}" for skill in selected[:3])

"""Portable, local-first Markdown vault for OMNI-X Brain."""

from __future__ import annotations

import os
import tempfile
import uuid
import re
from pathlib import Path


class VaultError(ValueError):
    pass


class MarkdownVault:
    """Keep Markdown as the source of truth with strict root containment."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, relative: str, *, allow_missing: bool = False) -> Path:
        if not isinstance(relative, str) or not relative.strip() or len(relative) > 400:
            raise VaultError("note path is invalid")
        candidate = (self.root / relative).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise VaultError("note path escapes the Brain vault") from exc
        if not allow_missing and not candidate.is_file():
            raise FileNotFoundError(relative)
        if candidate.suffix.lower() != ".md":
            raise VaultError("Brain notes must use the .md extension")
        return candidate

    def list_notes(self) -> list[dict[str, object]]:
        notes = []
        for path in self.root.rglob("*.md"):
            if path.is_file():
                notes.append({"path": path.relative_to(self.root).as_posix(), "size": path.stat().st_size, "updated": path.stat().st_mtime})
        return sorted(notes, key=lambda item: str(item["path"]))[:1000]

    def read(self, relative: str) -> str:
        path = self._path(relative)
        if path.stat().st_size > 5_000_000:
            raise VaultError("note exceeds the 5 MB read limit")
        return path.read_text(encoding="utf-8")

    def write(self, relative: str, content: str) -> str:
        if not isinstance(content, str) or len(content.encode("utf-8")) > 5_000_000:
            raise VaultError("note exceeds the 5 MB write limit")
        path = self._path(relative, allow_missing=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".omnix-{uuid.uuid4().hex}-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return path.relative_to(self.root).as_posix()

    def search(self, query: str) -> list[dict[str, str]]:
        if not isinstance(query, str) or not query.strip() or len(query) > 200:
            raise VaultError("search query is invalid")
        needle = query.casefold()
        results = []
        for item in self.list_notes():
            path = str(item["path"])
            content = self.read(path)
            if needle in content.casefold() or needle in path.casefold():
                results.append({"path": path, "snippet": content[:300]})
        return results[:100]

    def graph(self) -> dict[str, list[dict[str, str]]]:
        """Build a bounded wikilink graph from Markdown source, without AI calls."""
        notes = {str(item["path"]): item for item in self.list_notes()}
        edges: list[dict[str, str]] = []
        for path in notes:
            for target in re.findall(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]", self.read(path)):
                candidate = target.strip().replace("\\", "/")
                if not candidate.lower().endswith(".md"):
                    candidate += ".md"
                if candidate in notes:
                    edges.append({"source": path, "target": candidate})
        return {"nodes": [{"path": path} for path in sorted(notes)], "edges": edges}

    def backlinks(self, relative: str) -> list[str]:
        target = self._path(relative).relative_to(self.root).as_posix()
        stem = target[:-3] if target.lower().endswith(".md") else target
        return [edge["source"] for edge in self.graph()["edges"] if edge["target"] in {target, stem + ".md"}]

    def inspect(self, relative: str) -> dict[str, object]:
        """Return deterministic document intelligence suitable for local UI."""
        content = self.read(relative)
        headings = [line.lstrip("#").strip() for line in content.splitlines() if line.startswith("#")]
        return {"path": relative, "headings": headings[:100], "links": self.backlinks(relative),
                "word_count": len(content.split()), "character_count": len(content)}

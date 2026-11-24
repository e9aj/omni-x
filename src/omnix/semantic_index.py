"""Bounded local semantic-style indexing for the Brain vault.

This deliberately uses deterministic feature hashing rather than a downloaded
model. It provides local similarity ranking without sending note contents or
requiring credentials. It is not presented as neural semantic understanding.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Iterable

from .store import Store

_TOKEN = re.compile(r"[\w][\w'-]{1,63}", re.UNICODE)


def _vector(text: str, dimensions: int = 128) -> list[float]:
    values = [0.0] * dimensions
    tokens = [item.casefold() for item in _TOKEN.findall(text)][:20_000]
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        values[index] += sign
    magnitude = math.sqrt(sum(value * value for value in values))
    return [value / magnitude for value in values] if magnitude else values


def _similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


class SemanticIndex:
    """Persist deterministic local vectors and rank bounded Brain sources."""

    def __init__(self, store: Store, vault_root: Path):
        self.store = store
        self.vault_root = vault_root.expanduser().resolve()

    def rebuild(self, sources: Iterable[tuple[str, str]]) -> int:
        count = 0
        for path, content in list(sources)[:1000]:
            if not isinstance(path, str) or not isinstance(content, str):
                continue
            if len(content.encode("utf-8")) > 5_000_000:
                continue
            self.store.upsert_embedding(path, "brain-note", content, _vector(content))
            count += 1
        return count

    def search(self, query: str, limit: int = 20) -> list[dict[str, object]]:
        if not isinstance(query, str) or not query.strip() or len(query) > 200:
            raise ValueError("semantic search query is invalid")
        query_vector = _vector(query)
        ranked = []
        for row in self.store.embeddings(limit=1000):
            score = _similarity(query_vector, row["vector"])
            ranked.append({"path": row["source_id"], "source": row["source_type"], "score": round(score, 6)})
        ranked.sort(key=lambda item: (-float(item["score"]), str(item["path"])))
        return ranked[:max(1, min(int(limit), 100))]

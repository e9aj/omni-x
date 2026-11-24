from __future__ import annotations

import hashlib
import re
import time
from collections import OrderedDict


def compress_terminal_output(text: str, max_lines: int = 200, max_chars: int = 20_000) -> str:
    """Reduce repetitive terminal noise without changing error or code lines."""
    lines = text.splitlines()
    kept: list[str] = []
    previous = None
    repeats = 0
    for line in lines:
        if line == previous:
            repeats += 1
            if repeats == 3:
                kept.append(f"[repeated line omitted: {line[:200]}]")
            continue
        previous, repeats = line, 0
        kept.append(line)
    result = "\n".join(kept)
    if len(kept) > max_lines:
        result = "\n".join(kept[:max_lines]) + f"\n[remaining {len(kept) - max_lines} lines omitted]"
    return result[:max_chars]


def estimate_tokens(text: str) -> int:
    return max(0, (len(text) + 3) // 4)


def truncate_to_budget(text: str, token_budget: int) -> str:
    if token_budget < 1:
        raise ValueError("token budget must be positive")
    return text if estimate_tokens(text) <= token_budget else text[: token_budget * 4] + "\n[context truncated]"


def select_relevant_context(query: str, documents: list[tuple[str, str]], token_budget: int = 2000) -> list[tuple[str, str]]:
    terms = {item.casefold() for item in re.findall(r"[\w-]{3,}", query)}
    ranked = sorted(documents, key=lambda item: (len(terms & set(re.findall(r"[\w-]{3,}", item[1].casefold()))), item[0]), reverse=True)
    result, used = [], 0
    for name, content in ranked:
        clipped = truncate_to_budget(content, max(1, token_budget - used))
        if not clipped.strip():
            continue
        result.append((name, clipped)); used += estimate_tokens(clipped)
        if used >= token_budget:
            break
    return result


class PromptCache:
    """Bounded exact-request cache; never caches credentials or tool actions."""
    def __init__(self, max_entries: int = 128, ttl_seconds: float = 300):
        self.max_entries, self.ttl_seconds, self._items = max_entries, ttl_seconds, OrderedDict()

    def _key(self, provider: str, model: str, messages: object, parameters: object) -> str:
        return hashlib.sha256(repr((provider, model, messages, parameters)).encode()).hexdigest()

    def get(self, provider: str, model: str, messages: object, parameters: object):
        key = self._key(provider, model, messages, parameters); item = self._items.get(key)
        if not item or time.monotonic() - item[0] > self.ttl_seconds:
            self._items.pop(key, None); return None
        self._items.move_to_end(key); return item[1]

    def put(self, provider: str, model: str, messages: object, parameters: object, value: object) -> None:
        key = self._key(provider, model, messages, parameters); self._items[key] = (time.monotonic(), value); self._items.move_to_end(key)
        while len(self._items) > self.max_entries: self._items.popitem(last=False)

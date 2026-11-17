from __future__ import annotations


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

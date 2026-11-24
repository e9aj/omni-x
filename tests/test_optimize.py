from omnix.optimize import PromptCache, compress_terminal_output, estimate_tokens, select_relevant_context


def test_compression_only_removes_repetition():
    output = "same\n" * 10 + "ERROR: keep this"
    result = compress_terminal_output(output)
    assert "ERROR: keep this" in result
    assert "repeated line omitted" in result


def test_context_selection_and_cache_are_bounded():
    selected = select_relevant_context("python installer", [("a", "garden herbs"), ("b", "python Windows installer")], token_budget=20)
    assert selected[0][0] == "b"
    assert estimate_tokens(selected[0][1]) <= 20
    cache = PromptCache(max_entries=1)
    cache.put("omniroute", "free", [{"role": "user", "content": "hi"}], {}, "answer")
    assert cache.get("omniroute", "free", [{"role": "user", "content": "hi"}], {}) == "answer"

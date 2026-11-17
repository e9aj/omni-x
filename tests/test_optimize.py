from omnix.optimize import compress_terminal_output


def test_compression_only_removes_repetition():
    output = "same\n" * 10 + "ERROR: keep this"
    result = compress_terminal_output(output)
    assert "ERROR: keep this" in result
    assert "repeated line omitted" in result

from omnix.hermes_bridge import extract_tool_calls


def test_hermes_python_style_tool_call_is_executable():
    calls, cleaned = extract_tool_calls('<tool_call>write_file(filename="x.txt", content="ok")')
    assert calls[0]["function"]["name"] == "write_file"
    assert '"path": "x.txt"' in calls[0]["function"]["arguments"]
    assert cleaned == ""


def test_plain_hermes_tool_description_is_normalized_only_when_explicitly_marked():
    calls, cleaned = extract_tool_calls('Tool call: read_file(path="delegated_result.txt")')
    assert calls[0]["function"]["name"] == "read_file"
    assert cleaned == ""
    assert extract_tool_calls('I will read_file(path="delegated_result.txt")')[0] == []


def test_bare_function_calls_are_normalized_without_parsing_narrative():
    calls, _ = extract_tool_calls('write_file("x.txt", "ok")')
    assert calls and calls[0]["function"]["name"] == "write_file"
    assert extract_tool_calls('I will write_file("x.txt", "ok")')[0] == []

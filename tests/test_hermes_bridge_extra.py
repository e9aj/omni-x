from omnix.hermes_bridge import extract_tool_calls


def test_hermes_python_style_tool_call_is_executable():
    calls, cleaned = extract_tool_calls('<tool_call>write_file(filename="x.txt", content="ok")')
    assert calls[0]["function"]["name"] == "write_file"
    assert '"path": "x.txt"' in calls[0]["function"]["arguments"]
    assert cleaned == ""

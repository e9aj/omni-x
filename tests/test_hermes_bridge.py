from omnix.hermes_bridge import extract_tool_calls


def test_hermes_xml_tool_call_contract_is_parsed():
    calls, text = extract_tool_calls(
        '<tool_call>{"id":"c1","type":"function","function":{"name":"read_file","arguments":"{\\"path\\":\\"x.py\\"}"}}</tool_call>'
    )
    assert calls[0]["function"]["name"] == "read_file"
    assert calls[0]["id"] == "c1"
    assert text == ""


def test_hermes_compatibility_call_is_normalized():
    calls, text = extract_tool_calls('<tool_call>mcp__tool__read_file{"path": "x.py"}')
    assert calls[0]["function"]["name"] == "read_file"
    assert text == ""


def test_hermes_generic_tool_call_is_normalized():
    calls, _ = extract_tool_calls('<tool_call>tool_call{"name":"read_file","arguments":{"path":"x.py"}}</tool_call>')
    assert calls[0]["function"]["name"] == "read_file"


def test_hermes_namespace_call_alias_is_normalized():
    calls, _ = extract_tool_calls('<tool_call>mcp__read_file__read_file(file_path="x.py")')
    assert calls[0]["function"]["name"] == "read_file"
    assert '"path": "x.py"' in calls[0]["function"]["arguments"]


def test_hermes_direct_call_alias_is_normalized():
    calls, _ = extract_tool_calls('<tool_call>execute_command{"command":"python -m unittest -v"}')
    assert calls[0]["function"]["name"] == "run_command"

from omnix.runtime import AgentRuntime


def test_allowlisted_pseudo_tool_is_normalized():
    calls = AgentRuntime._pseudo_tool_calls("mcp__list_workspace_files()")
    assert calls[0]["function"]["name"] == "list_directory"
    formatted = AgentRuntime._pseudo_tool_calls('tool_call: mcp__file_write__write_file\ntool_params:\n  path: calculator.py\n  content: "return 1"')
    assert formatted[0]["function"]["name"] == "write_file"
    assert 'calculator.py' in formatted[0]["function"]["arguments"]
    assert AgentRuntime._pseudo_tool_calls("mcp__delete_everything()") == []

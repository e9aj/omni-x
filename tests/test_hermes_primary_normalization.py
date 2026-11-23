from types import SimpleNamespace

from omnix.hermes_primary import inject_omnix_text_calls


def test_hermes_normalization_injects_only_anchored_valid_call():
    message = SimpleNamespace(content='Tool call: read_file(path="note.txt")', tool_calls=None)
    assert inject_omnix_text_calls(message) is True
    assert message.tool_calls[0].function.name == "read_file"
    assert message.tool_calls[0].function.arguments == '{"path": "note.txt"}'


def test_hermes_normalization_does_not_execute_narrative_or_empty_response():
    narrative = SimpleNamespace(content="I will read_file(path=note.txt) next.", tool_calls=None)
    empty = SimpleNamespace(content="", tool_calls=None)
    assert inject_omnix_text_calls(narrative) is False
    assert inject_omnix_text_calls(empty) is False
    assert not getattr(narrative, "tool_calls", None)
    assert not getattr(empty, "tool_calls", None)

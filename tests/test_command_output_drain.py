import sys

from omnix.tools import ToolRegistry


def test_command_drains_output_larger_than_pipe_buffer(tmp_path):
    registry = ToolRegistry(tmp_path, approver=lambda _: True)
    result = registry.run_command(f'"{sys.executable}" -c "print(\'x\' * 200000)"')
    assert len(result) == 20_000
    assert result.endswith("x\n")

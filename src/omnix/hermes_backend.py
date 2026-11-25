"""Compatibility import for callers using the former backend module name."""

from .agent_backend import AgentExecutionBackend as HermesExecutionBackend

__all__ = ["HermesExecutionBackend"]

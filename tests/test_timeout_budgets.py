from omnix.config import Settings


def test_timeout_budgets_are_explicit_and_bounded():
    settings = Settings()
    assert settings.provider_request_timeout_seconds < settings.agent_execution_timeout_seconds
    assert settings.agent_execution_timeout_seconds <= settings.child_task_timeout_seconds
    assert settings.child_task_timeout_seconds <= settings.parent_orchestration_timeout_seconds
    assert all(value > 0 for value in (
        settings.provider_request_timeout_seconds,
        settings.agent_execution_timeout_seconds,
        settings.child_task_timeout_seconds,
        settings.parent_orchestration_timeout_seconds,
    ))

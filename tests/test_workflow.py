import threading

import pytest

from omnix.workflow import WorkflowError, WorkflowRunner, WorkflowStep


def test_workflow_runs_condition_parallel_retry_and_approval():
    attempts = {"retry": 0}
    runner = WorkflowRunner(
        agent=lambda payload, cancel: payload["value"],
        integration=lambda payload, cancel: (_ for _ in ()).throw(RuntimeError("retry")) if (attempts.__setitem__("retry", attempts["retry"] + 1) or attempts["retry"] < 2) else "integration-ok",
        approve=lambda payload: payload["allow"],
    )
    try:
        result = runner.run([
            WorkflowStep("first", "agent", {"value": "agent-ok"}),
            WorkflowStep("approval", "approval", {"allow": True}, depends_on=("first",)),
            WorkflowStep("retry", "integration", depends_on=("approval",), retries=1),
        ])
        assert result["first"] == "agent-ok"
        assert result["retry"] == "integration-ok"
        assert attempts["retry"] == 2
    finally:
        runner.close()


def test_workflow_denial_and_cycles_fail_closed():
    runner = WorkflowRunner(approve=lambda payload: False)
    try:
        with pytest.raises(PermissionError):
            runner.run([WorkflowStep("approval", "approval", {})])
        with pytest.raises(WorkflowError, match="cycle"):
            runner.run([WorkflowStep("a", "approval", depends_on=("b",)), WorkflowStep("b", "approval", depends_on=("a",))])
    finally:
        runner.close()


def test_workflow_cancellation_is_observed():
    cancel = threading.Event()
    cancel.set()
    runner = WorkflowRunner(agent=lambda payload, event: "never")
    try:
        with pytest.raises(WorkflowError, match="cancelled"):
            runner.run([WorkflowStep("a", "agent")], cancel=cancel)
    finally:
        runner.close()

"""Unit tests for the Orchestrator: plan once, loop execute+verify with Reflexion."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from issue_to_pr.executor.types import ExecutionResult, Task
from issue_to_pr.orchestrator import Orchestrator
from issue_to_pr.planner import Plan
from issue_to_pr.verifier import VerifierVerdict


def _execution(*, success: bool = True, prompt_t: int = 10) -> ExecutionResult:
    return ExecutionResult(
        task_id="t",
        success=success,
        iterations=2,
        exit_reason="done" if success else "max_iterations",
        final_assistant_content="DONE" if success else "stuck",
        total_prompt_tokens=prompt_t,
        total_completion_tokens=5,
        elapsed_seconds=0.5,
        verify_exit_code=0 if success else 1,
    )


def _verdict(*, approved: bool, feedback: str | None = None) -> VerifierVerdict:
    return VerifierVerdict(
        approved=approved,
        reasoning="ok" if approved else "needs work",
        feedback_for_executor=feedback,
    )


def _task(workspace: Path) -> Task:
    return Task(
        id="t1",
        description="fix it",
        workspace=workspace,
        verify_command="echo ok",
        max_iterations=5,
    )


def test_invalid_max_reflexion_rejected() -> None:
    with pytest.raises(ValueError, match="max_reflexion"):
        Orchestrator(
            planner=MagicMock(),
            executor=MagicMock(),
            verifier=MagicMock(),
            max_reflexion_iterations=0,
        )


def test_happy_path_one_iter(tmp_path: Path) -> None:
    """Planner emits a plan; executor succeeds; verifier approves on first try."""
    planner = MagicMock()
    planner.plan.return_value = Plan(
        files_to_read=("a.py",), files_to_modify=("a.py",), steps=("fix",)
    )
    executor = MagicMock()
    executor.run.return_value = _execution(success=True, prompt_t=100)
    verifier = MagicMock()
    verifier.judge.return_value = _verdict(approved=True)

    orch = Orchestrator(planner=planner, executor=executor, verifier=verifier)
    result = orch.run(_task(tmp_path))

    assert result.success is True
    assert result.exit_reason == "approved"
    assert result.reflexion_iterations == 1
    assert result.total_prompt_tokens == 100
    assert planner.plan.call_count == 1
    assert executor.run.call_count == 1
    assert verifier.judge.call_count == 1


def test_reflexion_retries_after_rejection(tmp_path: Path) -> None:
    """First execution rejected -> second succeeds with feedback in description."""
    planner = MagicMock()
    planner.plan.return_value = Plan(files_to_read=(), files_to_modify=(), steps=())
    executor = MagicMock()
    executor.run.side_effect = [
        _execution(success=False),  # tests fail
        _execution(success=True),  # tests pass after retry
    ]
    verifier = MagicMock()
    verifier.judge.side_effect = [
        _verdict(approved=False, feedback="read the error first"),
        _verdict(approved=True),
    ]
    orch = Orchestrator(
        planner=planner, executor=executor, verifier=verifier, max_reflexion_iterations=3
    )
    result = orch.run(_task(tmp_path))

    assert result.success is True
    assert result.reflexion_iterations == 2
    assert executor.run.call_count == 2
    # second executor call must receive feedback in its task description
    second_call_task = executor.run.call_args_list[1].args[0]
    assert "read the error first" in second_call_task.description


def test_orchestrator_stops_at_max_reflexion(tmp_path: Path) -> None:
    planner = MagicMock()
    planner.plan.return_value = Plan(files_to_read=(), files_to_modify=(), steps=())
    executor = MagicMock()
    executor.run.return_value = _execution(success=False)
    verifier = MagicMock()
    verifier.judge.return_value = _verdict(approved=False, feedback="try again")

    orch = Orchestrator(
        planner=planner, executor=executor, verifier=verifier, max_reflexion_iterations=2
    )
    result = orch.run(_task(tmp_path))
    assert result.success is False
    assert result.exit_reason == "max_reflexion_iterations"
    assert result.reflexion_iterations == 2
    assert executor.run.call_count == 2


def test_token_counters_aggregate_across_retries(tmp_path: Path) -> None:
    planner = MagicMock()
    planner.plan.return_value = Plan(files_to_read=(), files_to_modify=(), steps=())
    executor = MagicMock()
    executor.run.side_effect = [
        _execution(success=False, prompt_t=50),
        _execution(success=True, prompt_t=70),
    ]
    verifier = MagicMock()
    verifier.judge.side_effect = [_verdict(approved=False, feedback="x"), _verdict(approved=True)]
    orch = Orchestrator(
        planner=planner, executor=executor, verifier=verifier, max_reflexion_iterations=3
    )
    result = orch.run(_task(tmp_path))
    assert result.total_prompt_tokens == 120
    assert len(result.history) == 2


def test_plan_brief_appended_to_executor_description(tmp_path: Path) -> None:
    plan = Plan(files_to_read=("guide.py",), files_to_modify=(), steps=("first",))
    planner = MagicMock()
    planner.plan.return_value = plan
    executor = MagicMock()
    executor.run.return_value = _execution(success=True)
    verifier = MagicMock()
    verifier.judge.return_value = _verdict(approved=True)

    orch = Orchestrator(planner=planner, executor=executor, verifier=verifier)
    orch.run(_task(tmp_path))

    task_used = executor.run.call_args.args[0]
    assert "guide.py" in task_used.description
    assert "first" in task_used.description

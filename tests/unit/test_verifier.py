"""Unit tests for the Verifier: short-circuit on verify failure + JSON judging."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from issue_to_pr.executor.types import ExecutionResult, Task, ToolCallRecord
from issue_to_pr.llm import LLMResponse
from issue_to_pr.verifier import Verifier, VerifierVerdict
from issue_to_pr.verifier.verifier import _parse_verdict


def _resp(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        reasoning=None,
        tool_calls=[],
        finish_reason="stop",
        model="m",
        prompt_tokens=5,
        completion_tokens=5,
    )


def _execution(
    *,
    verify_exit_code: int = 0,
    tool_calls: tuple[ToolCallRecord, ...] = (),
) -> ExecutionResult:
    return ExecutionResult(
        task_id="t",
        success=verify_exit_code == 0,
        iterations=1,
        exit_reason="done",
        final_assistant_content="DONE",
        tool_calls=tool_calls,
        total_prompt_tokens=10,
        total_completion_tokens=2,
        elapsed_seconds=1.0,
        verify_exit_code=verify_exit_code,
        verify_stdout="",
        verify_stderr="",
    )


def _task(workspace: Path) -> Task:
    return Task(id="t", description="fix it", workspace=workspace, verify_command="pytest -q")


def test_verdict_to_executor_feedback_when_approved_is_empty() -> None:
    v = VerifierVerdict(approved=True, reasoning="lgtm")
    assert v.to_executor_feedback() == ""


def test_verdict_to_executor_feedback_when_rejected_includes_reasoning() -> None:
    v = VerifierVerdict(
        approved=False,
        reasoning="tests modified",
        feedback_for_executor="revert the test change",
    )
    out = v.to_executor_feedback()
    assert "tests modified" in out
    assert "revert the test change" in out


def test_short_circuits_when_verify_failed(tmp_path: Path) -> None:
    """Verifier must NOT call the LLM when verify_exit_code != 0."""
    llm = MagicMock()
    verifier = Verifier(llm=llm, model="m")
    verdict = verifier.judge(_task(tmp_path), _execution(verify_exit_code=1))
    assert verdict.approved is False
    assert "verify command exited" in verdict.reasoning
    llm.chat.assert_not_called()


def test_parse_verdict_approved() -> None:
    raw = '{"approved": true, "reasoning": "minimal fix", "feedback_for_executor": null}'
    v = _parse_verdict(raw)
    assert v.approved is True
    assert v.feedback_for_executor is None


def test_parse_verdict_rejected_with_feedback() -> None:
    raw = (
        '{"approved": false, '
        '"reasoning": "test files modified", '
        '"feedback_for_executor": "do not touch tests"}'
    )
    v = _parse_verdict(raw)
    assert v.approved is False
    assert v.feedback_for_executor == "do not touch tests"


def test_parse_verdict_malformed_json_defaults_to_rejected() -> None:
    v = _parse_verdict("not json")
    assert v.approved is False
    assert "not valid JSON" in v.reasoning


def test_parse_verdict_empty_output_defaults_to_rejected() -> None:
    v = _parse_verdict("   ")
    assert v.approved is False
    assert "empty" in v.reasoning


def test_parse_verdict_non_object_json_rejected() -> None:
    v = _parse_verdict("[1, 2, 3]")
    assert v.approved is False


def test_judge_calls_llm_when_verify_passed(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text("def f(): return 1")
    llm = MagicMock()
    llm.chat.return_value = _resp(
        '{"approved": true, "reasoning": "minimal fix", "feedback_for_executor": null}'
    )
    verifier = Verifier(llm=llm, model="m")
    verdict = verifier.judge(
        _task(tmp_path),
        _execution(
            tool_calls=(
                ToolCallRecord(
                    iteration=1,
                    name="write_file",
                    arguments_json='{"path": "f.py", "content": "def f(): return 2"}',
                    result="OK: wrote 18 bytes to f.py",
                    elapsed_seconds=0.01,
                    ok=True,
                ),
            ),
        ),
    )
    assert verdict.approved is True
    user_msg = llm.chat.call_args.kwargs["messages"][-1].content
    assert "f.py" in user_msg
    assert "verify_exit_code: 0" in user_msg


def test_judge_passes_workspace_file_content_to_llm(tmp_path: Path) -> None:
    """The verifier must include the current file content (post-edit) in the prompt."""
    (tmp_path / "fixed.py").write_text("def fixed(): return 42")
    llm = MagicMock()
    llm.chat.return_value = _resp(
        '{"approved": true, "reasoning": "ok", "feedback_for_executor": null}'
    )
    verifier = Verifier(llm=llm, model="m")
    verifier.judge(
        _task(tmp_path),
        _execution(
            tool_calls=(
                ToolCallRecord(
                    iteration=1,
                    name="write_file",
                    arguments_json='{"path": "fixed.py", "content": "ignored"}',
                    result="OK",
                    elapsed_seconds=0.01,
                    ok=True,
                ),
            ),
        ),
    )
    user_msg = llm.chat.call_args.kwargs["messages"][-1].content
    assert "def fixed(): return 42" in user_msg  # actual file content, not the arguments_json

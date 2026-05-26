"""Unit tests for Executor: tool loop termination, token accounting, verify decides success."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from issue_to_pr.executor import Executor, Task
from issue_to_pr.executor.executor import _build_user_prompt, _execute_tool
from issue_to_pr.llm import LLMResponse, LLMToolCall
from issue_to_pr.sandbox import LocalSubprocessRunner


def _make_llm(responses: list[LLMResponse]) -> MagicMock:
    """LLMClient mock that yields the queued responses in order."""
    mock = MagicMock()
    mock.chat.side_effect = responses
    return mock


def _resp(
    *,
    content: str = "",
    tool_calls: list[LLMToolCall] | None = None,
    finish: str = "stop",
    prompt_tokens: int = 100,
    completion_tokens: int = 20,
) -> LLMResponse:
    return LLMResponse(
        content=content,
        reasoning=None,
        tool_calls=tool_calls or [],
        finish_reason=finish,
        model="openai/gpt-oss-20b",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


@pytest.fixture()
def sandbox() -> LocalSubprocessRunner:
    return LocalSubprocessRunner(timeout_seconds=5)


def test_user_prompt_includes_id_description_and_verify() -> None:
    task = Task(
        id="t1",
        description="fix the bug",
        workspace=Path("/tmp/x"),
        verify_command="pytest -q",
    )
    prompt = _build_user_prompt(task)
    assert "t1" in prompt
    assert "fix the bug" in prompt
    assert "pytest -q" in prompt


def test_execute_tool_unknown_returns_error(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    out, ok, elapsed = _execute_tool("does_not_exist", "{}", tmp_path, sandbox)
    assert "unknown tool" in out
    assert ok is False
    assert elapsed == 0.0


def test_execute_tool_invalid_json_returns_error(
    tmp_path: Path, sandbox: LocalSubprocessRunner
) -> None:
    out, ok, _ = _execute_tool("read_file", "{not json", tmp_path, sandbox)
    assert "not valid JSON" in out
    assert ok is False


def test_execute_tool_classifies_error_string_as_not_ok(
    tmp_path: Path, sandbox: LocalSubprocessRunner
) -> None:
    out, ok, _ = _execute_tool("read_file", '{"path": "missing.txt"}', tmp_path, sandbox)
    assert out.startswith("ERROR")
    assert ok is False


def test_execute_tool_success_marks_ok(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    (tmp_path / "a.txt").write_text("hi")
    out, ok, elapsed = _execute_tool("read_file", '{"path": "a.txt"}', tmp_path, sandbox)
    assert out == "hi"
    assert ok is True
    assert elapsed >= 0


def test_executor_done_on_no_tool_calls(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    """One LLM turn with no tool_calls -> exit_reason='done'."""
    llm = _make_llm([_resp(content="DONE")])
    task = Task(
        id="t1",
        description="anything",
        workspace=tmp_path,
        verify_command="echo verified",
    )
    executor = Executor(llm=llm, sandbox=sandbox, model="x")
    result = executor.run(task)
    assert result.exit_reason == "done"
    assert result.iterations == 1
    assert result.success is True  # echo exit 0
    assert result.verify_exit_code == 0
    assert llm.chat.call_count == 1


def test_executor_runs_tool_then_done(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    (tmp_path / "f.txt").write_text("hello")
    llm = _make_llm(
        [
            _resp(
                tool_calls=[
                    LLMToolCall(id="c1", name="read_file", arguments_json='{"path":"f.txt"}')
                ],
                finish="tool_calls",
            ),
            _resp(content="DONE"),
        ]
    )
    task = Task(
        id="t1",
        description="read it",
        workspace=tmp_path,
        verify_command="echo ok",
    )
    result = Executor(llm=llm, sandbox=sandbox, model="x").run(task)
    assert result.exit_reason == "done"
    assert result.iterations == 2
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].ok is True


def test_executor_caps_at_max_iterations(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    """LLM keeps requesting tool calls -> stops at max_iterations."""
    loop_response = _resp(
        tool_calls=[LLMToolCall(id="c", name="list_dir", arguments_json='{"path":"."}')],
        finish="tool_calls",
    )
    llm = _make_llm([loop_response] * 10)
    task = Task(
        id="t1",
        description="loop forever",
        workspace=tmp_path,
        verify_command="echo done",
        max_iterations=3,
    )
    result = Executor(llm=llm, sandbox=sandbox, model="x").run(task)
    assert result.exit_reason == "max_iterations"
    assert result.iterations == 3
    assert len(result.tool_calls) == 3


def test_executor_accumulates_token_counts(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    llm = _make_llm(
        [
            _resp(
                tool_calls=[LLMToolCall(id="c", name="list_dir", arguments_json="{}")],
                finish="tool_calls",
                prompt_tokens=100,
                completion_tokens=10,
            ),
            _resp(content="DONE", prompt_tokens=120, completion_tokens=5),
        ]
    )
    task = Task(
        id="t1",
        description="counts",
        workspace=tmp_path,
        verify_command="echo go",
    )
    result = Executor(llm=llm, sandbox=sandbox, model="x").run(task)
    assert result.total_prompt_tokens == 220
    assert result.total_completion_tokens == 15
    assert result.total_tokens == 235


def test_executor_success_decided_by_verify_not_model_claim(
    tmp_path: Path, sandbox: LocalSubprocessRunner
) -> None:
    """Even if the model says DONE, success requires verify_command exit 0."""
    llm = _make_llm([_resp(content="DONE")])
    task = Task(
        id="t1",
        description="lying agent",
        workspace=tmp_path,
        verify_command='python -c "import sys; sys.exit(7)"',
    )
    result = Executor(llm=llm, sandbox=sandbox, model="x").run(task)
    assert result.success is False
    assert result.verify_exit_code == 7

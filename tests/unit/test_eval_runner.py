"""Unit tests for the eval runner: aggregation, JSON shape, threshold gate.

The runner is exercised with a mock Executor so these tests cost no API quota and run
deterministically. Real end-to-end coverage is in tests/integration/.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from evals import check_regression
from evals.runner import IssueResult, _run_one_executor, run_eval_set
from issue_to_pr.executor.types import ExecutionResult


def _fake_execution(*, success: bool, tokens: int = 50, iters: int = 3) -> ExecutionResult:
    return ExecutionResult(
        task_id="x",
        success=success,
        iterations=iters,
        exit_reason="done",
        final_assistant_content="DONE",
        total_prompt_tokens=tokens,
        total_completion_tokens=10,
        elapsed_seconds=1.5,
        verify_exit_code=0 if success else 1,
    )


@pytest.fixture()
def trivial_yaml(tmp_path: Path) -> Path:
    """Write a tiny passing issue YAML to a temp dir and return its path."""
    set_dir = tmp_path / "issues"
    set_dir.mkdir()
    yaml_path = set_dir / "001-noop.yaml"
    yaml_path.write_text(
        'id: "001-noop"\ndescription: noop\nfiles:\n  a.txt: hi\nverify_command: "echo ok"\n',
        encoding="utf-8",
    )
    return set_dir


def test_issue_result_to_dict_shape() -> None:
    r = IssueResult(
        id="x",
        success=True,
        iterations=3,
        exit_reason="done",
        prompt_tokens=100,
        completion_tokens=20,
        elapsed_seconds=1.2,
        verify_exit_code=0,
    )
    assert r.to_dict() == {
        "id": "x",
        "success": True,
        "iterations": 3,
        "exit_reason": "done",
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "elapsed_seconds": 1.2,
        "verify_exit_code": 0,
        "reflexion_iterations": 1,
        "verifier_approved": None,
    }


def test_run_one_passes_through_executor(trivial_yaml: Path) -> None:
    yaml_path = trivial_yaml / "001-noop.yaml"
    executor = MagicMock()
    executor.run.return_value = _fake_execution(success=True, tokens=42, iters=7)
    result = _run_one_executor(yaml_path, executor)
    assert result.id == "001-noop"
    assert result.success is True
    assert result.prompt_tokens == 42
    assert result.iterations == 7
    # workspace was passed; we don't care about exact path, just that .run was called once
    assert executor.run.call_count == 1


def test_run_eval_set_aggregates_resolved_at_1(trivial_yaml: Path) -> None:
    # Second YAML, will fail
    (trivial_yaml / "002-bad.yaml").write_text(
        'id: "002-bad"\ndescription: bad\nfiles:\n  a.txt: hi\nverify_command: "echo ok"\n',
        encoding="utf-8",
    )

    executor = MagicMock()
    executor.run.side_effect = [
        _fake_execution(success=True, tokens=10),
        _fake_execution(success=False, tokens=20),
    ]
    report = run_eval_set(trivial_yaml, executor=executor)
    assert report["total"] == 2
    assert report["solved"] == 1
    assert report["resolved_at_1"] == 0.5
    assert report["total_prompt_tokens"] == 30
    assert len(report["results"]) == 2


def test_run_eval_set_raises_when_no_yaml(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(RuntimeError, match="no YAML files"):
        run_eval_set(empty, executor=MagicMock())


def test_check_regression_passes_above_threshold(tmp_path: Path) -> None:
    report = tmp_path / "r.json"
    report.write_text(json.dumps({"resolved_at_1": 0.85, "total": 10, "solved": 9}))
    assert check_regression.main(["--report", str(report), "--threshold", "0.7"]) == 0


def test_check_regression_fails_below_threshold(tmp_path: Path) -> None:
    report = tmp_path / "r.json"
    report.write_text(json.dumps({"resolved_at_1": 0.5, "total": 10, "solved": 5}))
    assert check_regression.main(["--report", str(report), "--threshold", "0.7"]) == 1


def test_check_regression_missing_report_exits_2(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.json"
    assert check_regression.main(["--report", str(missing)]) == 2

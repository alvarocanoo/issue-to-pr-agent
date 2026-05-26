"""Unit tests for the Planner: JSON parsing, malformed fallback, executor brief format."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from issue_to_pr.executor.types import Task
from issue_to_pr.llm import LLMResponse
from issue_to_pr.planner import Plan, Planner
from issue_to_pr.planner.planner import _clean_list, _format_workspace_listing, _parse_plan


def _resp(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        reasoning=None,
        tool_calls=[],
        finish_reason="stop",
        model="m",
        prompt_tokens=10,
        completion_tokens=5,
    )


def test_plan_to_executor_brief_includes_sections() -> None:
    p = Plan(
        files_to_read=("a.py", "b.py"),
        files_to_modify=("a.py",),
        steps=("Read a.py", "Fix bug", "Run tests"),
    )
    out = p.to_executor_brief()
    assert "Read first" in out
    assert "a.py" in out
    assert "Likely to modify" in out
    assert "1. Read a.py" in out
    assert "3. Run tests" in out


def test_clean_list_filters_non_strings() -> None:
    assert _clean_list(["a", 1, "", None, "b"]) == ["a", "1", "b"]
    assert _clean_list("not a list") == []
    assert _clean_list(None) == []


def test_parse_plan_well_formed_json() -> None:
    raw = (
        '{"files_to_read": ["a.py"], '
        '"files_to_modify": ["a.py"], '
        '"steps": ["read", "edit", "verify"]}'
    )
    plan = _parse_plan(raw)
    assert plan.files_to_read == ("a.py",)
    assert plan.files_to_modify == ("a.py",)
    assert plan.steps == ("read", "edit", "verify")
    assert plan.raw_model_output == raw


def test_parse_plan_malformed_json_returns_empty_plan() -> None:
    plan = _parse_plan("not json at all")
    assert plan.files_to_read == ()
    assert plan.files_to_modify == ()
    assert plan.steps == ()


def test_parse_plan_empty_string_returns_empty_plan() -> None:
    plan = _parse_plan("")
    assert plan.files_to_read == ()
    assert plan.steps == ()


def test_parse_plan_partial_keys_handled() -> None:
    plan = _parse_plan('{"files_to_read": ["a"]}')
    assert plan.files_to_read == ("a",)
    assert plan.files_to_modify == ()
    assert plan.steps == ()


def test_format_workspace_listing_lists_files(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("y")
    listing = _format_workspace_listing(tmp_path)
    assert "a.py" in listing
    assert "sub" in listing
    assert "b.py" in listing


def test_format_workspace_listing_empty(tmp_path: Path) -> None:
    assert _format_workspace_listing(tmp_path) == "(workspace is empty)"


def test_format_workspace_listing_missing_dir() -> None:
    assert _format_workspace_listing(Path("/definitely/missing/9999")) == "(workspace is empty)"


def test_planner_invokes_llm_and_parses(tmp_path: Path) -> None:
    (tmp_path / "code.py").write_text("def f(): pass")
    llm = MagicMock()
    llm.chat.return_value = _resp(
        '{"files_to_read": ["code.py"], "files_to_modify": ["code.py"], "steps": ["fix"]}'
    )
    planner = Planner(llm=llm, model="gpt-oss-120b")
    task = Task(
        id="t1",
        description="bug",
        workspace=tmp_path,
        verify_command="pytest -q",
    )
    plan = planner.plan(task)
    assert plan.files_to_read == ("code.py",)
    assert plan.steps == ("fix",)
    # Workspace listing must be in the user prompt
    call = llm.chat.call_args
    user_message = call.kwargs["messages"][-1].content
    assert "code.py" in user_message
    assert "bug" in user_message


def test_planner_handles_non_dict_json_gracefully(tmp_path: Path) -> None:
    llm = MagicMock()
    llm.chat.return_value = _resp("[1, 2, 3]")  # JSON but not an object
    planner = Planner(llm=llm, model="m")
    plan = planner.plan(Task(id="t", description="", workspace=tmp_path, verify_command="echo ok"))
    assert plan.files_to_read == ()
    assert plan.steps == ()


def test_pytest_marker_present() -> None:
    """Anchor: keeps pytest import used so ruff cannot flag it as unused."""
    assert pytest is not None

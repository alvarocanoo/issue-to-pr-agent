"""Unit tests for executor tools: path safety, file IO, list_dir, bash via sandbox."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from issue_to_pr.executor.tools import (
    _safe_resolve,
    _truncate,
    bash,
    list_dir,
    read_file,
    write_file,
)
from issue_to_pr.sandbox import LocalSubprocessRunner
from issue_to_pr.sandbox.runner import (
    BlockedCommandError,
    SandboxResult,
    SandboxTimeoutError,
)


@pytest.fixture()
def sandbox() -> LocalSubprocessRunner:
    return LocalSubprocessRunner(timeout_seconds=5)


def test_safe_resolve_accepts_relative_subpath(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x")
    resolved = _safe_resolve(tmp_path, "a.txt")
    assert resolved == (tmp_path / "a.txt").resolve()


def test_safe_resolve_rejects_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes workspace"):
        _safe_resolve(tmp_path, "../outside.txt")


def test_safe_resolve_rejects_absolute_path(tmp_path: Path) -> None:
    abs_path = "/tmp/outside" if Path("/tmp").exists() else "C:\\Windows\\System32\\evil"
    with pytest.raises(ValueError, match="escapes workspace"):
        _safe_resolve(tmp_path, abs_path)


def test_safe_resolve_empty_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        _safe_resolve(tmp_path, "")


def test_truncate_under_limit() -> None:
    assert _truncate("hi", limit=5) == "hi"


def test_truncate_over_limit() -> None:
    out = _truncate("x" * 100, limit=10)
    assert out.startswith("x" * 10)
    assert "truncated 90" in out


def test_read_file_returns_content(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    (tmp_path / "f.txt").write_text("hello")
    assert read_file({"path": "f.txt"}, tmp_path, sandbox) == "hello"


def test_read_file_missing(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    out = read_file({"path": "nope.txt"}, tmp_path, sandbox)
    assert out.startswith("ERROR: file not found")


def test_read_file_path_traversal_blocked(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    out = read_file({"path": "../etc/passwd"}, tmp_path, sandbox)
    assert "escapes workspace" in out


def test_write_file_creates_parents(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    out = write_file({"path": "deep/nested/f.txt", "content": "x"}, tmp_path, sandbox)
    assert out.startswith("OK: wrote 1 bytes")
    assert (tmp_path / "deep" / "nested" / "f.txt").read_text() == "x"


def test_write_file_overwrites(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    (tmp_path / "f.txt").write_text("old")
    write_file({"path": "f.txt", "content": "new"}, tmp_path, sandbox)
    assert (tmp_path / "f.txt").read_text() == "new"


def test_write_file_non_string_content_rejected(
    tmp_path: Path, sandbox: LocalSubprocessRunner
) -> None:
    out = write_file({"path": "f.txt", "content": 42}, tmp_path, sandbox)
    assert out.startswith("ERROR: content must be a string")


def test_list_dir_lists_entries(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    (tmp_path / "a.txt").write_text("")
    (tmp_path / "sub").mkdir()
    out = list_dir({"path": "."}, tmp_path, sandbox)
    assert "a.txt" in out
    assert "sub/" in out


def test_list_dir_empty(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    assert list_dir({"path": "."}, tmp_path, sandbox) == "(empty)"


def test_list_dir_missing(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    out = list_dir({"path": "nope"}, tmp_path, sandbox)
    assert out.startswith("ERROR: not found")


def test_bash_empty_command_rejected(tmp_path: Path, sandbox: LocalSubprocessRunner) -> None:
    out = bash({"command": ""}, tmp_path, sandbox)
    assert "ERROR: command must be a non-empty string" in out


def test_bash_blocked_command_returns_error_string(tmp_path: Path) -> None:
    sandbox_mock = MagicMock()
    sandbox_mock.run.side_effect = BlockedCommandError("nope")
    out = bash({"command": "evil"}, tmp_path, sandbox_mock)
    assert "ERROR: BlockedCommandError: nope" in out


def test_bash_timeout_returns_error_string(tmp_path: Path) -> None:
    sandbox_mock = MagicMock()
    sandbox_mock.run.side_effect = SandboxTimeoutError("too slow")
    out = bash({"command": "anything"}, tmp_path, sandbox_mock)
    assert "ERROR: SandboxTimeoutError: too slow" in out


def test_bash_success_formats_full_output(tmp_path: Path) -> None:
    sandbox_mock = MagicMock()
    sandbox_mock.run.return_value = SandboxResult(
        command="echo hi",
        exit_code=0,
        stdout="hi\n",
        stderr="",
        elapsed_seconds=0.1,
        workspace=tmp_path,
        files_created=("new.txt",),
    )
    out = bash({"command": "echo hi"}, tmp_path, sandbox_mock)
    assert "exit_code=0" in out
    assert "hi" in out
    assert "created: ['new.txt']" in out

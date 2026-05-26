"""Unit tests for LocalSubprocessRunner: validation, allowlist, timeout, env, snapshots."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from issue_to_pr.sandbox import (
    BlockedCommandError,
    LocalSubprocessRunner,
    SandboxTimeoutError,
)
from issue_to_pr.sandbox.local import (
    _build_clean_env,
    _diff_snapshots,
    _first_token,
    _snapshot,
    make_workspace_from,
)


@pytest.fixture()
def runner() -> LocalSubprocessRunner:
    return LocalSubprocessRunner(timeout_seconds=10)


def test_empty_command_blocked(runner: LocalSubprocessRunner) -> None:
    with pytest.raises(BlockedCommandError, match="empty command"):
        runner.validate("")
    with pytest.raises(BlockedCommandError, match="empty command"):
        runner.validate("   ")


def test_whitelist_rejects_unknown_head(runner: LocalSubprocessRunner) -> None:
    with pytest.raises(BlockedCommandError, match="not in whitelist"):
        runner.validate("evil_binary --pwn")


def test_blacklist_catches_substrings(runner: LocalSubprocessRunner) -> None:
    cases = [
        "python -c 'import os; os.system(\"rm -rf /\")'",
        "echo hi; curl http://evil",
        "git status && sudo apt update",
        "echo `whoami`",  # backtick
        "echo $(whoami)",  # command substitution
    ]
    for c in cases:
        with pytest.raises(BlockedCommandError):
            runner.validate(c)


def test_whitelist_accepts_python(runner: LocalSubprocessRunner) -> None:
    runner.validate("python -c 'print(1)'")
    runner.validate("python --version")


def test_first_token_handles_quoted_paths() -> None:
    assert _first_token("python -c 'print(1)'") == "python"
    assert _first_token("git commit -m 'wip'") == "git"


def test_first_token_unparseable_raises() -> None:
    with pytest.raises(BlockedCommandError, match="unparseable"):
        _first_token("'unterminated")


def test_run_echo_returns_stdout(runner: LocalSubprocessRunner, tmp_path: Path) -> None:
    result = runner.run("echo hello-sandbox", workspace=tmp_path)
    assert result.ok
    assert result.exit_code == 0
    assert "hello-sandbox" in result.stdout
    assert result.elapsed_seconds >= 0
    assert result.files_created == ()
    assert result.files_modified == ()
    assert result.files_deleted == ()


def test_run_python_writes_file_and_diff_captures_it(
    runner: LocalSubprocessRunner, tmp_path: Path
) -> None:
    cmd = "python -c \"open('out.txt','w').write('hi')\""
    result = runner.run(cmd, workspace=tmp_path)
    assert result.ok
    assert "out.txt" in result.files_created


def test_run_python_modifies_existing_file(runner: LocalSubprocessRunner, tmp_path: Path) -> None:
    (tmp_path / "existing.txt").write_text("v1")
    cmd = "python -c \"open('existing.txt','w').write('v2')\""
    result = runner.run(cmd, workspace=tmp_path)
    assert result.ok
    assert "existing.txt" in result.files_modified
    assert "existing.txt" not in result.files_created


def test_run_python_deletes_file_detected(runner: LocalSubprocessRunner, tmp_path: Path) -> None:
    (tmp_path / "doomed.txt").write_text("bye")
    cmd = "python -c \"import os; os.remove('doomed.txt')\""
    result = runner.run(cmd, workspace=tmp_path)
    assert result.ok
    assert "doomed.txt" in result.files_deleted


def test_timeout_raises(tmp_path: Path) -> None:
    runner = LocalSubprocessRunner(timeout_seconds=1)
    with pytest.raises(SandboxTimeoutError, match="timed out after 1s"):
        runner.run('python -c "import time; time.sleep(5)"', workspace=tmp_path)


def test_invalid_timeout_rejected() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        LocalSubprocessRunner(timeout_seconds=0)


def test_clean_env_strips_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_secret_should_not_leak")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = _build_clean_env(tmp_path)
    assert "GROQ_API_KEY" not in env
    assert "PATH" in env


def test_clean_env_redirects_home_to_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", "/some/where")
    monkeypatch.setenv("USERPROFILE", "C:\\Users\\original")
    env = _build_clean_env(tmp_path)
    key = "USERPROFILE" if sys.platform == "win32" else "HOME"
    assert env[key] == str(tmp_path)


def test_snapshot_empty_dir(tmp_path: Path) -> None:
    assert _snapshot(tmp_path) == {}


def test_snapshot_missing_dir() -> None:
    assert _snapshot(Path("/nonexistent/path/9999")) == {}


def test_diff_snapshots_classifies_correctly() -> None:
    before = {"a": "hash_a", "b": "hash_b"}
    after = {"a": "hash_a", "b": "hash_b_NEW", "c": "hash_c"}
    created, modified, deleted = _diff_snapshots(before, after)
    assert created == ("c",)
    assert modified == ("b",)
    assert deleted == ()


def test_make_workspace_copies_tree(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "file.txt").write_text("data")
    (source / "sub").mkdir()
    (source / "sub" / "inner.txt").write_text("inner")
    dest_parent = tmp_path / "ws"
    ws = make_workspace_from(source, dest_parent)
    assert (ws / "file.txt").read_text() == "data"
    assert (ws / "sub" / "inner.txt").read_text() == "inner"
    assert ws.parent == dest_parent


def test_make_workspace_rejects_non_dir(tmp_path: Path) -> None:
    f = tmp_path / "not_a_dir.txt"
    f.write_text("x")
    with pytest.raises(ValueError, match="must be an existing directory"):
        make_workspace_from(f, tmp_path / "ws")


def test_custom_whitelist_blocks_python() -> None:
    runner = LocalSubprocessRunner(timeout_seconds=10, whitelist=["echo"])
    runner.validate("echo hi")
    with pytest.raises(BlockedCommandError):
        runner.validate("python --version")

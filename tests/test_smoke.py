"""Smoke tests: package imports, settings load, CLI invokes. Replaced as real components land."""

from __future__ import annotations

from typer.testing import CliRunner

from issue_to_pr import __version__
from issue_to_pr.cli import app
from issue_to_pr.settings import get_settings


def test_version_is_semver_like() -> None:
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_settings_load_with_defaults() -> None:
    s = get_settings()
    assert s.planner_model.startswith("claude-")
    assert s.executor_model.startswith("claude-")
    assert s.verifier_model.startswith("claude-")
    assert 60 <= s.sandbox_timeout_seconds <= 3600


def test_cli_version_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout

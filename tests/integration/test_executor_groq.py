"""End-to-end integration test: real Groq agent solves the 001-typo trivial issue."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from issue_to_pr.executor import Executor, Task
from issue_to_pr.issues import load_issue, materialise
from issue_to_pr.llm import LLMClient
from issue_to_pr.sandbox import LocalSubprocessRunner
from issue_to_pr.settings import get_settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("GROQ_API_KEY") and not get_settings().groq_api_key,
        reason="GROQ_API_KEY not set; skipping live Groq integration",
    ),
]


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_agent_resolves_trivial_typo_end_to_end() -> None:
    """Walking-skeleton end-to-end gate: agent fixes the typo and pytest passes."""
    spec = load_issue(REPO_ROOT / "evals" / "trivial_issues" / "001-typo.yaml")
    workspace = Path(tempfile.mkdtemp(prefix=f"itp-test-{spec.id}-"))
    try:
        materialise(spec, workspace)
        settings = get_settings()
        executor = Executor(
            llm=LLMClient(api_key=settings.groq_api_key),
            sandbox=LocalSubprocessRunner(timeout_seconds=60),
            model=settings.executor_model,
        )
        task = Task(
            id=spec.id,
            description=spec.description,
            workspace=workspace,
            verify_command=spec.verify_command,
            max_iterations=15,
        )
        result = executor.run(task)
        assert result.success is True, (
            f"agent failed to resolve issue. exit_reason={result.exit_reason} "
            f"verify_exit={result.verify_exit_code} "
            f"stdout={result.verify_stdout!r} stderr={result.verify_stderr!r}"
        )
        assert result.verify_exit_code == 0
        assert result.iterations <= 15
        assert result.total_tokens > 0
    finally:
        import shutil

        shutil.rmtree(workspace, ignore_errors=True)

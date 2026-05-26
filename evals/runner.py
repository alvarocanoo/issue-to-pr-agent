"""Run every issue in a set through the agent and emit a JSON report.

Invocation:
    uv run python -m evals.runner --set trivial [--out report.json]

Exit code reflects the regression gate (default threshold 0.70).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from issue_to_pr.executor import Executor, Task
from issue_to_pr.issues import load_issue, materialise
from issue_to_pr.llm import LLMClient
from issue_to_pr.sandbox import LocalSubprocessRunner
from issue_to_pr.settings import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class IssueResult:
    """Per-issue outcome shape used in the JSON report."""

    id: str
    success: bool
    iterations: int
    exit_reason: str
    prompt_tokens: int
    completion_tokens: int
    elapsed_seconds: float
    verify_exit_code: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "success": self.success,
            "iterations": self.iterations,
            "exit_reason": self.exit_reason,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "elapsed_seconds": self.elapsed_seconds,
            "verify_exit_code": self.verify_exit_code,
        }


def _run_one(yaml_path: Path, executor: Executor) -> IssueResult:
    """Resolve one issue end-to-end. Workspace is cleaned up after the run."""
    spec = load_issue(yaml_path)
    workspace = Path(tempfile.mkdtemp(prefix=f"itp-eval-{spec.id}-"))
    try:
        materialise(spec, workspace)
        task = Task(
            id=spec.id,
            description=spec.description,
            workspace=workspace,
            verify_command=spec.verify_command,
        )
        outcome = executor.run(task)
        return IssueResult(
            id=spec.id,
            success=outcome.success,
            iterations=outcome.iterations,
            exit_reason=outcome.exit_reason,
            prompt_tokens=outcome.total_prompt_tokens,
            completion_tokens=outcome.total_completion_tokens,
            elapsed_seconds=round(outcome.elapsed_seconds, 2),
            verify_exit_code=outcome.verify_exit_code,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _build_executor(settings: Settings) -> Executor:
    return Executor(
        llm=LLMClient(api_key=settings.groq_api_key),
        sandbox=LocalSubprocessRunner(timeout_seconds=60),
        model=settings.executor_model,
    )


def run_eval_set(set_dir: Path, *, executor: Executor | None = None) -> dict[str, Any]:
    """Run every `*.yaml` in `set_dir` and return an aggregated report dict."""
    yaml_files = sorted(set_dir.glob("*.yaml"))
    if not yaml_files:
        raise RuntimeError(f"no YAML files in {set_dir}")

    if executor is None:
        settings = get_settings()
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY not set in environment or .env")
        executor = _build_executor(settings)

    started = time.perf_counter()
    results: list[IssueResult] = []
    for yaml_path in yaml_files:
        print(f"[eval] running {yaml_path.name} ...", flush=True)
        result = _run_one(yaml_path, executor)
        status = "PASS" if result.success else "FAIL"
        print(
            f"[eval]   {status} id={result.id} iter={result.iterations} "
            f"tokens={result.prompt_tokens + result.completion_tokens} "
            f"elapsed={result.elapsed_seconds}s",
            flush=True,
        )
        results.append(result)
    total_elapsed = time.perf_counter() - started

    total = len(results)
    solved = sum(1 for r in results if r.success)
    try:
        set_dir_repr = str(set_dir.relative_to(REPO_ROOT))
    except ValueError:
        set_dir_repr = str(set_dir)
    return {
        "set_dir": set_dir_repr,
        "total": total,
        "solved": solved,
        "resolved_at_1": (solved / total) if total else 0.0,
        "total_prompt_tokens": sum(r.prompt_tokens for r in results),
        "total_completion_tokens": sum(r.completion_tokens for r in results),
        "total_elapsed_seconds": round(total_elapsed, 2),
        "results": [r.to_dict() for r in results],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an eval set with the agent.")
    parser.add_argument("--set", required=True, choices=["trivial"], help="Eval set name.")
    parser.add_argument("--out", type=Path, default=None, help="Optional JSON report destination.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.70,
        help="Minimum resolved@1 to exit 0; otherwise exit 1.",
    )
    args = parser.parse_args(argv)

    if args.set == "trivial":
        set_dir = REPO_ROOT / "evals" / "trivial_issues"
    else:
        raise SystemExit(f"unknown set: {args.set}")

    report = run_eval_set(set_dir)
    serialised = json.dumps(report, indent=2)
    print(serialised)
    if args.out:
        args.out.write_text(serialised, encoding="utf-8")
        print(f"[eval] report written to {args.out}", flush=True)

    return 0 if report["resolved_at_1"] >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())

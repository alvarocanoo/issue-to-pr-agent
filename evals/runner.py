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
from issue_to_pr.orchestrator import Orchestrator
from issue_to_pr.planner import Planner
from issue_to_pr.sandbox import LocalSubprocessRunner
from issue_to_pr.settings import Settings, get_settings
from issue_to_pr.storage import Storage
from issue_to_pr.verifier import Verifier

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
    reflexion_iterations: int = 1  # 1 with --executor-only; >=1 with orchestrator
    verifier_approved: bool | None = None  # None when running executor-only

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
            "reflexion_iterations": self.reflexion_iterations,
            "verifier_approved": self.verifier_approved,
        }


def _run_one_executor(
    yaml_path: Path,
    executor: Executor,
    storage: Storage | None = None,
) -> IssueResult:
    """Resolve one issue with the Executor only (baseline). Cleans workspace."""
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
        if storage is not None:
            try:
                storage.insert_run(
                    task_id=spec.id,
                    mode="executor",
                    success=outcome.success,
                    executor_iterations=outcome.iterations,
                    verify_exit_code=outcome.verify_exit_code,
                    prompt_tokens=outcome.total_prompt_tokens,
                    completion_tokens=outcome.total_completion_tokens,
                    elapsed_seconds=outcome.elapsed_seconds,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[eval]   WARNING: could not persist run {spec.id}: {exc}", flush=True)
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


def _run_one_orchestrator(
    yaml_path: Path,
    orchestrator: Orchestrator,
    storage: Storage | None = None,
) -> IssueResult:
    """Resolve one issue with the full Planner -> Executor -> Verifier loop.

    If `storage` is provided, the run is persisted immediately after the orchestrator
    returns (and BEFORE any later iteration that might rate-limit and crash).
    """
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
        outcome = orchestrator.run(task)
        final = outcome.final_execution
        if storage is not None:
            from dataclasses import asdict

            try:
                storage.insert_run(
                    task_id=spec.id,
                    mode="orchestrator",
                    success=outcome.success,
                    executor_iterations=final.iterations,
                    verify_exit_code=final.verify_exit_code,
                    prompt_tokens=outcome.total_prompt_tokens,
                    completion_tokens=outcome.total_completion_tokens,
                    elapsed_seconds=outcome.elapsed_seconds,
                    reflexion_iterations=outcome.reflexion_iterations,
                    plan=asdict(outcome.plan),
                    verdict=asdict(outcome.final_verdict),
                )
            except Exception as exc:  # noqa: BLE001  # persistence failure must not lose the result
                print(f"[eval]   WARNING: could not persist run {spec.id}: {exc}", flush=True)
        return IssueResult(
            id=spec.id,
            success=outcome.success,
            iterations=final.iterations,
            exit_reason=outcome.exit_reason,
            prompt_tokens=outcome.total_prompt_tokens,
            completion_tokens=outcome.total_completion_tokens,
            elapsed_seconds=round(outcome.elapsed_seconds, 2),
            verify_exit_code=final.verify_exit_code,
            reflexion_iterations=outcome.reflexion_iterations,
            verifier_approved=outcome.final_verdict.approved,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _build_executor(settings: Settings, llm: LLMClient) -> Executor:
    return Executor(
        llm=llm,
        sandbox=LocalSubprocessRunner(timeout_seconds=60),
        model=settings.executor_model,
    )


def _build_orchestrator(settings: Settings, llm: LLMClient) -> Orchestrator:
    return Orchestrator(
        planner=Planner(llm=llm, model=settings.planner_model),
        executor=_build_executor(settings, llm),
        verifier=Verifier(llm=llm, model=settings.verifier_model),
        max_reflexion_iterations=3,
    )


def run_eval_set(
    set_dir: Path,
    *,
    executor: Executor | None = None,
    orchestrator: Orchestrator | None = None,
    use_orchestrator: bool = True,
    storage: Storage | None = None,
) -> dict[str, Any]:
    """Run every `*.yaml` in `set_dir` and return an aggregated report dict.

    Inject `orchestrator` (preferred) or `executor` for tests; otherwise build from settings.
    `use_orchestrator=False` falls back to the executor-only path (baseline measurement).
    Pass `storage` to persist each run row-by-row (survives crashes / rate limits).
    """
    yaml_files = sorted(set_dir.glob("*.yaml"))
    if not yaml_files:
        raise RuntimeError(f"no YAML files in {set_dir}")

    if executor is None and orchestrator is None:
        settings = get_settings()
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY not set in environment or .env")
        llm = LLMClient(api_key=settings.groq_api_key)
        if use_orchestrator:
            orchestrator = _build_orchestrator(settings, llm)
        else:
            executor = _build_executor(settings, llm)

    started = time.perf_counter()
    results: list[IssueResult] = []
    for yaml_path in yaml_files:
        print(f"[eval] running {yaml_path.name} ...", flush=True)
        if orchestrator is not None:
            result = _run_one_orchestrator(yaml_path, orchestrator, storage=storage)
        else:
            assert executor is not None
            result = _run_one_executor(yaml_path, executor, storage=storage)
        status = "PASS" if result.success else "FAIL"
        suffix = (
            f" reflexion={result.reflexion_iterations} approved={result.verifier_approved}"
            if orchestrator is not None
            else ""
        )
        print(
            f"[eval]   {status} id={result.id} iter={result.iterations} "
            f"tokens={result.prompt_tokens + result.completion_tokens} "
            f"elapsed={result.elapsed_seconds}s{suffix}",
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
    parser.add_argument(
        "--executor-only",
        action="store_true",
        help="Baseline: skip Planner+Verifier, run the Executor directly.",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist the aggregate report to Postgres (uses DATABASE_URL).",
    )
    args = parser.parse_args(argv)

    if args.set == "trivial":
        set_dir = REPO_ROOT / "evals" / "trivial_issues"
    else:
        raise SystemExit(f"unknown set: {args.set}")

    storage: Storage | None = None
    if args.persist:
        settings = get_settings()
        storage = Storage(settings.database_url)
        storage.init_schema()
        print("[eval] persistence ON: each run is committed as it finishes", flush=True)

    report = run_eval_set(
        set_dir,
        use_orchestrator=not args.executor_only,
        storage=storage,
    )
    serialised = json.dumps(report, indent=2)
    print(serialised)
    if args.out:
        args.out.write_text(serialised, encoding="utf-8")
        print(f"[eval] report written to {args.out}", flush=True)

    if storage is not None:
        report_id = storage.insert_eval_report(
            set_name=args.set,
            mode="executor" if args.executor_only else "orchestrator",
            report=report,
        )
        print(f"[eval] aggregate report persisted as eval_reports.id={report_id}", flush=True)

    return 0 if report["resolved_at_1"] >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())

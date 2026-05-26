"""CLI entrypoint for issue-to-pr-agent."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from issue_to_pr import __version__
from issue_to_pr.executor import Executor, Task
from issue_to_pr.executor.types import ExecutionResult
from issue_to_pr.issues import load_issue, materialise
from issue_to_pr.llm import LLMClient
from issue_to_pr.orchestrator import Orchestrator, OrchestratorResult
from issue_to_pr.planner import Planner
from issue_to_pr.sandbox import LocalSubprocessRunner
from issue_to_pr.settings import get_settings
from issue_to_pr.verifier import Verifier

app = typer.Typer(
    name="issue-to-pr",
    help="Autonomous agent that turns a GitHub issue into a PR.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Print the package version."""
    console.print(f"issue-to-pr-agent [bold cyan]{__version__}[/bold cyan]")


@app.command()
def run(
    issue: Path = typer.Option(
        ..., "--issue", help="Path to a YAML eval issue (see evals/trivial_issues/*.yaml)."
    ),
    max_iterations: int = typer.Option(
        15, "--max-iterations", help="Hard cap on inner executor tool-loop iterations."
    ),
    timeout: int = typer.Option(
        60, "--timeout", help="Per-bash-command wall-clock timeout (seconds)."
    ),
    keep_workspace: bool = typer.Option(
        False, "--keep-workspace", help="Do not delete the temp workspace after the run."
    ),
    orchestrator: bool = typer.Option(
        True,
        "--orchestrator/--no-orchestrator",
        help=(
            "Use the full Planner -> Executor -> Verifier loop (default). "
            "With --no-orchestrator, run only the Executor (baseline)."
        ),
    ),
    max_reflexion: int = typer.Option(
        3, "--max-reflexion", help="Max outer Plan -> Execute -> Verify cycles."
    ),
) -> None:
    """Resolve a single trivial issue end-to-end and report metrics."""
    settings = get_settings()
    if not settings.groq_api_key:
        console.print("[red]GROQ_API_KEY not set in .env or environment[/red]")
        raise typer.Exit(code=2)
    if not issue.exists():
        console.print(f"[red]Issue file not found:[/red] {issue}")
        raise typer.Exit(code=2)

    spec = load_issue(issue)
    workspace = Path(tempfile.mkdtemp(prefix=f"itp-{spec.id}-"))
    materialise(spec, workspace)
    console.print(f"[cyan]workspace[/cyan]   {workspace}")
    console.print(f"[cyan]executor[/cyan]    {settings.executor_model}")
    if orchestrator:
        console.print(f"[cyan]planner[/cyan]     {settings.planner_model}")
        console.print(f"[cyan]verifier[/cyan]    {settings.verifier_model}")

    llm = LLMClient(api_key=settings.groq_api_key)
    sandbox = LocalSubprocessRunner(timeout_seconds=timeout)
    exec_engine = Executor(llm=llm, sandbox=sandbox, model=settings.executor_model)

    task = Task(
        id=spec.id,
        description=spec.description,
        workspace=workspace,
        verify_command=spec.verify_command,
        max_iterations=max_iterations,
    )

    success: bool
    try:
        if orchestrator:
            orch = Orchestrator(
                planner=Planner(llm=llm, model=settings.planner_model),
                executor=exec_engine,
                verifier=Verifier(llm=llm, model=settings.verifier_model),
                max_reflexion_iterations=max_reflexion,
            )
            with console.status(f"running orchestrator on issue {spec.id}…"):
                orch_result = orch.run(task)
            _print_orchestrator_summary(orch_result)
            success = orch_result.success
        else:
            with console.status(f"running executor on issue {spec.id}…"):
                exec_result = exec_engine.run(task)
            _print_executor_summary(exec_result)
            success = exec_result.success
    finally:
        if not keep_workspace:
            shutil.rmtree(workspace, ignore_errors=True)

    raise typer.Exit(code=0 if success else 1)


def _print_executor_summary(result: ExecutionResult) -> None:
    table = Table(title=f"Executor-only run report — {result.task_id}", show_header=False)
    table.add_column("metric", style="cyan", no_wrap=True)
    table.add_column("value")
    table.add_row("success", "[green]YES[/green]" if result.success else "[red]NO[/red]")
    table.add_row("exit_reason", result.exit_reason)
    table.add_row("iterations", str(result.iterations))
    table.add_row("tool_calls", str(len(result.tool_calls)))
    table.add_row("prompt_tokens", str(result.total_prompt_tokens))
    table.add_row("completion_tokens", str(result.total_completion_tokens))
    table.add_row("elapsed_seconds", f"{result.elapsed_seconds:.2f}")
    table.add_row("verify_exit_code", str(result.verify_exit_code))
    console.print(table)
    if not result.success and (result.verify_stdout or result.verify_stderr):
        console.print("\n[red]Verification failed.[/red]")
        if result.verify_stdout:
            console.print(f"\n[dim]--- stdout ---[/dim]\n{result.verify_stdout}")
        if result.verify_stderr:
            console.print(f"\n[dim]--- stderr ---[/dim]\n{result.verify_stderr}")


def _print_orchestrator_summary(result: OrchestratorResult) -> None:
    table = Table(title=f"Orchestrator run report — {result.task_id}", show_header=False)
    table.add_column("metric", style="cyan", no_wrap=True)
    table.add_column("value")
    table.add_row("success", "[green]YES[/green]" if result.success else "[red]NO[/red]")
    table.add_row("exit_reason", result.exit_reason)
    table.add_row("reflexion_iterations", str(result.reflexion_iterations))
    table.add_row("plan.steps", str(len(result.plan.steps)))
    table.add_row("plan.files_to_modify", str(list(result.plan.files_to_modify)))
    table.add_row("executor (final).iterations", str(result.final_execution.iterations))
    table.add_row("executor (final).tool_calls", str(len(result.final_execution.tool_calls)))
    table.add_row("verifier.approved", "yes" if result.final_verdict.approved else "no")
    table.add_row("total_prompt_tokens", str(result.total_prompt_tokens))
    table.add_row("total_completion_tokens", str(result.total_completion_tokens))
    table.add_row("elapsed_seconds", f"{result.elapsed_seconds:.2f}")
    table.add_row("verify_exit_code", str(result.final_execution.verify_exit_code))
    console.print(table)
    if not result.success:
        console.print(f"\n[yellow]Verifier reasoning:[/yellow] {result.final_verdict.reasoning}")
        if result.final_verdict.feedback_for_executor:
            console.print(
                f"[yellow]Feedback to next executor:[/yellow] "
                f"{result.final_verdict.feedback_for_executor}"
            )


if __name__ == "__main__":
    app()

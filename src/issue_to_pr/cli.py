"""CLI entrypoint for issue-to-pr-agent."""

from __future__ import annotations

import tempfile
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from issue_to_pr import __version__
from issue_to_pr.executor import Executor, Task
from issue_to_pr.issues import load_issue, materialise
from issue_to_pr.llm import LLMClient
from issue_to_pr.sandbox import LocalSubprocessRunner
from issue_to_pr.settings import get_settings

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
        15, "--max-iterations", help="Hard cap on tool-loop iterations."
    ),
    timeout: int = typer.Option(
        60, "--timeout", help="Per-bash-command wall-clock timeout (seconds)."
    ),
    keep_workspace: bool = typer.Option(
        False, "--keep-workspace", help="Do not delete the temp workspace after the run."
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
    console.print(f"[cyan]workspace[/cyan] {workspace}")
    console.print(f"[cyan]model[/cyan]     {settings.executor_model}")

    executor = Executor(
        llm=LLMClient(api_key=settings.groq_api_key),
        sandbox=LocalSubprocessRunner(timeout_seconds=timeout),
        model=settings.executor_model,
    )
    task = Task(
        id=spec.id,
        description=spec.description,
        workspace=workspace,
        verify_command=spec.verify_command,
        max_iterations=max_iterations,
    )

    with console.status(f"running agent on issue {spec.id}…"):
        result = executor.run(task)

    _print_summary(result)

    if not keep_workspace:
        # Best-effort cleanup. Skipping on error is fine — workspace is in temp dir.
        try:
            import shutil

            shutil.rmtree(workspace)
        except OSError:
            console.print(f"[yellow]could not clean workspace {workspace}[/yellow]")

    raise typer.Exit(code=0 if result.success else 1)


def _print_summary(result: object) -> None:
    """Render a small summary table for an ExecutionResult."""
    # local import to keep tests' import paths simple
    from issue_to_pr.executor.types import ExecutionResult

    assert isinstance(result, ExecutionResult)

    table = Table(title=f"Run report — {result.task_id}", show_header=False)
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

    if not result.success:
        console.print("\n[red]Verification failed.[/red]")
        if result.verify_stdout:
            console.print(f"\n[dim]--- stdout ---[/dim]\n{result.verify_stdout}")
        if result.verify_stderr:
            console.print(f"\n[dim]--- stderr ---[/dim]\n{result.verify_stderr}")


if __name__ == "__main__":
    app()

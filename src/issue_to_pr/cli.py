"""CLI entrypoint for issue-to-pr-agent.

`version` works now. `run` is a placeholder until Week 1 step 5 lands
(sandbox + executor + first trivial issue).
"""

from __future__ import annotations

import typer
from rich.console import Console

from issue_to_pr import __version__

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
    issue: str = typer.Option(
        ..., "--issue", help="Path to a YAML eval issue or a GitHub issue URL."
    ),
) -> None:
    """Resolve an issue and (eventually) open a PR. Not implemented yet - lands Week 1 step 5."""
    console.print(f"[yellow]run --issue {issue}[/yellow]")
    console.print("[red]not implemented yet[/red] — see roadmap in README.md")
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()

"""Dataclasses for executor inputs/outputs. Everything frozen for cheap equality + caching."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Task:
    """One job for the executor: solve an issue inside a workspace."""

    id: str
    description: str
    workspace: Path
    verify_command: str
    max_iterations: int = 15


@dataclass(frozen=True)
class ToolCallRecord:
    """Audit row for one tool invocation."""

    iteration: int
    name: str
    arguments_json: str
    result: str
    elapsed_seconds: float
    ok: bool


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of an executor run. `success` reflects the verify command, not the model's claim."""

    task_id: str
    success: bool
    iterations: int
    exit_reason: str  # "done", "max_iterations", "no_tool_calls_no_progress", "error"
    final_assistant_content: str
    tool_calls: tuple[ToolCallRecord, ...] = field(default_factory=tuple)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    elapsed_seconds: float = 0.0
    verify_exit_code: int = -1
    verify_stdout: str = ""
    verify_stderr: str = ""
    estimated_cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

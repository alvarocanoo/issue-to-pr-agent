"""Planner: one LLM call that reads the task + workspace listing and emits a JSON plan.

The plan is advisory, not binding. The Executor reads it as extra context but can deviate
(e.g., if its first tool call reveals the planner was wrong). The Verifier never sees the
plan; it judges the diff against the original task only.

We use the Groq JSON-mode (response_format=json_object) so the model is constrained to emit
parsable JSON. If JSON parsing still fails we return an empty `Plan` rather than crash —
the executor is responsible for the actual work, and an empty plan just means "no extra hints".
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from issue_to_pr.executor.types import Task
from issue_to_pr.llm import LLMClient, LLMMessage
from issue_to_pr.planner.types import Plan

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are the PLANNER for a coding agent.

You receive:
- A task description (a Python bug to fix).
- A listing of the workspace files.

You produce a short plan that an executor agent will follow. Do NOT write code; just plan.

Reply with a single JSON object with exactly these keys:
- "files_to_read": list of relative file paths the executor should read first.
- "files_to_modify": list of relative file paths the executor will likely need to change.
  Tests are usually NOT in this list (do not modify tests unless the task explicitly asks).
- "steps": list of 3 to 6 imperative one-line strings describing the order of operations.

Output JSON only. No markdown fences, no commentary."""


def _format_workspace_listing(workspace: Path) -> str:
    """Pretty-print one line per file in the workspace (depth-first, sorted)."""
    if not workspace.exists():
        return "(workspace is empty)"
    entries: list[str] = []
    for p in sorted(workspace.rglob("*")):
        if p.is_file():
            try:
                rel = p.relative_to(workspace)
            except ValueError:
                continue
            entries.append(str(rel))
    return "\n".join(entries) if entries else "(workspace is empty)"


def _build_user_prompt(task: Task, listing: str) -> str:
    return (
        f"Task id: {task.id}\n\n"
        f"Description:\n{task.description}\n\n"
        f"Verification command (this is what decides success):\n  {task.verify_command}\n\n"
        f"Workspace files:\n{listing}\n"
    )


def _parse_plan(raw: str) -> Plan:
    """Best-effort parse. Returns an empty plan if JSON is malformed."""
    if not raw.strip():
        return Plan(files_to_read=(), files_to_modify=(), steps=(), raw_model_output=raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("planner output not valid JSON; falling back to empty plan")
        return Plan(files_to_read=(), files_to_modify=(), steps=(), raw_model_output=raw)
    if not isinstance(data, dict):
        return Plan(files_to_read=(), files_to_modify=(), steps=(), raw_model_output=raw)
    return Plan(
        files_to_read=tuple(_clean_list(data.get("files_to_read"))),
        files_to_modify=tuple(_clean_list(data.get("files_to_modify"))),
        steps=tuple(_clean_list(data.get("steps"))),
        raw_model_output=raw,
    )


def _clean_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if isinstance(x, str | int | float) and str(x).strip()]


class Planner:
    """Wraps one LLM call that turns a Task into a structured Plan."""

    def __init__(self, *, llm: LLMClient, model: str, max_tokens: int = 1024) -> None:
        self._llm = llm
        self._model = model
        self._max_tokens = max_tokens

    def plan(self, task: Task) -> Plan:
        listing = _format_workspace_listing(task.workspace)
        messages = [
            LLMMessage(role="system", content=SYSTEM_PROMPT),
            LLMMessage(role="user", content=_build_user_prompt(task, listing)),
        ]
        resp = self._llm.chat(
            model=self._model,
            messages=messages,
            max_tokens=self._max_tokens,
        )
        return _parse_plan(resp.content)

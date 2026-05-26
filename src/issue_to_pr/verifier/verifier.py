"""Verifier: LLM-as-judge over the executor's diff + verify command result.

Inputs to the judge:
- The original task description.
- The list of files the executor created / modified / deleted (from the sandbox snapshot).
- The verify command result (exit code, stdout, stderr).
- A snapshot of each modified file's current content (so the judge can read the actual fix).

The verifier is intentionally read-only: no tool use, no shell, one chat call.

Approval rule:
- verify_exit_code MUST be 0 for approval.
- The diff must look like a minimal, on-topic fix.
- Test files must not be modified unless the task description explicitly asks.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from issue_to_pr.executor.types import ExecutionResult, Task
from issue_to_pr.llm import LLMClient, LLMMessage
from issue_to_pr.verifier.types import VerifierVerdict

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are the VERIFIER for a coding agent.

You judge whether the executor's work is acceptable to ship as a pull request.

Approval rules (ALL must hold):
1. The verify command must have exited with code 0.
2. The changes must look like a minimal, on-topic fix for the task.
3. Test files must NOT have been modified, unless the task explicitly says so.
4. No unrelated files should have been touched.

Reply with a single JSON object with exactly these keys:
- "approved": boolean.
- "reasoning": 1-3 sentences explaining the verdict.
- "feedback_for_executor": if NOT approved, one short paragraph telling the next executor
  attempt what to do differently. Use null if approved.

Output JSON only. No markdown fences, no commentary."""


def _truncate(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} more chars]"


def _read_file_safely(workspace: Path, rel_path: str) -> str:
    target = workspace / rel_path
    try:
        if not target.is_file():
            return "(not a file or missing)"
        return _truncate(target.read_text(encoding="utf-8"), limit=4000)
    except (OSError, UnicodeDecodeError) as exc:
        return f"(could not read: {exc})"


def _build_user_prompt(task: Task, run: ExecutionResult, workspace: Path) -> str:
    """Build the judge's user message with task + diff + verify outcome."""
    parts: list[str] = [
        f"Task id: {task.id}",
        f"\nTask description:\n{task.description}",
        f"\nVerify command: {task.verify_command}",
        f"verify_exit_code: {run.verify_exit_code}",
        f"verify_stdout:\n{_truncate(run.verify_stdout, 1500)}",
        f"verify_stderr:\n{_truncate(run.verify_stderr, 1500)}",
    ]

    if run.tool_calls:
        files_modified = {c.name: c for c in run.tool_calls if c.name == "write_file" and c.ok}
        if files_modified:
            parts.append(f"\nExecutor made {len(files_modified)} write_file calls during the run.")

    # Read each plausibly-modified file from the workspace and include its content.
    candidates: set[str] = set()
    for c in run.tool_calls:
        if c.name == "write_file" and c.ok:
            try:
                args = json.loads(c.arguments_json)
                path = args.get("path")
                if isinstance(path, str):
                    candidates.add(path)
            except json.JSONDecodeError:
                continue

    if candidates:
        parts.append("\n## Current content of files the executor wrote")
        for rel in sorted(candidates):
            parts.append(f"\n### `{rel}`")
            parts.append("```")
            parts.append(_read_file_safely(workspace, rel))
            parts.append("```")
    else:
        parts.append("\n(no file writes recorded in this run)")

    return "\n".join(parts)


def _parse_verdict(raw: str) -> VerifierVerdict:
    """Parse the judge's JSON output. Defensive: malformed JSON -> not approved."""
    if not raw.strip():
        return VerifierVerdict(
            approved=False,
            reasoning="verifier produced empty output",
            feedback_for_executor="Retry; the verifier could not parse the previous run.",
            raw_model_output=raw,
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("verifier output not valid JSON; treating as not approved")
        return VerifierVerdict(
            approved=False,
            reasoning="verifier output was not valid JSON",
            feedback_for_executor="Retry; ensure tests pass and the fix is minimal.",
            raw_model_output=raw,
        )
    if not isinstance(data, dict):
        return VerifierVerdict(
            approved=False,
            reasoning="verifier output was not a JSON object",
            raw_model_output=raw,
        )
    approved = bool(data.get("approved", False))
    reasoning = str(data.get("reasoning", "")).strip() or "(no reasoning)"
    feedback_raw = data.get("feedback_for_executor")
    feedback = (
        str(feedback_raw).strip()
        if isinstance(feedback_raw, str) and feedback_raw.strip()
        else None
    )
    return VerifierVerdict(
        approved=approved,
        reasoning=reasoning,
        feedback_for_executor=feedback,
        raw_model_output=raw,
    )


class Verifier:
    """One LLM-as-judge call. Approves or rejects an executor run with structured feedback."""

    def __init__(self, *, llm: LLMClient, model: str, max_tokens: int = 1024) -> None:
        self._llm = llm
        self._model = model
        self._max_tokens = max_tokens

    def judge(self, task: Task, run: ExecutionResult) -> VerifierVerdict:
        # Hard rule first: if the verify command failed, no judge call is needed.
        if run.verify_exit_code != 0:
            return VerifierVerdict(
                approved=False,
                reasoning=(
                    f"verify command exited with code {run.verify_exit_code}; "
                    "the fix is not yet correct"
                ),
                feedback_for_executor=(
                    "Tests are failing. Read the verify_stderr in the previous attempt to "
                    "identify the failing assertion and adjust the fix."
                ),
            )
        messages = [
            LLMMessage(role="system", content=SYSTEM_PROMPT),
            LLMMessage(role="user", content=_build_user_prompt(task, run, task.workspace)),
        ]
        resp = self._llm.chat(
            model=self._model,
            messages=messages,
            max_tokens=self._max_tokens,
        )
        return _parse_verdict(resp.content)

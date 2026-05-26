"""Hand-rolled tool loop over LLMClient + SandboxRunner.

Loop contract:
1. Send messages + tool schemas to the LLM.
2. If the response carries tool_calls, execute each in order, append a tool message
   per call, and iterate.
3. If the response carries no tool_calls, treat the assistant content as the final
   answer and break.
4. Cap at `task.max_iterations` to prevent runaway loops.
5. After the loop, run `task.verify_command` in the sandbox. Success is decided by
   that exit code, never by the model's self-report.

Reasoning-model note: gpt-oss-* return `message.reasoning` separately from `message.content`.
LLMClient captures both; we feed back only `content` to the conversation, never `reasoning`.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from issue_to_pr.executor.tools import TOOL_REGISTRY, TOOL_SCHEMAS
from issue_to_pr.executor.types import ExecutionResult, Task, ToolCallRecord
from issue_to_pr.llm import LLMClient, LLMMessage
from issue_to_pr.sandbox.runner import SandboxResult, SandboxRunner

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a coding agent operating inside an isolated Python workspace.

Available tools: read_file, write_file, list_dir, bash.

Workflow you must follow:
1. Use list_dir / read_file to understand the codebase before changing anything.
2. Use write_file to apply the smallest fix that addresses the task.
3. Use bash to run the verification command; if it fails, read the output and iterate.
4. When the verification command succeeds, reply with a single line: DONE.

Rules:
- Never modify the test files unless the task explicitly asks you to.
- Always run the verification command after editing.
- Keep tool calls minimal; each call has a real wall-clock cost.
"""


def _build_user_prompt(task: Task) -> str:
    return (
        f"Task id: {task.id}\n\n"
        f"Description:\n{task.description}\n\n"
        f"Verification command (this is what decides success):\n  {task.verify_command}\n"
    )


def _execute_tool(
    name: str,
    arguments_json: str,
    workspace: Any,
    sandbox: SandboxRunner,
) -> tuple[str, bool, float]:
    """Run one tool call. Returns (result_string, ok, elapsed_seconds)."""
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return (f"ERROR: unknown tool {name!r}", False, 0.0)
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError as e:
        return (f"ERROR: arguments not valid JSON: {e}", False, 0.0)
    start = time.perf_counter()
    try:
        result = fn(args, workspace, sandbox)
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.exception("tool %s raised", name)
        return (f"ERROR: {type(e).__name__}: {e}", False, elapsed)
    elapsed = time.perf_counter() - start
    ok = not result.startswith("ERROR")
    return (result, ok, elapsed)


def _run_verify(task: Task, sandbox: SandboxRunner) -> SandboxResult:
    return sandbox.run(task.verify_command, workspace=task.workspace)


class Executor:
    """Drive an LLM to solve a Task by calling registered tools in a loop."""

    def __init__(
        self,
        *,
        llm: LLMClient,
        sandbox: SandboxRunner,
        model: str,
        max_tokens: int = 4096,
    ) -> None:
        self._llm = llm
        self._sandbox = sandbox
        self._model = model
        self._max_tokens = max_tokens

    def run(self, task: Task) -> ExecutionResult:
        start = time.perf_counter()
        messages: list[LLMMessage] = [
            LLMMessage(role="system", content=SYSTEM_PROMPT),
            LLMMessage(role="user", content=_build_user_prompt(task)),
        ]
        tool_records: list[ToolCallRecord] = []
        total_prompt = 0
        total_completion = 0
        total_cost = 0.0
        exit_reason = "max_iterations"
        final_content = ""

        for iteration in range(1, task.max_iterations + 1):
            resp = self._llm.chat(
                model=self._model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                max_tokens=self._max_tokens,
            )
            total_prompt += resp.prompt_tokens
            total_completion += resp.completion_tokens
            total_cost += resp.estimated_cost_usd
            final_content = resp.content
            messages.append(LLMMessage(role="assistant", content=resp.content))

            if not resp.tool_calls:
                exit_reason = "done"
                break

            for tc in resp.tool_calls:
                result_str, ok, elapsed = _execute_tool(
                    tc.name, tc.arguments_json, task.workspace, self._sandbox
                )
                tool_records.append(
                    ToolCallRecord(
                        iteration=iteration,
                        name=tc.name,
                        arguments_json=tc.arguments_json,
                        result=result_str,
                        elapsed_seconds=elapsed,
                        ok=ok,
                    )
                )
                messages.append(
                    LLMMessage(
                        role="tool",
                        content=result_str,
                        tool_call_id=tc.id,
                        name=tc.name,
                    )
                )

        verify = _run_verify(task, self._sandbox)
        elapsed_total = time.perf_counter() - start

        return ExecutionResult(
            task_id=task.id,
            success=verify.exit_code == 0,
            iterations=min(iteration, task.max_iterations),
            exit_reason=exit_reason,
            final_assistant_content=final_content,
            tool_calls=tuple(tool_records),
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            elapsed_seconds=elapsed_total,
            verify_exit_code=verify.exit_code,
            verify_stdout=verify.stdout,
            verify_stderr=verify.stderr,
            estimated_cost_usd=total_cost,
        )

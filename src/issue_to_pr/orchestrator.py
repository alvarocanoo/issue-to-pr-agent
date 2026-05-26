"""Plan -> Execute -> Verify loop with Reflexion-style retries.

Architecture (see [ADR-002 / docs/adr/002-planner-executor-verifier.md]):

  Planner (one call)
      |
      v
  +-- Executor (tool loop, hand-rolled) ---+
  |        |                               |
  |        v                               |
  |   Verifier (LLM-as-judge)              |
  |        |                               |
  |   approved? --no--> feedback --> loop -+
  |        |
  |       yes
  v
  Result

`max_reflexion_iterations` caps the outer loop. The executor's own `max_iterations` caps the
inner tool loop. Both bound the runtime independently.

Each retry re-runs the executor on the same workspace with the verifier's feedback prepended
to the task description (`VerifierVerdict.to_executor_feedback()`).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace

from issue_to_pr.executor import Executor
from issue_to_pr.executor.types import ExecutionResult, Task
from issue_to_pr.planner import Plan, Planner
from issue_to_pr.verifier import Verifier, VerifierVerdict

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrchestratorResult:
    """Outcome of one Plan -> Execute -> Verify cycle (possibly with retries)."""

    task_id: str
    success: bool
    reflexion_iterations: int
    exit_reason: str  # "approved", "max_reflexion_iterations", "verify_failed_terminally"
    plan: Plan
    final_execution: ExecutionResult
    final_verdict: VerifierVerdict
    history: tuple[tuple[ExecutionResult, VerifierVerdict], ...] = field(default_factory=tuple)
    elapsed_seconds: float = 0.0

    @property
    def total_prompt_tokens(self) -> int:
        return sum(e.total_prompt_tokens for e, _ in self.history)

    @property
    def total_completion_tokens(self) -> int:
        return sum(e.total_completion_tokens for e, _ in self.history)


class Orchestrator:
    """Coordinates Planner, Executor and Verifier into one Reflexion-style loop."""

    def __init__(
        self,
        *,
        planner: Planner,
        executor: Executor,
        verifier: Verifier,
        max_reflexion_iterations: int = 3,
    ) -> None:
        if max_reflexion_iterations < 1:
            raise ValueError("max_reflexion_iterations must be >= 1")
        self._planner = planner
        self._executor = executor
        self._verifier = verifier
        self._max_iter = max_reflexion_iterations

    def run(self, task: Task) -> OrchestratorResult:
        start = time.perf_counter()
        plan = self._planner.plan(task)
        plan_brief = plan.to_executor_brief()

        history: list[tuple[ExecutionResult, VerifierVerdict]] = []
        feedback_brief = ""

        execution: ExecutionResult | None = None
        verdict: VerifierVerdict | None = None
        exit_reason = "max_reflexion_iterations"

        for iteration in range(1, self._max_iter + 1):
            augmented_description = self._build_description(task, plan_brief, feedback_brief)
            iter_task = replace(task, description=augmented_description)
            execution = self._executor.run(iter_task)
            verdict = self._verifier.judge(task, execution)
            history.append((execution, verdict))
            logger.info(
                "orchestrator iter=%s verify_exit=%s approved=%s",
                iteration,
                execution.verify_exit_code,
                verdict.approved,
            )
            if verdict.approved:
                exit_reason = "approved"
                break
            feedback_brief = verdict.to_executor_feedback()

        assert execution is not None and verdict is not None  # loop ran at least once
        elapsed = time.perf_counter() - start

        return OrchestratorResult(
            task_id=task.id,
            success=execution.verify_exit_code == 0 and verdict.approved,
            reflexion_iterations=len(history),
            exit_reason=exit_reason,
            plan=plan,
            final_execution=execution,
            final_verdict=verdict,
            history=tuple(history),
            elapsed_seconds=elapsed,
        )

    @staticmethod
    def _build_description(task: Task, plan_brief: str, feedback_brief: str) -> str:
        sections = [task.description.strip()]
        if plan_brief.strip():
            sections.append(plan_brief.strip())
        if feedback_brief.strip():
            sections.append(feedback_brief.strip())
        return "\n\n".join(sections)

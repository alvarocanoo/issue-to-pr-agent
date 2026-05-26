"""Dataclasses for the Verifier verdict."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifierVerdict:
    """Outcome of one LLM-as-judge call over an executor run.

    `approved` is the gate: True means the orchestrator should stop and report success.
    False means the orchestrator should re-run the executor with `feedback_for_executor`
    appended to the task description (Reflexion-style).
    """

    approved: bool
    reasoning: str
    feedback_for_executor: str | None = None
    raw_model_output: str = ""

    def to_executor_feedback(self) -> str:
        """Format the verdict as feedback prepended to the next executor task description."""
        if self.approved:
            return ""
        feedback = self.feedback_for_executor or "Previous attempt was rejected."
        return (
            "## Feedback from the previous attempt (rejected by the verifier)\n"
            f"Reason: {self.reasoning}\n"
            f"What to do differently: {feedback}\n"
        )

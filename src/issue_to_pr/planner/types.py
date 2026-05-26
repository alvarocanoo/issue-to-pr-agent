"""Dataclasses for the Planner output."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    """Structured plan emitted by the Planner. Consumed by the Executor as extra context."""

    files_to_read: tuple[str, ...]
    files_to_modify: tuple[str, ...]
    steps: tuple[str, ...]
    raw_model_output: str = ""  # for debugging; not used in subsequent prompts

    def to_executor_brief(self) -> str:
        """Format the plan as a short markdown block appended to the executor user prompt."""
        sections = ["## Plan from the planner agent"]
        if self.files_to_read:
            sections.append("**Read first**:")
            sections.extend(f"- {p}" for p in self.files_to_read)
        if self.files_to_modify:
            sections.append("\n**Likely to modify**:")
            sections.extend(f"- {p}" for p in self.files_to_modify)
        if self.steps:
            sections.append("\n**Steps**:")
            sections.extend(f"{i + 1}. {s}" for i, s in enumerate(self.steps))
        return "\n".join(sections)

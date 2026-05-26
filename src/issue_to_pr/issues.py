"""Load a trivial-issue YAML spec and materialise its files into a workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class IssueSpec:
    """A trivial-issue evaluation case stored as a YAML file under evals/trivial_issues/."""

    id: str
    description: str
    files: dict[str, str]
    verify_command: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IssueSpec:
        required = {"id", "description", "files", "verify_command"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"IssueSpec missing required keys: {sorted(missing)}")
        if not isinstance(data["files"], dict):
            raise ValueError("'files' must be a mapping of path -> content")
        for rel, content in data["files"].items():
            if not isinstance(rel, str) or not isinstance(content, str):
                raise ValueError(f"file entry {rel!r} must be str -> str")
        return cls(
            id=str(data["id"]),
            description=str(data["description"]),
            files=dict(data["files"]),
            verify_command=str(data["verify_command"]),
        )


def load_issue(path: Path) -> IssueSpec:
    """Parse `path` (a YAML file) into an `IssueSpec`."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level YAML must be a mapping, got {type(raw).__name__}")
    return IssueSpec.from_dict(raw)


def materialise(spec: IssueSpec, workspace: Path) -> None:
    """Write every file in `spec.files` into `workspace`. Creates parent dirs as needed."""
    workspace.mkdir(parents=True, exist_ok=True)
    for rel, content in spec.files.items():
        if rel.startswith("/") or ".." in Path(rel).parts:
            raise ValueError(f"IssueSpec file path escapes workspace: {rel!r}")
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

"""Tools the agent can call. Each tool is a callable + a JSON-schema entry passed to the LLM.

Path safety: every relative path is resolved against the workspace and rejected if it escapes
(via `..`, symlinks, absolute paths). The sandbox runner enforces a second line of defence on
shell commands.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from issue_to_pr.sandbox.runner import BlockedCommandError, SandboxRunner, SandboxTimeoutError

ToolFn = Callable[[dict[str, Any], Path, SandboxRunner], str]


def _safe_resolve(workspace: Path, rel_path: str) -> Path:
    """Resolve `rel_path` inside `workspace`. Raise ValueError on escape attempts."""
    if not rel_path:
        raise ValueError("path must be non-empty")
    candidate = (workspace / rel_path).resolve()
    workspace_resolved = workspace.resolve()
    try:
        candidate.relative_to(workspace_resolved)
    except ValueError as exc:
        raise ValueError(f"path escapes workspace: {rel_path}") from exc
    return candidate


def _truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} more chars]"


def read_file(args: dict[str, Any], workspace: Path, sandbox: SandboxRunner) -> str:  # noqa: ARG001  # sandbox unused (kept for uniform Tool signature)
    path = args.get("path", "")
    try:
        p = _safe_resolve(workspace, path)
    except ValueError as e:
        return f"ERROR: {e}"
    if not p.exists():
        return f"ERROR: file not found: {path}"
    if not p.is_file():
        return f"ERROR: not a file: {path}"
    try:
        return _truncate(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        return f"ERROR: {type(e).__name__}: {e}"


def write_file(args: dict[str, Any], workspace: Path, sandbox: SandboxRunner) -> str:  # noqa: ARG001  # sandbox unused (kept for uniform Tool signature)
    path = args.get("path", "")
    content = args.get("content", "")
    if not isinstance(content, str):
        return "ERROR: content must be a string"
    try:
        p = _safe_resolve(workspace, path)
    except ValueError as e:
        return f"ERROR: {e}"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except OSError as e:
        return f"ERROR: {type(e).__name__}: {e}"
    return f"OK: wrote {len(content)} bytes to {path}"


def list_dir(args: dict[str, Any], workspace: Path, sandbox: SandboxRunner) -> str:  # noqa: ARG001  # sandbox unused (kept for uniform Tool signature)
    path = args.get("path", ".")
    try:
        p = _safe_resolve(workspace, path)
    except ValueError as e:
        return f"ERROR: {e}"
    if not p.exists():
        return f"ERROR: not found: {path}"
    if not p.is_dir():
        return f"ERROR: not a directory: {path}"
    entries: list[str] = []
    for child in sorted(p.iterdir()):
        suffix = "/" if child.is_dir() else ""
        entries.append(f"{child.name}{suffix}")
    return "\n".join(entries) if entries else "(empty)"


def bash(args: dict[str, Any], workspace: Path, sandbox: SandboxRunner) -> str:
    command = args.get("command", "")
    if not isinstance(command, str) or not command.strip():
        return "ERROR: command must be a non-empty string"
    try:
        result = sandbox.run(command, workspace=workspace)
    except BlockedCommandError as e:
        return f"ERROR: BlockedCommandError: {e}"
    except SandboxTimeoutError as e:
        return f"ERROR: SandboxTimeoutError: {e}"
    sections = [
        f"exit_code={result.exit_code}",
        f"elapsed_seconds={result.elapsed_seconds:.2f}",
        "--- stdout ---",
        _truncate(result.stdout),
        "--- stderr ---",
        _truncate(result.stderr),
    ]
    if result.files_created or result.files_modified or result.files_deleted:
        sections.append("--- files ---")
        if result.files_created:
            sections.append(f"created: {list(result.files_created)}")
        if result.files_modified:
            sections.append(f"modified: {list(result.files_modified)}")
        if result.files_deleted:
            sections.append(f"deleted: {list(result.files_deleted)}")
    return "\n".join(sections)


TOOL_REGISTRY: dict[str, ToolFn] = {
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
    "bash": bash,
}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file from the workspace and return its content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside the workspace."}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create or overwrite a file in the workspace. Parents are created if missing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path inside the workspace.",
                    },
                    "content": {"type": "string", "description": "Full file contents to write."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List the entries in a workspace directory (subdirs end with '/').",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path inside the workspace. Defaults to '.'.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Run a shell command inside the sandboxed workspace. Subject to a strict "
                "whitelist (python, pytest, git, ruff, ls, cat, echo, grep, find, ...) and a "
                "blacklist (rm -rf, curl, sudo, command substitution, ...). Use this to run tests."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute."}
                },
                "required": ["command"],
            },
        },
    },
]

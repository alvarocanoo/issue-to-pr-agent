"""Sandbox interface + shared types.

Two implementations live in sibling modules:
- `local.LocalSubprocessRunner`: no admin needed, isolates filesystem (tempdir + cleared env)
  and commands (whitelist + blacklist). Does NOT isolate network or memory. ADR-003.
- (planned) `container.ContainerRunner`: Podman per-task, `--network none`, memory cap.
  Wire when Podman is installed.

Both implementations share `SandboxRunner` so the executor swaps via config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class SandboxError(Exception):
    """Base for all sandbox-level failures."""


class BlockedCommandError(SandboxError):
    """Raised when a command is rejected by the whitelist / blacklist."""


class SandboxTimeoutError(SandboxError):
    """Raised when a command exceeds the configured timeout."""


# Commands the agent can run by default. Extend per-project via SandboxRunner constructor.
DEFAULT_WHITELIST: tuple[str, ...] = (
    "python",
    "python3",
    "pytest",
    "pip",
    "uv",
    "ruff",
    "mypy",
    "ls",
    "cat",
    "echo",
    "pwd",
    "grep",
    "find",
    "git",
    "diff",
)

# Substrings that immediately reject a command — never the full bash semantics, just first defence.
DEFAULT_BLACKLIST: tuple[str, ...] = (
    "rm -rf",
    "rm -fr",
    "sudo",
    "curl",
    "wget",
    "ssh",
    "scp",
    "ftp",
    "nc ",
    "ncat",
    "telnet",
    "chmod 777",
    "chown",
    "dd if=",
    "mkfs",
    "shutdown",
    "reboot",
    "kill -9",
    ":(){",  # fork bomb
    "&&:",
    ">/dev/",
    "> /dev/",
    "$(",  # command substitution — too easy to smuggle
    "`",  # backtick command substitution
)


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of a single sandboxed command."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    workspace: Path
    files_created: tuple[str, ...] = field(default_factory=tuple)
    files_modified: tuple[str, ...] = field(default_factory=tuple)
    files_deleted: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class SandboxRunner(Protocol):
    """Run a single command in an isolated workspace."""

    def run(self, command: str, *, workspace: Path) -> SandboxResult:
        """Execute `command` with `workspace` as CWD.

        Implementations MUST:
        - Reject commands blocked by whitelist/blacklist (raise BlockedCommandError).
        - Enforce a wall-clock timeout (raise SandboxTimeoutError on overrun).
        - Capture stdout / stderr / exit code.
        - Report filesystem diff (created / modified / deleted) relative to a pre-run snapshot.
        """
        ...

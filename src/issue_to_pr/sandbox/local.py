"""`LocalSubprocessRunner`: filesystem + command isolation without admin.

Threat model (ADR-003):
- IN scope: prevent the agent from clobbering files outside the workspace; prevent obvious
  destructive commands (rm -rf, curl, etc.); enforce wall-clock timeout.
- NOT in scope: network isolation, memory limits, sibling-process visibility, kernel-level
  isolation. Production runs MUST use the container runner.
"""

from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path

from issue_to_pr.sandbox.runner import (
    DEFAULT_BLACKLIST,
    DEFAULT_WHITELIST,
    BlockedCommandError,
    SandboxResult,
    SandboxTimeoutError,
)

# Env vars we keep on Windows so Python/uv/git can find themselves. Anything else is dropped.
_WINDOWS_SAFE_ENV: tuple[str, ...] = (
    "PATH",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "PATHEXT",
    "COMSPEC",
    "USERPROFILE",  # uv needs this for cache discovery on Windows
)
_POSIX_SAFE_ENV: tuple[str, ...] = ("PATH", "HOME", "LANG", "LC_ALL")


def _build_clean_env(workspace: Path) -> dict[str, str]:
    """Strip env down to what tooling needs; everything else (including the API key) gone."""
    keep = _WINDOWS_SAFE_ENV if sys.platform == "win32" else _POSIX_SAFE_ENV
    env = {k: os.environ[k] for k in keep if k in os.environ}
    # Point HOME/USERPROFILE at the workspace so accidental writes land inside it, not in ~/.
    if sys.platform == "win32":
        env["USERPROFILE"] = str(workspace)
    else:
        env["HOME"] = str(workspace)
    return env


def _snapshot(workspace: Path) -> dict[str, str]:
    """Map of relative-path -> sha256 hex for every file in workspace. Empty for missing dirs."""
    if not workspace.exists():
        return {}
    snap: dict[str, str] = {}
    for p in workspace.rglob("*"):
        if not p.is_file():
            continue
        try:
            data = p.read_bytes()
        except OSError:
            continue
        rel = str(p.relative_to(workspace))
        snap[rel] = hashlib.sha256(data).hexdigest()
    return snap


def _diff_snapshots(
    before: dict[str, str], after: dict[str, str]
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Return (created, modified, deleted) tuples sorted alphabetically."""
    before_keys = set(before)
    after_keys = set(after)
    created = sorted(after_keys - before_keys)
    deleted = sorted(before_keys - after_keys)
    modified = sorted(k for k in before_keys & after_keys if before[k] != after[k])
    return tuple(created), tuple(modified), tuple(deleted)


def _first_token(command: str) -> str:
    """Best-effort first token; handles posix and windows quoting."""
    try:
        tokens = shlex.split(command, posix=sys.platform != "win32")
    except ValueError as exc:
        raise BlockedCommandError(f"unparseable command: {command!r}") from exc
    if not tokens:
        raise BlockedCommandError("empty command")
    return os.path.basename(tokens[0])


class LocalSubprocessRunner:
    """Run shell commands in a workspace with a cleared env, whitelist and timeout.

    NOT a security boundary against a determined adversary. Defence in depth: most LLM-generated
    "destructive" commands die at the whitelist or the blacklist long before reaching the shell.
    """

    def __init__(
        self,
        *,
        timeout_seconds: int = 60,
        whitelist: Iterable[str] = DEFAULT_WHITELIST,
        blacklist: Iterable[str] = DEFAULT_BLACKLIST,
        shell: bool = True,
    ) -> None:
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be >= 1")
        self._timeout = timeout_seconds
        self._whitelist = tuple(whitelist)
        self._blacklist = tuple(blacklist)
        self._shell = shell

    def validate(self, command: str) -> None:
        """Raise BlockedCommandError if the command violates whitelist or blacklist.

        Public so the executor can pre-check before logging anything.
        """
        if not command.strip():
            raise BlockedCommandError("empty command")
        lowered = command.lower()
        for needle in self._blacklist:
            if needle in lowered:
                raise BlockedCommandError(f"blacklisted token {needle!r} in command")
        head = _first_token(command)
        if head not in self._whitelist:
            raise BlockedCommandError(f"command head {head!r} not in whitelist {self._whitelist}")

    def run(self, command: str, *, workspace: Path) -> SandboxResult:
        self.validate(command)
        workspace.mkdir(parents=True, exist_ok=True)

        before = _snapshot(workspace)
        env = _build_clean_env(workspace)
        start = time.perf_counter()
        try:
            proc = subprocess.run(  # noqa: S603  # shell=True + validated command — see threat model
                command,
                cwd=workspace,
                env=env,
                shell=self._shell,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.perf_counter() - start
            raise SandboxTimeoutError(
                f"command timed out after {self._timeout}s: {command!r}"
            ) from exc
        elapsed = time.perf_counter() - start

        after = _snapshot(workspace)
        created, modified, deleted = _diff_snapshots(before, after)

        return SandboxResult(
            command=command,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            elapsed_seconds=elapsed,
            workspace=workspace,
            files_created=created,
            files_modified=modified,
            files_deleted=deleted,
        )


def make_workspace_from(source: Path, dest_parent: Path) -> Path:
    """Copy `source` directory tree into a fresh subdir of `dest_parent`. Returns the new path."""
    if not source.is_dir():
        raise ValueError(f"source must be an existing directory: {source}")
    dest_parent.mkdir(parents=True, exist_ok=True)
    workspace = dest_parent / f"ws-{int(time.time() * 1000)}"
    shutil.copytree(source, workspace)
    return workspace

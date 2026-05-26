"""FastAPI surface for the agent. Read-only over the `runs` table for now."""

from issue_to_pr.api.server import build_app

__all__ = ["build_app"]

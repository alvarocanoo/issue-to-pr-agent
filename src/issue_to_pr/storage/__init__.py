"""Postgres persistence for agent runs and eval reports.

We use psycopg3 in synchronous mode because the runner is a CLI script, not a server.
FastAPI integration (Week 3.2) can wrap the same calls in run_in_executor or move to
the asyncpg variant if profiling shows it matters.
"""

from issue_to_pr.storage.db import Storage, build_dsn

__all__ = ["Storage", "build_dsn"]

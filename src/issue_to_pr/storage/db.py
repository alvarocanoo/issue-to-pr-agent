"""psycopg3 sync wrapper over the `runs` and `eval_reports` tables."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def build_dsn(url: str) -> str:
    """Return the DSN unchanged for now; centralised in case we add SSL / pool params later."""
    return url


@dataclass(frozen=True)
class StoredRun:
    """Subset of a run row useful to the API. Mirrors the columns we expose to readers."""

    id: int
    task_id: str
    mode: str
    success: bool
    reflexion_iterations: int | None
    executor_iterations: int
    verify_exit_code: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    elapsed_seconds: float
    started_at: str  # ISO 8601 (timestamptz cast to str by psycopg dict_row)
    finished_at: str | None
    plan: dict[str, Any]
    verdict: dict[str, Any]
    history: list[dict[str, Any]]


class Storage:
    """Thin wrapper around a psycopg3 connection. One instance per process is enough."""

    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("Storage requires a non-empty DSN")
        self._dsn = build_dsn(dsn)

    @contextmanager
    def connect(self) -> Any:
        """Open a fresh autocommit connection. Caller is responsible for closing."""
        conn = psycopg.connect(self._dsn, autocommit=True)
        try:
            yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Apply schema.sql idempotently."""
        ddl = SCHEMA_FILE.read_text(encoding="utf-8")
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(ddl)
        logger.info("schema applied from %s", SCHEMA_FILE)

    def insert_run(
        self,
        *,
        task_id: str,
        mode: str,
        success: bool,
        executor_iterations: int,
        verify_exit_code: int,
        prompt_tokens: int,
        completion_tokens: int,
        elapsed_seconds: float,
        estimated_cost_usd: float = 0.0,
        reflexion_iterations: int | None = None,
        plan: dict[str, Any] | None = None,
        verdict: dict[str, Any] | None = None,
        history: list[Any] | None = None,
    ) -> int:
        """Insert one run row. Returns the new id."""
        if mode not in ("executor", "orchestrator"):
            raise ValueError(f"mode must be 'executor' or 'orchestrator', got {mode!r}")
        sql = """
            INSERT INTO runs (
                task_id, mode, success, reflexion_iterations, executor_iterations,
                verify_exit_code, prompt_tokens, completion_tokens, estimated_cost_usd,
                elapsed_seconds, plan, verdict, history, finished_at
            )
            VALUES (
                %(task_id)s, %(mode)s, %(success)s, %(reflexion_iterations)s,
                %(executor_iterations)s, %(verify_exit_code)s, %(prompt_tokens)s,
                %(completion_tokens)s, %(estimated_cost_usd)s, %(elapsed_seconds)s,
                %(plan)s::jsonb, %(verdict)s::jsonb, %(history)s::jsonb, NOW()
            )
            RETURNING id
        """
        params = {
            "task_id": task_id,
            "mode": mode,
            "success": success,
            "reflexion_iterations": reflexion_iterations,
            "executor_iterations": executor_iterations,
            "verify_exit_code": verify_exit_code,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_cost_usd": estimated_cost_usd,
            "elapsed_seconds": elapsed_seconds,
            "plan": json.dumps(plan or {}),
            "verdict": json.dumps(verdict or {}),
            "history": json.dumps(history or []),
        }
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            assert row is not None
            return cast(int, row[0])

    def insert_eval_report(
        self,
        *,
        set_name: str,
        mode: str,
        report: dict[str, Any],
    ) -> int:
        """Persist a runner aggregate report. Returns the new id."""
        if mode not in ("executor", "orchestrator"):
            raise ValueError(f"mode must be 'executor' or 'orchestrator', got {mode!r}")
        sql = """
            INSERT INTO eval_reports (
                set_name, mode, total, solved, resolved_at_1,
                total_prompt_tokens, total_completion_tokens, total_elapsed_seconds, raw
            )
            VALUES (
                %(set_name)s, %(mode)s, %(total)s, %(solved)s, %(resolved_at_1)s,
                %(prompt_tokens)s, %(completion_tokens)s, %(elapsed)s, %(raw)s::jsonb
            )
            RETURNING id
        """
        params = {
            "set_name": set_name,
            "mode": mode,
            "total": int(report["total"]),
            "solved": int(report["solved"]),
            "resolved_at_1": float(report["resolved_at_1"]),
            "prompt_tokens": int(report["total_prompt_tokens"]),
            "completion_tokens": int(report["total_completion_tokens"]),
            "elapsed": float(report["total_elapsed_seconds"]),
            "raw": json.dumps(report),
        }
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            assert row is not None
            return cast(int, row[0])

    def list_runs(self, *, limit: int = 50, offset: int = 0) -> list[StoredRun]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be in 1..500")
        sql = """
            SELECT id, task_id, mode, success, reflexion_iterations, executor_iterations,
                   verify_exit_code, prompt_tokens, completion_tokens, estimated_cost_usd,
                   elapsed_seconds,
                   started_at::text AS started_at,
                   finished_at::text AS finished_at,
                   plan, verdict, history
            FROM runs
            ORDER BY started_at DESC
            LIMIT %(limit)s OFFSET %(offset)s
        """
        with self.connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, {"limit": limit, "offset": offset})
            rows = cur.fetchall()
        return [self._row_to_run(row) for row in rows]

    def get_run(self, run_id: int) -> StoredRun | None:
        sql = """
            SELECT id, task_id, mode, success, reflexion_iterations, executor_iterations,
                   verify_exit_code, prompt_tokens, completion_tokens, estimated_cost_usd,
                   elapsed_seconds,
                   started_at::text AS started_at,
                   finished_at::text AS finished_at,
                   plan, verdict, history
            FROM runs
            WHERE id = %(id)s
        """
        with self.connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, {"id": run_id})
            row = cur.fetchone()
        return None if row is None else self._row_to_run(row)

    @staticmethod
    def _row_to_run(row: dict[str, Any]) -> StoredRun:
        return StoredRun(
            id=row["id"],
            task_id=row["task_id"],
            mode=row["mode"],
            success=row["success"],
            reflexion_iterations=row["reflexion_iterations"],
            executor_iterations=row["executor_iterations"],
            verify_exit_code=row["verify_exit_code"],
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            estimated_cost_usd=row.get("estimated_cost_usd") or 0.0,
            elapsed_seconds=row["elapsed_seconds"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            plan=row["plan"] or {},
            verdict=row["verdict"] or {},
            history=row.get("history") or [],
        )

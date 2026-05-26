"""Unit tests for Storage that hit a real Postgres if available; otherwise skip.

A local pgsql-portable instance under DATABASE_URL is the dev environment. CI does not
yet run Postgres for this test (the integration story is via FastAPI + docker-compose later),
so the suite is gated by `pytest.importorskip` on a real DB connection.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg
import pytest

from issue_to_pr.storage import Storage

_DSN = os.environ.get("DATABASE_URL", "postgresql://itp@localhost:5432/itp")


def _can_connect(dsn: str) -> bool:
    try:
        with psycopg.connect(dsn, connect_timeout=2):
            return True
    except psycopg.Error:
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect(_DSN),
    reason=f"no Postgres reachable at {_DSN}",
)


@pytest.fixture()
def storage() -> Storage:
    s = Storage(_DSN)
    s.init_schema()
    # Clean the tables before each test to keep assertions deterministic.
    with s.connect() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE runs RESTART IDENTITY")
        cur.execute("TRUNCATE TABLE eval_reports RESTART IDENTITY")
    return s


def test_insert_and_get_run_roundtrip(storage: Storage) -> None:
    run_id = storage.insert_run(
        task_id="t-1",
        mode="orchestrator",
        success=True,
        executor_iterations=3,
        verify_exit_code=0,
        prompt_tokens=100,
        completion_tokens=10,
        elapsed_seconds=1.5,
        reflexion_iterations=1,
        plan={"steps": ["read", "edit"], "files_to_modify": ["a.py"]},
        verdict={"approved": True, "reasoning": "ok"},
    )
    assert run_id == 1
    fetched = storage.get_run(run_id)
    assert fetched is not None
    assert fetched.task_id == "t-1"
    assert fetched.mode == "orchestrator"
    assert fetched.plan["steps"] == ["read", "edit"]
    assert fetched.verdict["approved"] is True


def test_list_runs_newest_first(storage: Storage) -> None:
    for i in range(3):
        storage.insert_run(
            task_id=f"t-{i}",
            mode="executor",
            success=(i % 2 == 0),
            executor_iterations=i + 1,
            verify_exit_code=0 if i % 2 == 0 else 1,
            prompt_tokens=10 * i,
            completion_tokens=i,
            elapsed_seconds=float(i),
        )
    runs = storage.list_runs(limit=10)
    assert len(runs) == 3
    # Newest first
    assert runs[0].task_id == "t-2"
    assert runs[-1].task_id == "t-0"


def test_list_runs_respects_limit_and_offset(storage: Storage) -> None:
    for i in range(5):
        storage.insert_run(
            task_id=f"t-{i}",
            mode="executor",
            success=True,
            executor_iterations=1,
            verify_exit_code=0,
            prompt_tokens=0,
            completion_tokens=0,
            elapsed_seconds=0.1,
        )
    page1 = storage.list_runs(limit=2, offset=0)
    page2 = storage.list_runs(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].id != page2[0].id


def test_get_run_missing_returns_none(storage: Storage) -> None:
    assert storage.get_run(999_999) is None


def test_insert_eval_report_returns_id(storage: Storage) -> None:
    sample: dict[str, Any] = {
        "set_dir": "evals/trivial_issues",
        "total": 2,
        "solved": 2,
        "resolved_at_1": 1.0,
        "total_prompt_tokens": 100,
        "total_completion_tokens": 20,
        "total_elapsed_seconds": 5.0,
        "results": [],
    }
    rid = storage.insert_eval_report(set_name="trivial", mode="orchestrator", report=sample)
    assert rid == 1


def test_insert_run_rejects_invalid_mode(storage: Storage) -> None:
    with pytest.raises(ValueError, match="mode"):
        storage.insert_run(
            task_id="t",
            mode="banana",
            success=True,
            executor_iterations=1,
            verify_exit_code=0,
            prompt_tokens=0,
            completion_tokens=0,
            elapsed_seconds=0.1,
        )


def test_init_schema_is_idempotent(storage: Storage) -> None:
    storage.init_schema()
    storage.init_schema()


def test_empty_dsn_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty DSN"):
        Storage("")


def test_list_runs_limit_out_of_range_rejected(storage: Storage) -> None:
    with pytest.raises(ValueError, match="limit must be"):
        storage.list_runs(limit=0)
    with pytest.raises(ValueError, match="limit must be"):
        storage.list_runs(limit=501)

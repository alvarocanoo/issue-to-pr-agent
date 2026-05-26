"""Unit tests for the FastAPI server with a fake Storage. No DB needed."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from issue_to_pr.api import build_app
from issue_to_pr.storage.db import StoredRun


def _stored_run(*, run_id: int = 1, task_id: str = "t") -> StoredRun:
    return StoredRun(
        id=run_id,
        task_id=task_id,
        mode="orchestrator",
        success=True,
        reflexion_iterations=1,
        executor_iterations=3,
        verify_exit_code=0,
        prompt_tokens=100,
        completion_tokens=10,
        elapsed_seconds=1.5,
        started_at="2026-05-26T10:00:00+00:00",
        finished_at="2026-05-26T10:00:02+00:00",
        plan={"steps": ["s"]},
        verdict={"approved": True, "reasoning": "ok"},
    )


def test_healthz_does_not_touch_storage() -> None:
    storage = MagicMock()
    client = TestClient(build_app(storage=storage))
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    storage.list_runs.assert_not_called()


def test_list_runs_returns_serialised_items() -> None:
    storage = MagicMock()
    storage.list_runs.return_value = [_stored_run(run_id=1), _stored_run(run_id=2, task_id="other")]
    client = TestClient(build_app(storage=storage))
    r = client.get("/runs?limit=10&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 2
    assert data["limit"] == 10
    assert data["offset"] == 0
    ids = [item["id"] for item in data["items"]]
    assert ids == [1, 2]
    storage.list_runs.assert_called_once_with(limit=10, offset=0)


def test_list_runs_validates_query_params() -> None:
    storage = MagicMock()
    client = TestClient(build_app(storage=storage))
    assert client.get("/runs?limit=0").status_code == 422
    assert client.get("/runs?limit=501").status_code == 422
    assert client.get("/runs?offset=-1").status_code == 422


def test_get_run_returns_one() -> None:
    storage = MagicMock()
    storage.get_run.return_value = _stored_run(run_id=42, task_id="foo")
    client = TestClient(build_app(storage=storage))
    r = client.get("/runs/42")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 42
    assert body["task_id"] == "foo"
    assert body["plan"] == {"steps": ["s"]}
    storage.get_run.assert_called_once_with(42)


def test_get_run_404() -> None:
    storage = MagicMock()
    storage.get_run.return_value = None
    client = TestClient(build_app(storage=storage))
    r = client.get("/runs/9999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]

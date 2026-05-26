"""Read-only HTTP surface over the `runs` table.

Endpoints:
- GET /healthz                 -> {"status": "ok"} (no DB hit)
- GET /runs?limit=&offset=     -> list recent runs (newest first)
- GET /runs/{id}               -> one run with plan + verdict

Storage is injected so tests can wire an in-memory or fake Storage without a DB.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from issue_to_pr.settings import get_settings
from issue_to_pr.storage import Storage


def build_app(storage: Storage | None = None) -> FastAPI:
    """Build a FastAPI app. `storage` defaults to a Storage built from settings."""
    if storage is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is empty; set it in .env or environment")
        storage = Storage(settings.database_url)

    app = FastAPI(
        title="issue-to-pr-agent",
        version="0.1.0",
        description=("Read-only API over agent runs. Writes happen inside the CLI / eval runner."),
    )

    # Next.js dashboard at localhost:3000 (dev) needs cross-origin reads.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/stats")
    def stats() -> dict[str, Any]:
        runs = storage.list_runs(limit=500)
        total = len(runs)
        solved = sum(1 for r in runs if r.success)
        prompt_t = sum(r.prompt_tokens for r in runs)
        completion_t = sum(r.completion_tokens for r in runs)
        elapsed = sum(r.elapsed_seconds for r in runs)
        modes: dict[str, int] = {"executor": 0, "orchestrator": 0}
        for r in runs:
            modes[r.mode] = modes.get(r.mode, 0) + 1
        return {
            "total_runs": total,
            "solved": solved,
            "resolved_at_1": (solved / total) if total else 0.0,
            "total_prompt_tokens": prompt_t,
            "total_completion_tokens": completion_t,
            "total_elapsed_seconds": elapsed,
            "by_mode": modes,
        }

    @app.get("/runs")
    def list_runs(
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        runs = storage.list_runs(limit=limit, offset=offset)
        return {
            "count": len(runs),
            "limit": limit,
            "offset": offset,
            "items": [asdict(r) for r in runs],
        }

    @app.get("/runs/{run_id}")
    def get_run(run_id: int) -> dict[str, Any]:
        run = storage.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        return asdict(run)

    return app


# Allow `uv run uvicorn issue_to_pr.api.server:app` for ad-hoc local serving.
app = build_app() if __name__ != "__main__" else None

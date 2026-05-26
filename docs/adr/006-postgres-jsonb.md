# ADR-006: Postgres + JSONB for run persistence

**Status**: accepted (schema + sync psycopg3 wrapper implemented; FastAPI surface read-only)
**Date**: 2026-05-26
**Deciders**: Álvaro

## Context

Once the agent has more than a handful of runs, the `eval-report.json` file pattern starts
to hurt:
- No history. Each new run overwrites or sits next to the previous one with no link.
- No query by mode (executor vs orchestrator), no time series, no aggregates.
- The Next.js dashboard (Week 3.2) needs a backend that can stream runs incrementally as
  they finish, not parse a JSON blob.

What we need is a persistent store with:
1. **Append-only runs**: one row per `Orchestrator.run()` or `Executor.run()`.
2. **Aggregated reports**: one row per `evals/runner` invocation.
3. **Nested artefacts** (plan, verdict, history) without schema churn every time we add a
   field. The agent's data shape evolves faster than a SQL schema can.
4. **Indexes** for the dashboard's hot queries: most-recent-first, by task id, by mode.

Constraints:
- Solo dev environment is Windows without admin (see [ADR-003](003-pluggable-sandbox.md)).
  The user has `pgsql-portable` (Postgres 16.14 binary) but cannot run Docker for a
  container'd Postgres.
- CI on Ubuntu runners *can* run Postgres, but for Week 1–3 tests we keep CI on unit tests
  only (the Postgres integration tests skip when no DB is reachable).
- Eventually the API will go async (FastAPI); the persistence layer must not paint us into a
  sync corner.

## Alternatives considered

1. **SQLite + JSONB-like text columns**. Pros: zero ops, file in repo. Cons: poor concurrency,
   poor JSONB support (functional JSON1, no GIN indexes), Postgres-compatibility friction
   when we move to a managed instance later.
2. **MongoDB / DuckDB / a document DB**. Pros: native nested docs. Cons: another binary to
   ship in dev, no `pgsql-portable` equivalent, the rest of the ecosystem is SQL.
3. **Pure flat SQL columns** (no JSONB). Pros: typed schemas, regular `JOIN`s. Cons: every
   new field in `Plan` or `VerifierVerdict` becomes a migration; the actual queries we run
   don't `JOIN` deeply, they pull whole runs by id.
4. **Postgres with `JSONB` for nested artefacts + flat columns for indexed/aggregable ones**.
   Pros: one engine for everything, the right hybrid: flat columns for query-time
   predicates (mode, success, started_at), JSONB for the structured payloads we evolve.

## Decision

Use Postgres 16 (via `pgsql-portable` locally; managed Postgres later) with two tables:

```sql
runs (
    id, task_id, started_at, finished_at,
    mode CHECK IN ('executor', 'orchestrator'),
    success, reflexion_iterations, executor_iterations, verify_exit_code,
    prompt_tokens, completion_tokens, elapsed_seconds,
    plan JSONB, verdict JSONB, history JSONB
)

eval_reports (
    id, set_name, mode, started_at,
    total, solved, resolved_at_1,
    total_prompt_tokens, total_completion_tokens, total_elapsed_seconds,
    raw JSONB
)
```

Indexes on `runs.task_id`, `runs.started_at DESC`, `runs(mode, success)`,
`eval_reports.started_at DESC`, `eval_reports(set_name, mode)` — these match the queries the
API and the Next.js dashboard will issue.

Driver: **psycopg3 sync** (`psycopg[binary]>=3.2`). One Storage instance per process,
autocommit connections opened lazily. We deliberately avoid asyncpg right now: the CLI runner
is sync, FastAPI can wrap psycopg in `run_in_executor` if we ever profile and find it
matters. Moving to asyncpg later is a Storage-class rewrite, not a system rewrite.

## Why JSONB and not just text JSON

- Operators (`->>`, `@>`, `jsonb_path_*`) let the dashboard ask *"give me runs where
  `verdict->>'approved' = false`"* without parsing every row in Python.
- GIN indexes on JSONB columns are an easy optimisation later if a key becomes a hot predicate.
- Postgres validates the JSON at insert time — typo'd payloads fail loudly, not silently.

## Consequences

**Easier**:
- New fields on `Plan` / `VerifierVerdict` cost zero migration: just write the dict, the
  schema accepts it.
- Local dev uses pgsql-portable, no Docker required. Idempotent `init_schema()` on every
  process means "just run it" works.
- API surface (read-only `/runs`, `/runs/{id}`) maps 1:1 to `Storage.list_runs` /
  `Storage.get_run` and serialises a dataclass.

**Harder**:
- Two competing sources of truth for "what's in a run": the dataclasses in `executor/types.py`
  and the JSON shape persisted to Postgres. We pay this with explicit `to_dict()` / `asdict`
  at the boundary; if it drifts, tests catch it.
- The integration tests for `Storage` need a running Postgres. We skip them when no DB is
  reachable rather than fail; CI consequently does not exercise them today (Week 3.2 will add
  a `services: postgres` block to the eval workflow).
- Choosing psycopg sync means FastAPI request handlers are sync. For our load (a handful of
  dashboard requests per minute), this is fine; if it ever isn't, asyncpg is one Storage
  rewrite away.

**Accepted**:
- We don't shard, we don't replicate, we don't tune. One Postgres instance is the design.

## Verification

- `Storage.init_schema()` is idempotent — confirmed by the
  `test_init_schema_is_idempotent` test.
- Round-trip `insert_run` → `get_run` preserves JSONB payloads
  (`test_insert_and_get_run_roundtrip`).
- `list_runs` orders newest-first and respects limit/offset
  (`test_list_runs_newest_first`, `test_list_runs_respects_limit_and_offset`).
- FastAPI surface returns the right shape: `test_list_runs_returns_serialised_items`,
  `test_get_run_returns_one`, `test_get_run_404`. These use a `MagicMock(Storage)` so they
  cost no DB.
- Local: `psql -U itp -h localhost -d itp -c "TABLE runs"` shows whatever the runner just
  persisted.

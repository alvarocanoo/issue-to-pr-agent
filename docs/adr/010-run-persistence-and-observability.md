# ADR-010: Run persistence + read-only dashboard observability

**Status**: accepted (Postgres persistence + FastAPI surface + Next.js dashboard implemented;
SSE live streaming planned)
**Date**: 2026-05-26
**Deciders**: Álvaro

## Context

For the first half of the project the only output of a run was a JSON file
(`eval-report.json`) and the rich-text table the CLI printed. That was enough to debug
during Week 1, but not enough to:

- **Show progress over time** ("did this fix regress vs last week?")
- **Compare modes** (executor-only vs orchestrator with Reflexion)
- **Inspect a failed run** (timeline of attempts, planner output, verifier reasoning)
- **Demo the project visually** to a reviewer who is not going to run `pytest` on their box

The portfolio is the product. A dashboard that renders a run with its plan, every Reflexion
iteration, and the final verdict is what separates "I have a CLI tool" from "I have a system".

## Alternatives considered

1. **Stay JSON-file only.** Cheapest. Loses time-series, comparisons, dashboards.
2. **Use Langfuse for the whole thing.** Pros: ready-made traces UI. Cons: Langfuse is a
   *trace* viewer per LLM call, not a run-history dashboard. Also self-hosting needs Docker
   (see [ADR-003](003-pluggable-sandbox.md) — no admin in dev). We will still wire Langfuse
   for the per-tool-call view (planned Week 3.3), but it is not a substitute for the
   run-level dashboard.
3. **Postgres-backed runs + custom Next.js dashboard.** Reuses
   [ADR-006](006-postgres-jsonb.md) (Postgres + JSONB) for storage. Dashboard is one
   small Next.js app that reads a read-only FastAPI surface.
4. **Realtime SSE streaming of in-progress runs.** Extension of (3): the dashboard
   sees each tool call land as the agent works. Powerful but adds complexity (server-side
   event source, orchestrator callbacks, client EventSource handling). Planned, not in this
   ADR.

## Decision

Adopt (3) now and reserve (4) for an explicit follow-up.

**Persistence shape** (see [`storage/schema.sql`](../../src/issue_to_pr/storage/schema.sql)):
- One row in `runs` per `Executor.run()` or `Orchestrator.run()`.
- Per-iteration detail of the Reflexion loop persisted in `runs.history` as a JSONB array.
  Each entry is `{iteration, execution: {executor_iterations, tool_calls_count, tokens,
  elapsed, verify_exit_code}, verdict: {approved, reasoning, feedback_for_executor}}`.
  We deliberately don't store the raw messages from the LLM: that's Langfuse's job (Week 3.3).
- Persistence is **row-by-row** from inside the runner (`evals/runner.py::_run_one_*`)
  before each call returns. A rate-limit crash mid-set keeps the rows that already
  completed — verified during the first real A/B attempt where the runner crashed after
  one orchestrator run had committed.

**API surface** (see [`api/server.py`](../../src/issue_to_pr/api/server.py)):
- `GET /healthz` — liveness, no DB hit.
- `GET /stats` — aggregate counts (resolved@1, by-mode, total tokens, total time).
- `GET /runs?limit=&offset=` — most-recent-first.
- `GET /runs/{id}` — full row including the history array.
- CORS allow list is `localhost:3000` for dev only; production is a TODO when we deploy
  (Week 4).

**Dashboard** (see [`web/`](../../web/)):
- Next.js 16 app router + React 19 + Tailwind 4, all TypeScript.
- Home page: stats bar (resolved@1 percentage, count per mode, cumulative tokens, time) +
  recent-runs table with success badges and link to detail.
- Detail page: per-run plan from the planner, **vertical Reflexion timeline** with one
  card per iteration (rejected vs approved colour, per-iteration metrics, verifier
  reasoning, feedback box for retries), final verdict, raw JSON for diffing.

## Consequences

**Easier**:
- A reviewer scans the README, sees the dashboard screenshot, and immediately understands
  what the agent does and what came out of it.
- The Reflexion architecture (ADR-002) becomes visible: rejected attempts + feedback ->
  approved attempts. Without the timeline UI, Reflexion is a feature you have to take on
  faith from a README paragraph.
- The eval gate (resolved@1 ≥ 0.70) is no longer just a CI exit code — it's a number on
  the dashboard that updates every run.

**Harder**:
- One more component (Next.js) to keep building. Mitigated by keeping the dashboard
  read-only: write paths live in the CLI runner only.
- Two repos of truth for the run shape (Python dataclass + TypeScript type). Mitigated by
  the API serialiser being thin (`dataclasses.asdict`) so any field added to the Python
  dataclass shows up in the API automatically; only the TS type needs a copy.
- The dashboard is not yet authenticated. It is a localhost-only demo for now; when we
  deploy (Week 4), we add an API key gate. ADR-011 will cover that.

**Accepted**:
- We ship a dashboard before we ship a deploy. The intent is to screenshot it for the
  README; until Week 4, `localhost:3000` is the only place it runs.

## Verification

- 117 unit tests green (storage + api + orchestrator + planner + verifier + executor +
  tools + LLM client + sandbox). The api tests inject a `MagicMock(Storage)` so they
  cost nothing; storage tests hit a real Postgres but `skipif` cleanly when no DB is
  reachable, keeping CI green.
- Captured against the real stack with Edge headless:
  [docs/images/dashboard-home.png](../images/dashboard-home.png) and
  [docs/images/dashboard-detail.png](../images/dashboard-detail.png).
- The first real Reflexion run that hits production (when TPD allows the orchestrator to
  finish without rate-limiting) will persist its history and surface in the timeline —
  no extra work needed; the runner already passes it.

## Next steps (out of scope here)

- ADR-011: deploy story for the dashboard + API (Fly.io / Railway), with API key gate.
- Langfuse integration (Week 3.3): per-tool-call traces visible from the dashboard via a
  deep link, so the dashboard owns "what happened across runs" and Langfuse owns
  "what happened inside one run".
- SSE live mode (Week 3.4): dashboard sees in-progress runs without a refresh.

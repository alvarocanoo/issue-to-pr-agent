# ADR-011: Deploy story — GitHub Pages now, hosted backend later

**Status**: accepted (dashboard live on GitHub Pages; hosted backend deferred)
**Date**: 2026-05-26
**Deciders**: Álvaro

## Context

The dashboard exists as a Next.js app under `web/`, the API as a FastAPI server under
`src/issue_to_pr/api/`. A reviewer clicking from GitHub on a Friday night should see the
dashboard rendering real runs without having to clone, install Python, install Postgres
and run two servers.

Constraints:
- Solo dev, no infra budget.
- Groq free-tier API key is mine; if I expose an HTTP endpoint that runs the agent on
  demand, a single shared link can drain my daily token quota. Authentication is overkill
  for a portfolio demo.
- The dashboard data shape is stable enough that a build-time snapshot is honest: the
  reviewer is looking at the *measured A/B*, not at a live system.

## Alternatives considered

1. **GitHub Pages, static export, embedded snapshot.** Pros: free, runs entirely off
   `*.github.io`, no Node/Python in production, no API keys live. Cons: the demo is a
   read-only snapshot, regenerated on every push to `main`.
2. **Vercel + Postgres hosted (Neon / Supabase).** Pros: SSR, fresh data on every render
   if connected to a hosted DB. Cons: needs a hosted Postgres + env vars + a Vercel
   account. Still doesn't enable "run the agent" without an auth gate.
3. **Vercel + Postgres + auth-gated agent execution.** Pros: closest to a real product.
   Cons: significantly more surface area (rate limiting, abuse handling, OAuth, billing
   for compromise), all of which would dominate the remaining schedule.
4. **Fly.io / Render for FastAPI + Vercel for Next.js.** Pros: closer to a "real" split.
   Cons: two deploys to maintain, two free-tier limits to watch.

## Decision

**Option 1 today, option 2 deferred (Week 4 if scope allows), option 3 explicitly
out of scope** for this project.

Why option 1:
- `next.config.ts` has `output: "export"` gated by `NEXT_PUBLIC_USE_STATIC=true`.
- `lib/api.ts` reads from `data/runs.json` and `data/stats.json` (a snapshot exported from
  Postgres after each A/B) when the same flag is set.
- The home page and every `/runs/[id]/` are pre-rendered via `generateStaticParams()` over
  the embedded snapshot.
- `.github/workflows/pages.yml` runs `npm run build` with that env var, uploads
  `web/out/` as a Pages artifact, and `actions/deploy-pages` publishes it. Pages was
  enabled with `gh api repos/.../pages -f build_type=workflow`.
- Result: https://alvarocanoo.github.io/issue-to-pr-agent/ — public, free, no secrets
  required in the deployed build.

## Consequences

**Easier**:
- A reviewer clicks the badge in the README and sees the live A/B numbers with the
  Reflexion timeline, with zero clone-and-run friction.
- No API keys in the deploy. The build process needs none.
- No abuse vector — the static export is read-only.

**Harder**:
- The dashboard data is only as fresh as the last build. After a real A/B run, the
  developer must regenerate `web/data/*.json` from Postgres and push. Not automated yet.
- "Run the agent on this issue" is not a feature of the public site. Reviewers must
  clone to do that.

**Accepted**:
- The demo is a snapshot, not a live system. We trade liveness for safety + zero ops.

## Operational notes for the developer

```powershell
# 1. Run the A/B locally, persisting to Postgres
uv run python -m evals.runner --set trivial --persist                  # orchestrator
uv run python -m evals.runner --set trivial --executor-only --persist  # baseline

# 2. Regenerate the static snapshot from the eval-*.json (see scripts/seed_runs.py for
#    the inverse: seed Postgres from a snapshot).
#    The snapshot lives at web/data/runs.json + web/data/stats.json.

# 3. Commit web/data/ + push -> the Pages workflow rebuilds and republishes automatically.
```

## What option 2 looks like, if we go there in Week 4

- Neon free tier (Postgres serverless) holds the `runs` table. Schema is the same SQL
  the local `pgsql-portable` uses.
- `Storage(dsn)` reads `DATABASE_URL` from `.env` (already supported).
- Vercel deploys the same Next.js app with `NEXT_PUBLIC_USE_STATIC=false` and
  `NEXT_PUBLIC_API_BASE` pointing at a hosted FastAPI (Render / Fly.io / Vercel function).
- The build no longer needs the embedded JSON snapshot — drop the JSON, keep the code.
- Cost: ~$0 in free tiers; the trade-off is needing to keep two free-tier services
  alive instead of zero.

The migration is "one Storage DSN swap + one CORS allowlist update + drop two static
files". Not free, not heavy either.

## Verification

- Pages workflow: `gh run watch <run_id>` reports `success` for the deploy job.
- `curl https://alvarocanoo.github.io/issue-to-pr-agent/` → 200, HTML containing
  `issue-to-pr-agent` and the stats bar.
- `curl https://alvarocanoo.github.io/issue-to-pr-agent/runs/22/` → 200, HTML containing
  `Reflexion timeline` (orchestrator run with verdict iterations visible).
- `curl https://alvarocanoo.github.io/issue-to-pr-agent/runs/11/` → 200, HTML for a
  baseline (executor-only) run, no timeline section.
- The Pages badge in the README turns green after each successful deploy.

The kill-switch for option 1 is `gh api -X DELETE repos/alvarocanoo/issue-to-pr-agent/pages`,
which unpublishes the demo without touching the codebase. We expect not to need it.

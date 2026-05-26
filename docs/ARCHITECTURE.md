# Architecture

> One-page overview. Decisions and trade-offs live in [adr/](adr/), indexed by [DECISIONS.md](DECISIONS.md).

## High-level flow

```
User runs: issue-to-pr run --issue <url>
                │
                ▼
       ┌────────────────────┐
       │  github/fetch_issue│  Reads issue title + body + linked files
       └─────────┬──────────┘
                 │
                 ▼
       ┌────────────────────┐
       │      Planner       │  Sonnet 4.6 → structured plan (JSON)
       └─────────┬──────────┘
                 │
                 ▼
       ┌────────────────────┐
       │      Executor      │  Haiku 4.5 driving Claude Agent SDK
       │  (Read/Edit/Bash/  │  PreToolUse hook validates each Bash
       │   Grep/Glob)       │  PostToolUse hook logs to Langfuse
       └─────────┬──────────┘
                 │ runs inside
                 ▼
       ┌────────────────────┐
       │  Docker sandbox    │  python:3.12-slim, --network none,
       │  per-task          │  RW mount of cloned repo, 20m watchdog
       └─────────┬──────────┘
                 │
                 ▼
       ┌────────────────────┐
       │     Verifier       │  Sonnet 4.6 LLM-as-judge on diff + tests
       │  (LLM-as-judge)    │  Decides: open PR or reject + retry
       └─────────┬──────────┘
                 │ if approved
                 ▼
       ┌────────────────────┐
       │  github/open_pr    │  gh CLI: branch, commit, push, PR
       └────────────────────┘

Side-channel (every step):
  - Langfuse: span per tool call, tokens, cost, latency
  - Postgres: run metadata + JSONB raw trace
  - FastAPI SSE: live event stream to Next.js dashboard
```

## Why three models

Cost analysis lives in [adr/004-multi-model-routing.md](adr/004-multi-model-routing.md). Summary: planner and verifier are small fractions of total tokens (~10% each) and benefit from Sonnet's reasoning. Executor burns 80% of tokens in tool loops and works fine on Haiku for routine Read/Edit/Bash.

## Why Docker `--network none`

See [adr/003-docker-sandbox.md](adr/003-docker-sandbox.md). LLM-generated shell commands are untrusted code. Network isolation + RW mount of only the cloned repo workdir means: worst case the agent corrupts its own scratch directory.

## What is NOT in this project

- No retrieval / RAG (that's `claude-docs-rag`).
- No fine-tuning (ADR-008).
- No support for non-Python repos in v1 (Python only — the test framework assumption is `pytest`).

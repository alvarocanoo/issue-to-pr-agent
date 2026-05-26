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
       │      Planner       │  openai/gpt-oss-120b → structured plan (JSON)
       └─────────┬──────────┘
                 │
                 ▼
       ┌────────────────────┐
       │      Executor      │  openai/gpt-oss-20b driving hand-rolled tool loop
       │  (Read/Edit/Bash/  │  PreToolUse validator: Bash whitelist
       │   Grep/Glob)       │  PostToolUse logger: spans to Langfuse
       └─────────┬──────────┘
                 │ runs inside
                 ▼
       ┌────────────────────┐
       │  SandboxRunner     │  LocalSubprocessRunner (default, no admin):
       │  (pluggable)       │    tempdir cwd, clean env, timeout, fs snapshot diff
       │                    │  ContainerRunner (opt-in, Podman per-task):
       │                    │    --network none, RW mount, 20m watchdog
       └─────────┬──────────┘
                 │
                 ▼
       ┌────────────────────┐
       │     Verifier       │  openai/gpt-oss-120b LLM-as-judge on diff + tests
       │  (LLM-as-judge)    │  Decides: open PR or reject + retry
       └─────────┬──────────┘
                 │ if approved
                 ▼
       ┌────────────────────┐
       │  github/open_pr    │  gh CLI: branch, commit, push, PR
       └────────────────────┘

Side-channel (every step):
  - LLMClient (src/issue_to_pr/llm/client.py): single Groq wrapper, captures tokens + cost
  - Langfuse: span per tool call, latency
  - Postgres: run metadata + JSONB raw trace
  - FastAPI SSE: live event stream to Next.js dashboard
```

## Why three models

Cost analysis lives in [adr/004-multi-model-routing.md](adr/004-multi-model-routing.md).
Summary: Groq free tier costs $0/run regardless of model, so the routing optimisation is **speed
and capability**, not cost. `openai/gpt-oss-20b` at 1000 tps wins the executor loop (lots of
short tool calls); `openai/gpt-oss-120b` at 500 tps wins planner and verifier where reasoning
quality matters more than throughput.

## Why hand-rolled tool loop instead of an agent framework

See [adr/001-no-agent-framework.md](adr/001-no-agent-framework.md). Frameworks (LangChain,
LangGraph, Claude Agent SDK) hide the tool loop behind opinionated abstractions. Building the
loop from scratch keeps every decision visible and defendible in code review, and avoids
provider lock-in (the LLM client is a single file).

## Why a pluggable sandbox

See [adr/003-sandbox.md](adr/003-sandbox.md). LLM-generated shell commands are untrusted code.
In Windows dev without admin we cannot run Docker/Podman, so `LocalSubprocessRunner` enforces
isolation through tempdir CWD + cleared env + Bash whitelist + filesystem-snapshot diff. The
same `SandboxRunner` interface is implemented by `ContainerRunner` (Podman per-task,
`--network none`) — swappable behind a config flag once Podman is installed.

## What is NOT in this project

- No retrieval / RAG (that's `claude-docs-rag`).
- No fine-tuning (ADR-008).
- No support for non-Python repos in v1 (Python only — the test framework assumption is `pytest`).

# issue-to-pr-agent

[![CI](https://github.com/alvarocanoo/issue-to-pr-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/alvarocanoo/issue-to-pr-agent/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![Type-checked: mypy strict](https://img.shields.io/badge/types-mypy%20strict-1f5082.svg)](http://mypy-lang.org/)

> Autonomous coding agent that takes a GitHub issue URL and opens a pull request with a working fix, tests passing, full decision traces. **Hand-rolled tool loop** over **Groq Cloud** with open-source models (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`) — $0 per run on Groq's free tier.

**Status**: Week 1 — LLM client + sandbox done, executor + first end-to-end issue resolution in progress.

## What this is

A production-grade coding agent built **without an agent framework**: the tool loop, hooks, sandboxing and self-correction are all implemented from scratch on top of the Groq Python SDK. Given an issue in a Python repo, the agent:

1. **Plans** the fix (`openai/gpt-oss-120b` via Groq).
2. **Executes** the work inside a per-task sandbox (temp dir + command whitelist + timeout; container-based mode behind the same interface, see [ADR-003](docs/adr/003-sandbox.md)) — `openai/gpt-oss-20b` driving Read/Edit/Bash/Grep tools.
3. **Verifies** the diff with an LLM-as-judge (`openai/gpt-oss-120b`) before opening a PR.
4. **Traces** every tool call, token, and latency to Langfuse.
5. **Reports** metrics: `resolved@1`, latency.

## Why this project exists

Most "AI coding" demos either wrap a framework (LangChain, LangGraph, Claude Agent SDK) or are toy chatbots. This is the opposite: every layer of the agent loop is hand-built, defendible line by line in a code review, and evaluated against SWE-bench Lite. Vendor-agnostic by design — the LLM client is a thin wrapper, so switching providers is a one-file change.

Companion project: [claude-docs-rag](https://github.com/alvarocanoo/claude-docs-rag) — production RAG over the Anthropic Claude API docs.

## Target metrics (declared before coding — see ADR-007)

| Metric | Target | Why |
|---|---|---|
| `resolved@1` on my 10 trivial issues | ≥ 70% | Baseline sanity — if this fails, the agent is broken |
| `resolved@1` on SWE-bench Lite (50-issue subset) | TBD after Week 4 | Re-measured against `openai/gpt-oss-120b`; published number replaces this row |
| Mean wall-clock per issue | ≤ 15 min | Otherwise it does not feel like automation |
| Cost per issue | $0 (free tier) | Groq free tier; documented rate-limit fallback in ADR-004 |
| Sandbox escapes | 0 in 100 runs | Validated via filesystem-snapshot diff + Bash whitelist + timeout |
| Tests reproducible | 100% (eval suite passes 3× in CI without flakes) | Otherwise the "regression gate" is theatre |

Numbers will replace targets in this README as soon as Week 2 evals run.

## Architecture (1 paragraph)

Three open-source models on Groq in a Planner → Executor → Verifier loop. The LLM client is a thin Groq SDK wrapper (`src/issue_to_pr/llm/client.py`) — all cost and trace hooks live there. Executor calls a hand-built tool loop with `PreToolUse` validation that whitelists Bash, restricts CWD and clears env. The sandbox interface (`src/issue_to_pr/sandbox/runner.py`) has two implementations: `LocalSubprocessRunner` (default, no admin needed — tempdir + snapshot diff + timeout) and `ContainerRunner` (Podman/Docker per-task — for production). Postgres stores run metadata + JSONB traces; Langfuse captures the full agent timeline; Next.js dashboard exposes both.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and the ADR index in [docs/DECISIONS.md](docs/DECISIONS.md).

## Stack

- **Agent core**: `groq` Python SDK, models `openai/gpt-oss-120b` (planner, verifier) and `openai/gpt-oss-20b` (executor).
- **Sandbox**: pluggable interface — `LocalSubprocessRunner` (default) or `ContainerRunner` (Podman).
- **Storage**: Postgres 16 — JSONB traces. Local dev uses `pgsql-portable` (no Docker required), see [docs/POSTGRES.md](docs/POSTGRES.md).
- **Observability**: Langfuse self-hosted.
- **API**: FastAPI + SSE.
- **Frontend**: Next.js 16 (planned Week 3).
- **Eval**: SWE-bench Lite subset + custom trivial set.
- **Tooling**: uv, ruff, mypy strict, pytest.

## Quickstart (local dev)

> Requires: Windows 11 + PowerShell 5.1, Python 3.12, [uv](https://docs.astral.sh/uv/) ≥ 0.11, [gh CLI](https://cli.github.com/) authenticated, a free [Groq API key](https://console.groq.com/keys).

```powershell
git clone https://github.com/alvarocanoo/issue-to-pr-agent.git
cd issue-to-pr-agent
Copy-Item .env.example .env  # then paste your GROQ_API_KEY
uv sync
uv run pytest
```

Once Week 1 is done, the entrypoint will be:

```powershell
uv run issue-to-pr run --issue evals/trivial_issues/001-typo.yaml
```

## Roadmap

- [x] Week 1.1: walking skeleton + CI green (uv project, settings, CLI, GitHub Actions)
- [x] Week 1.2: Groq `LLMClient` wrapper (captures content + reasoning + tool_calls + tokens)
- [x] Week 1.3: `LocalSubprocessRunner` sandbox (whitelist + blacklist + snapshot diff + timeout, no admin required)
- [ ] Week 1.4: Executor with hand-rolled tool loop + 1 trivial issue resolved end-to-end
- [ ] Week 2: planner + verifier + 10 trivial issues + CI eval gate
- [ ] Week 3: Langfuse traces + Postgres persistence + FastAPI + Next.js dashboard
- [ ] Week 4: SWE-bench Lite subset eval + sandbox hardening (Podman runner) + deploy
- [ ] Weeks 5-6: ablation studies + blog posts + README final with measured numbers

## License

MIT — see [LICENSE](LICENSE).

## Author

Álvaro Cano · [@alvarocanoo](https://github.com/alvarocanoo)

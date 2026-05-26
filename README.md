# issue-to-pr-agent

> Autonomous agent that takes a GitHub issue URL and opens a pull request with a working fix, tests passing, full decision traces — all inside an isolated Docker sandbox.

**Status**: Week 1 — walking skeleton in progress. Not usable yet.

## What this is

A production-grade coding agent built on the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview). Given an issue in a Python repo, it:

1. **Plans** the fix (Sonnet 4.6).
2. **Executes** the work inside a Docker container with `--network none` (Haiku 4.5 driving Read/Edit/Bash/Grep).
3. **Verifies** the diff with an LLM-as-judge (Sonnet 4.6) before opening a PR.
4. **Traces** every tool call, token, and cost to Langfuse.
5. **Reports** metrics: `resolved@1`, cost, latency.

## Why this project exists

Most "AI coding" demos are toy chatbots. This is the opposite: a defensible system with sandboxing, evals, regression gates in CI, and honest metrics in the README — built to be auditable in a technical interview, line by line.

Companion project: [claude-docs-rag](https://github.com/alvarocanoo/claude-docs-rag) — production RAG over the Anthropic Claude API docs.

## Target metrics (declared before coding, see ADR-007)

| Metric | Target | Why |
|---|---|---|
| `resolved@1` on my 10 trivial issues | ≥ 70% | Baseline sanity — if this fails, the agent is broken |
| `resolved@1` on SWE-bench Lite (50-issue subset) | ≥ 25% | SOTA is Claude Opus 4.6 at 62.7%; 25% is defendible for a solo project |
| Mean cost per issue | ≤ $0.40 | With planner/executor/judge routing across Sonnet 4.6 + Haiku 4.5 |
| Mean wall-clock per issue | ≤ 15 min | Otherwise it does not feel like automation |
| Sandbox escapes | 0 in 100 runs | Validated via `docker inspect` + PreToolUse Bash whitelist |

Real measured numbers will replace these targets in this README as soon as Week 2 evals run.

## Architecture (1 paragraph)

Three Anthropic models in a Planner → Executor → Verifier loop. Executor uses the Claude Agent SDK with restricted `allowed_tools` and a `PreToolUse` hook that whitelists `Bash` calls. All file edits and shell commands run inside a per-task Docker container (`python:3.12-slim`, `--network none`, 20-minute watchdog, memory cap). Postgres stores run metadata and JSONB traces; Langfuse captures the full agent timeline; Next.js dashboard exposes both.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and the ADR index in [docs/DECISIONS.md](docs/DECISIONS.md).

## Stack

- **Agent core**: `claude-agent-sdk` (Python), Anthropic models (`claude-sonnet-4-6`, `claude-haiku-4-5-20251001`)
- **Sandbox**: Docker per-task (`--network none`, RW mount of cloned repo)
- **Storage**: Postgres 16 (JSONB traces)
- **Observability**: Langfuse self-hosted
- **API**: FastAPI + SSE
- **Frontend**: Next.js 16 (planned Week 3)
- **Eval**: SWE-bench Lite subset + custom trivial set
- **Tooling**: uv (Python), ruff, mypy strict, pytest

## Quickstart (local dev)

> Requires: Windows 11 + PowerShell 5.1, Docker Desktop, Python 3.12, [uv](https://docs.astral.sh/uv/) ≥ 0.11, [gh CLI](https://cli.github.com/) authenticated, an `ANTHROPIC_API_KEY`.

```powershell
git clone https://github.com/alvarocanoo/issue-to-pr-agent.git
cd issue-to-pr-agent
Copy-Item .env.example .env  # then edit ANTHROPIC_API_KEY
uv sync
docker compose up -d
uv run pytest
```

Once Week 1 is done, the entrypoint will be:

```powershell
uv run issue-to-pr run --issue evals/trivial_issues/001-typo.yaml
```

## Roadmap

- [x] Week 1: walking skeleton (sandbox, executor, 1 trivial issue resolved)
- [ ] Week 2: planner + verifier + 10 trivial issues + CI eval gate
- [ ] Week 3: Langfuse traces + Postgres persistence + FastAPI + Next.js dashboard
- [ ] Week 4: SWE-bench Lite subset eval + sandbox hardening + deploy
- [ ] Weeks 5-6: ablation studies + blog posts + README final with measured numbers

## License

MIT — see [LICENSE](LICENSE).

## Author

Álvaro Cano · [@alvarocanoo](https://github.com/alvarocanoo)

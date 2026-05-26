# CLAUDE.md — issue-to-pr-agent

> Instructions for Claude Code when working in this repo. Read before doing anything.

## What this repo is

Production-grade autonomous coding agent. Given a GitHub issue URL in a Python repo, opens a PR with the fix. Built on Claude Agent SDK (Python). Components: Planner → Executor → Verifier, each defendible in a technical interview against the paper that justifies it.

Companion project: `../claude-docs-rag` (RAG over Anthropic API docs). Do NOT touch it from here.

## Stack and conventions

- **Python 3.12**, managed with `uv`. Use `uv add <pkg>` to add deps (never `pip install`).
- **Type hints required**. `mypy --strict` runs in CI.
- **Ruff** for lint and format. Run `uv run ruff check --fix` and `uv run ruff format` before commit.
- **Tests**: `uv run pytest`. Unit tests in `tests/unit/`, integration in `tests/integration/`.
- **Secrets**: `.env` only (gitignored). Use `pydantic-settings` to load. Never hardcode keys.
- **Async I/O** where it touches DB or network (FastAPI, asyncpg).
- **All Anthropic calls** go through `claude_agent_sdk.query()` — never direct `anthropic.Anthropic()`. The SDK gives us tool loop, hooks and sessions for free.

## Architecture invariants (do NOT violate without a new ADR)

1. **Every Bash command from the agent runs inside Docker `--network none`**. The `PreToolUse` hook in `executor/hooks.py` validates this. If you bypass the hook, write an ADR first.
2. **Planner is Sonnet, Executor is Haiku, Verifier is Sonnet** (model IDs in `settings.py`). Swap → ADR.
3. **No retrieval / vector DB** in this project. That's `claude-docs-rag`'s job.
4. **No fine-tuning**. Prompt + routing is the contract — see ADR-008.
5. **Every component has tests**. Coverage is not the metric; "can I delete this and CI tells me" is.

## Commands you'll use

```powershell
uv sync                                          # install/update deps from lock
uv add <pkg>                                     # add a dep
uv run pytest                                    # all tests
uv run pytest -m "not evals"                     # skip eval suite (faster)
uv run pytest tests/unit/test_sandbox.py -v      # single file
uv run ruff check --fix; uv run ruff format      # lint + format
uv run mypy src/                                 # type check strict
uv run issue-to-pr --help                        # CLI entrypoint (once cli.py exists)
docker compose up -d postgres                    # start Postgres
docker compose logs -f postgres                  # tail logs
```

## Pre-commit checks (manual until pre-commit hook is added)

1. `uv run ruff check --fix` — must end clean
2. `uv run ruff format`
3. `uv run mypy src/` — must end clean
4. `uv run pytest -m "not evals"` — all green
5. (when eval suite exists) `uv run python -m evals.runner --set trivial` — `resolved@1 ≥ 70%`

If any of those fail: do NOT commit. Fix root cause.

## Push policy (agreed with user)

Push to `origin/main` automatically after each verified work block. A "verified block" =
component implemented + its tests passing + (if eval-relevant) regression gate green + user
has seen the result. Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).

Do NOT push if: tests fail, lint red, eval metric dropped, or block incomplete.

## Anti-patterns specific to this project

- ❌ Calling `anthropic.Anthropic()` directly. Use `claude_agent_sdk.query()`.
- ❌ Running the agent's `Bash` outside Docker. Always via `sandbox/docker_runner.py`.
- ❌ Adding a new model alias without updating `settings.py` and ADR-004.
- ❌ Catching `Exception:` broadly. Catch the specific type or let it propagate.
- ❌ Mocking Anthropic in tests beyond fixtures — integration tests must hit the real API on a tiny prompt.
- ❌ Touching `web/` (Next.js) until Week 3.

## When in doubt

Read the relevant ADR in `docs/adr/`. If no ADR covers the decision, write one before coding.

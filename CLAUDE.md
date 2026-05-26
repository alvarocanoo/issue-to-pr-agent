# CLAUDE.md — issue-to-pr-agent

> Instructions for Claude Code when working in this repo. Read before doing anything.

## What this repo is

Production-grade autonomous coding agent. Given a GitHub issue URL in a Python repo, opens a PR
with the fix. Hand-rolled tool loop over Groq Cloud + open-source models (`openai/gpt-oss-120b`,
`openai/gpt-oss-20b`). Components: Planner → Executor → Verifier, each defendible in a technical
interview against the paper that justifies it.

Companion project: `../claude-docs-rag` (RAG over Anthropic API docs). Do NOT touch it from here.

## Stack and conventions

- **Python 3.12**, managed with `uv`. Use `uv add <pkg>` to add deps (never `pip install`).
- **Type hints required**. `mypy --strict` runs in CI.
- **Ruff** for lint and format. Run `uv run ruff check --fix` and `uv run ruff format` before commit.
- **Tests**: `uv run pytest`. Unit tests in `tests/unit/`, integration in `tests/integration/`.
- **Secrets**: `.env` only (gitignored). Use `pydantic-settings` to load. Never hardcode keys.
- **Async I/O** where it touches DB or network (FastAPI, asyncpg).
- **All LLM calls** go through `LLMClient` in `src/issue_to_pr/llm/client.py` (single Groq SDK
  wrapper). Never instantiate `groq.Groq()` directly outside that module — keeps cost/token
  tracking and trace hooks in one place.

## Architecture invariants (do NOT violate without a new ADR)

1. **Every Bash command from the agent runs inside the sandbox** (`src/issue_to_pr/sandbox/`).
   The `PreToolUse` validator in `executor/hooks.py` whitelists commands; the runner restricts
   cwd, env, and timeout. Bypassing it requires a new ADR.
2. **Planner = `openai/gpt-oss-120b`, Executor = `openai/gpt-oss-20b`, Verifier = `openai/gpt-oss-120b`**
   (IDs in `settings.py`). Swap → ADR.
3. **No retrieval / vector DB** in this project. That's `claude-docs-rag`'s job.
4. **No fine-tuning**. Prompt + routing is the contract — see ADR-008.
5. **Every component has tests**. Coverage is not the metric; "can I delete this and CI tells me"
   is.

## Commands you'll use

```powershell
uv sync                                          # install/update deps from lock
uv add <pkg>                                     # add a dep
uv run pytest                                    # all tests
uv run pytest -m "not evals"                     # skip eval suite (faster)
uv run pytest tests/unit/test_sandbox.py -v      # single file
uv run ruff check --fix; uv run ruff format      # lint + format
uv run mypy src/                                 # type check strict
uv run issue-to-pr --help                        # CLI entrypoint
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

- ❌ Instantiating `groq.Groq()` directly outside `src/issue_to_pr/llm/client.py`.
- ❌ Running the agent's `Bash` outside the sandbox. Always via `sandbox/runner.py`.
- ❌ Adding a new model alias without updating `settings.py` and ADR-004.
- ❌ Catching `Exception:` broadly. Catch the specific type or let it propagate.
- ❌ Mocking Groq in tests beyond fixtures — integration tests must hit the real API on a tiny prompt.
- ❌ Touching `web/` (Next.js) until Week 3.

## When in doubt

Read the relevant ADR in `docs/adr/`. If no ADR covers the decision, write one before coding.

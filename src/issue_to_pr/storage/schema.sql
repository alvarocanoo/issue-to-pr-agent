-- issue-to-pr-agent storage schema. Applied idempotently by `Storage.init_schema()`.
-- Convention: prefer JSONB for nested artefacts (plan, verdict, history) so we can keep the
-- shape evolving without per-field migrations.

CREATE TABLE IF NOT EXISTS runs (
    id              BIGSERIAL PRIMARY KEY,
    task_id         TEXT        NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    mode            TEXT        NOT NULL CHECK (mode IN ('executor', 'orchestrator')),
    success         BOOLEAN     NOT NULL,
    reflexion_iterations  INTEGER,           -- NULL for executor-only mode
    executor_iterations   INTEGER NOT NULL,
    verify_exit_code      INTEGER NOT NULL,
    prompt_tokens         INTEGER NOT NULL DEFAULT 0,
    completion_tokens     INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd    REAL    NOT NULL DEFAULT 0.0,
    langfuse_trace_url    TEXT,
    elapsed_seconds       REAL    NOT NULL,
    -- JSONB payloads. Always present; objects can be empty {}.
    plan            JSONB       NOT NULL DEFAULT '{}'::jsonb,
    verdict         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    history         JSONB       NOT NULL DEFAULT '[]'::jsonb
);

-- Idempotent column adds for upgrades (skip when already there).
ALTER TABLE runs ADD COLUMN IF NOT EXISTS estimated_cost_usd REAL NOT NULL DEFAULT 0.0;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS langfuse_trace_url TEXT;

CREATE INDEX IF NOT EXISTS idx_runs_task_id     ON runs (task_id);
CREATE INDEX IF NOT EXISTS idx_runs_started_at  ON runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_mode_success ON runs (mode, success);

CREATE TABLE IF NOT EXISTS eval_reports (
    id              BIGSERIAL PRIMARY KEY,
    set_name        TEXT        NOT NULL,
    mode            TEXT        NOT NULL CHECK (mode IN ('executor', 'orchestrator')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total           INTEGER     NOT NULL,
    solved          INTEGER     NOT NULL,
    resolved_at_1   REAL        NOT NULL,
    total_prompt_tokens     INTEGER NOT NULL,
    total_completion_tokens INTEGER NOT NULL,
    total_elapsed_seconds   REAL    NOT NULL,
    raw             JSONB       NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eval_reports_started_at ON eval_reports (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_eval_reports_set_mode   ON eval_reports (set_name, mode);

"""Seed the runs table with synthetic data for dashboard demos.

Use when the DB is empty and we want to screenshot the dashboard without
spending API tokens. Idempotent: deletes the synthetic rows (task_id LIKE 'seed-%')
before inserting, leaving any real runs untouched.

    uv run python -m scripts.seed_runs
"""

from __future__ import annotations

import random
from typing import Any

from issue_to_pr.settings import get_settings
from issue_to_pr.storage import Storage

SEED_TASKS = [
    ("seed-001-typo", "fix typo in greet()"),
    ("seed-002-off-by-one", "fix off-by-one in count_up_to"),
    ("seed-003-missing-import", "add missing math import"),
    ("seed-004-wrong-return-type", "remove str() wrapping"),
    ("seed-005-none-comparison", "use is None instead of == None"),
    ("seed-006-typo-attribute", "rename .nname to .name"),
    ("seed-007-mutable-default", "replace mutable default with None sentinel"),
    ("seed-008-division-by-zero", "guard against b == 0 returning 0.0"),
    ("seed-009-fstring-bug", "prepend f to the string literal"),
    ("seed-010-recursion-base-case", "factorial(0) should return 1, not 0"),
]


def main() -> int:
    settings = get_settings()
    storage = Storage(settings.database_url)
    storage.init_schema()

    # Wipe any prior seed rows.
    with storage.connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM runs WHERE task_id LIKE 'seed-%'")

    rng = random.Random(42)  # noqa: S311  # deterministic seed for demo data, not crypto
    inserted = 0
    for task_id, description in SEED_TASKS:
        mode = rng.choice(["orchestrator", "executor"])
        success = rng.random() > 0.1  # 90% resolved rate
        exec_iter = rng.randint(6, 14)
        prompt_t = rng.randint(5000, 12000) * (3 if mode == "orchestrator" else 1)
        completion_t = rng.randint(400, 900)
        elapsed = rng.uniform(3.0, 35.0)
        reflexion = rng.randint(1, 2) if mode == "orchestrator" else None

        plan = (
            {
                "files_to_read": [task_id.split("-", 1)[1] + ".py"],
                "files_to_modify": [task_id.split("-", 1)[1] + ".py"],
                "steps": [
                    "Read the file",
                    f"Apply the fix described in: {description}",
                    "Run the verification command",
                ],
            }
            if mode == "orchestrator"
            else {}
        )
        final_verdict = (
            {
                "approved": success,
                "reasoning": (
                    "Minimal on-topic fix, tests pass, no test files modified."
                    if success
                    else "Tests still fail; the fix did not address the root cause."
                ),
                "feedback_for_executor": None
                if success
                else "Re-read the failing assertion and adjust the function accordingly.",
            }
            if mode == "orchestrator"
            else {}
        )

        # Build synthetic history with one rejected attempt for reflexion=2 runs.
        history: list[dict[str, Any]] = []
        if mode == "orchestrator" and reflexion is not None:
            if reflexion >= 2:
                history.append(
                    {
                        "iteration": 1,
                        "execution": {
                            "executor_iterations": rng.randint(4, 8),
                            "exit_reason": "done",
                            "tool_calls_count": rng.randint(3, 6),
                            "prompt_tokens": int(prompt_t * 0.4),
                            "completion_tokens": int(completion_t * 0.3),
                            "elapsed_seconds": round(elapsed * 0.45, 2),
                            "verify_exit_code": 1,
                        },
                        "verdict": {
                            "approved": False,
                            "reasoning": (
                                "Tests still fail; the assertion error suggests the fix "
                                "missed the edge case described in the task."
                            ),
                            "feedback_for_executor": (
                                "Re-read the failing assertion in the verify output and "
                                "extend the function to cover the edge case."
                            ),
                        },
                    }
                )
            history.append(
                {
                    "iteration": len(history) + 1,
                    "execution": {
                        "executor_iterations": exec_iter,
                        "exit_reason": "done",
                        "tool_calls_count": rng.randint(5, 9),
                        "prompt_tokens": prompt_t
                        - sum(h["execution"]["prompt_tokens"] for h in history),
                        "completion_tokens": completion_t
                        - sum(h["execution"]["completion_tokens"] for h in history),
                        "elapsed_seconds": round(
                            elapsed - sum(h["execution"]["elapsed_seconds"] for h in history), 2
                        ),
                        "verify_exit_code": 0 if success else 1,
                    },
                    "verdict": final_verdict,
                }
            )

        storage.insert_run(
            task_id=task_id,
            mode=mode,
            success=success,
            executor_iterations=exec_iter,
            verify_exit_code=0 if success else 1,
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
            elapsed_seconds=elapsed,
            reflexion_iterations=reflexion,
            plan=plan,
            verdict=final_verdict,
            history=history,
        )
        inserted += 1

    print(f"seeded {inserted} synthetic runs (task_id like 'seed-%')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

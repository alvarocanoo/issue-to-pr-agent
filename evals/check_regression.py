"""Read an eval report JSON and exit non-zero if resolved@1 drops below the threshold.

Used in CI to gate merges: a PR that lowers `resolved@1` below the configured threshold
fails the workflow, blocking the merge.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True, help="Path to eval report JSON.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.70,
        help="Minimum resolved@1 (0.0-1.0). Exit non-zero if actual is below.",
    )
    args = parser.parse_args(argv)

    if not args.report.exists():
        print(f"ERROR: report not found: {args.report}", file=sys.stderr)
        return 2

    data = json.loads(args.report.read_text(encoding="utf-8"))
    actual = float(data.get("resolved_at_1", 0.0))
    total = int(data.get("total", 0))
    solved = int(data.get("solved", 0))

    print(f"resolved@1 = {actual:.2%}  ({solved}/{total})  threshold = {args.threshold:.2%}")

    if actual < args.threshold:
        print("REGRESSION: resolved@1 below threshold", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

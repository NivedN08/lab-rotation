"""Prints data/bench/results.csv as a markdown table, one row per (split, system).

    uv run python -m bench.table
"""

from __future__ import annotations

import csv
import sys

from bench.data import DIMENSIONS, SHORT
from bench.run import RECORDS, RESULTS


def table(rows: list[dict]) -> str:
    by = {}
    for r in rows:
        by.setdefault((r["split"], r["system"]), {})[r["dimension"]] = r
    head = "| split | system | " + " | ".join(SHORT[d] for d in DIMENSIONS) + " | n replies |"
    lines = [head, "|" + "---|" * (len(DIMENSIONS) + 3)]
    for (split, system), dims in sorted(by.items()):
        cells = [dims[d]["macro_f1"] if d in dims else "" for d in DIMENSIONS]
        n = next(iter(dims.values()))["n"]
        lines.append(f"| {split} | {system} | " + " | ".join(str(c) for c in cells) + f" | {n} |")
    lines.append("| test | record (best team) | " + " | ".join(str(RECORDS[d]) for d in DIMENSIONS) + " | 1547 |")
    return "\n".join(lines)


def main() -> int:
    with RESULTS.open() as f:
        print(table(list(csv.DictReader(f))))
    return 0


if __name__ == "__main__":
    sys.exit(main())

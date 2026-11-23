"""`GET /api/bench`: N4's MRBench results for the examiner panel, and the three demo lines.

Rows come from Bruin's `learn.bench_results` in data/warehouse.duckdb (read-only); when the
table or file is missing or locked, from N4's data/bench/results.csv. Splits are sent as they
are (`dev-A`, `dev-B`, `test`): dev numbers are never relabelled as test numbers.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"
RESULTS_CSV = ROOT / "data" / "bench" / "results.csv"
README = ROOT / "bench" / "README.md"

# bench/README.md "Demo lines" (N4); used when the README has no such section.
LINES = [
    "MRBench (BEA 2025), held-out dev data: our tuned grading guide adds +5.1 macro-F1 (95% CI +2.1 to +8.0).",
    "Dev, tuned guide: MI 66.4 · ML 57.1 · PG 59.7 · AC 69.8. Best teams on the test set: 71.8 · 59.8 · 58.3 · 70.9.",
    "Two readers plus a referee score the same as one reader (+0.5, CI -0.8 to +1.8). "
    "Test set: score pending on CodaBench.",
]
COLUMNS = ("split", "dimension", "system", "macro_f1", "n", "record")


def _num(x, kind=float):
    if x is None or (isinstance(x, str) and not x.strip()):
        return None
    try:
        return kind(float(x)) if kind is int else kind(x)
    except (TypeError, ValueError):
        return None


def _row(r: dict) -> dict:
    return {"split": str(r.get("split") or ""), "dimension": str(r.get("dimension") or ""),
            "system": str(r.get("system") or ""), "macro_f1": _num(r.get("macro_f1")),
            "n": _num(r.get("n"), int), "record": _num(r.get("record"))}


def _from_warehouse() -> list[dict] | None:
    if not WAREHOUSE.exists():
        return None
    try:
        import duckdb
        con = duckdb.connect(str(WAREHOUSE), read_only=True)
        try:
            got = con.execute(f"select {', '.join(COLUMNS)} from learn.bench_results "
                              "order by split, dimension, system").fetchall()
        finally:
            con.close()
    except Exception:   # no table yet, or Bruin holds the write lock: the CSV answers
        return None
    return [_row(dict(zip(COLUMNS, r))) for r in got]


def _from_csv() -> list[dict] | None:
    try:
        with open(RESULTS_CSV, newline="") as f:
            rows = [_row(r) for r in csv.DictReader(f)]
    except OSError:
        return None
    return sorted(rows, key=lambda r: (r["split"], r["dimension"], r["system"]))


def demo_lines() -> list[str]:
    """The indented lines under "## Demo lines" in bench/README.md, else LINES."""
    try:
        text = README.read_text()
    except OSError:
        return list(LINES)
    m = re.search(r"^## Demo lines\s*$(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
    lines = [ln.strip() for ln in (m.group(1).splitlines() if m else []) if ln.startswith("    ") and ln.strip()]
    return lines[:3] if len(lines) >= 3 else list(LINES)


def results() -> dict:
    """{source: "bruin" | "csv" | "none", rows: [{split, dimension, system, macro_f1, n, record}], lines}."""
    rows, source = _from_warehouse(), "bruin"
    if not rows:   # missing, locked or not loaded yet
        rows, source = _from_csv(), "csv"
    if rows is None:
        rows, source = [], "none"
    return {"source": source, "rows": rows, "lines": demo_lines()}

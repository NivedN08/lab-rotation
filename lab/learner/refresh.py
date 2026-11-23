"""Refresh the learning tables in the Bruin warehouse from recorded sessions and bench results.

    refresh(ingest=True, bruin=True) -> {"sessions", "events", "bench", "ingestr": {...}, "bruin": {...}}

1. Flatten data/sessions/*.jsonl into data/bruin/learn/session_events.csv (one row per event,
   with the session's learner carried onto each row) and copy data/bench/results.csv (N4) to
   data/bruin/learn/bench.csv. Both files always exist, header only when there is no data.
2. ingestr loads both files into the warehouse as raw.session_events and raw.bench_results
   (an archive copy per refresh; skipped when ingestr is missing or the file has no rows).
3. `bruin run --tag learning bruin` builds learn.session_events, learn.skill_attempts,
   learn.session_scores, learn.bench_results and learn.bkt_mastery (the Python asset, which
   replays lab.learner.bkt over skill_attempts).
"""
from __future__ import annotations

import csv
import fcntl
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSIONS = ROOT / "data" / "sessions"
BENCH = ROOT / "data" / "bench" / "results.csv"
STAGE = ROOT / "data" / "bruin" / "learn"
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"
LOCK = ROOT / "data" / "bruin" / "run.lock"

EVENT_COLUMNS = ["session_id", "seq", "t", "k", "agent", "task", "learner", "mode", "trap", "tier", "score",
                 "beat_rival", "verdict", "passed", "data"]
BENCH_COLUMNS = ["split", "dimension", "system", "macro_f1", "n", "record"]


def flatten_sessions(src: Path = SESSIONS) -> list[list]:
    rows = []
    for f in sorted(src.glob("*.jsonl")) if src.exists() else []:
        learner, mode = None, None
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = e.get("data") or {}
            if e.get("k") == "session.start":
                learner, mode = d.get("learner"), d.get("mode")
            rows.append([f.stem, e.get("seq"), e.get("t"), e.get("k"), e.get("agent"), e.get("task"),
                         learner, mode, d.get("trap"), d.get("tier"), d.get("score"), d.get("beatRival"),
                         d.get("verdict"), d.get("passed"), json.dumps(d, separators=(",", ":"))])
    return rows


def sessions_dir() -> Path:
    """data/sessions, or LAB_SESSIONS_DIR when set (the session engine writes there too)."""
    return Path(os.environ.get("LAB_SESSIONS_DIR") or SESSIONS)


def stage(sessions: Path | None = None, bench: Path = BENCH, dest: Path = STAGE) -> dict:
    sessions = sessions or sessions_dir()
    dest.mkdir(parents=True, exist_ok=True)
    rows = flatten_sessions(sessions)
    with open(dest / "session_events.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(EVENT_COLUMNS)
        w.writerows([["" if v is None else v for v in r] for r in rows])
    bench_rows = []
    if bench.exists():
        with open(bench, newline="") as f:
            bench_rows = [[r.get(c, "") for c in BENCH_COLUMNS] for r in csv.DictReader(f)]
    with open(dest / "bench.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(BENCH_COLUMNS)
        w.writerows(bench_rows)
    return {"sessions": len({r[0] for r in rows}), "events": len(rows), "bench": len(bench_rows)}


def _ingestr(csv_path: Path, table: str) -> dict:
    if shutil.which("ingestr") is None:
        return {"table": table, "ok": False, "error": "ingestr is not installed"}
    t0 = time.perf_counter()
    proc = subprocess.run(
        ["ingestr", "ingest", "--source-uri", f"csv://{csv_path}", "--source-table", csv_path.stem,
         "--dest-uri", f"duckdb:///{WAREHOUSE}", "--dest-table", table, "--incremental-strategy", "replace",
         "--yes"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    return {"table": table, "ok": proc.returncode == 0, "ms": round((time.perf_counter() - t0) * 1000)}


def refresh(ingest: bool = True, bruin: bool = True, timeout: float = 180.0) -> dict:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            out = stage()
            out["ingestr"] = {}
            if ingest:
                if out["events"]:
                    out["ingestr"]["session_events"] = _ingestr(STAGE / "session_events.csv", "raw.session_events")
                if out["bench"]:
                    out["ingestr"]["bench_results"] = _ingestr(STAGE / "bench.csv", "raw.bench_results")
            if bruin and shutil.which("bruin"):
                t0 = time.perf_counter()
                proc = subprocess.run(
                    ["bruin", "run", "--tag", "learning", "--no-color",
                     "--var", f"learn={json.dumps(str(STAGE))}", "bruin"],
                    cwd=ROOT, capture_output=True, text=True, timeout=timeout)
                text = proc.stdout + proc.stderr
                out["bruin"] = {"ok": proc.returncode == 0, "seconds": round(time.perf_counter() - t0, 2),
                                "runId": f"bruin-learn-{time.strftime('%H%M%S')}"}
                if proc.returncode != 0:
                    out["bruin"]["error"] = " | ".join([ln for ln in text.splitlines() if ln.strip()][-4:])[:400]
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    return out


def bkt_mastery_table() -> list[tuple]:
    """learn.bkt_mastery rows from the warehouse: (learner, trap, score, attempts)."""
    import duckdb
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        return con.execute("SELECT learner, trap, score, attempts FROM learn.bkt_mastery "
                           "ORDER BY learner, trap").fetchall()
    finally:
        con.close()


if __name__ == "__main__":
    print(json.dumps(refresh(), indent=2))

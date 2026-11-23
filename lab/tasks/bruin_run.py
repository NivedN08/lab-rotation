"""Run a task's trap checks through Bruin: stage its public tables, `bruin run --tag task`, parse.

    run(task, timeout=60) -> {"runId", "ok", "checks": {check_id: passed}, "seconds", "error"?}

The staged CSVs have every column the assets in `bruin/assets/task/` read (empty where the task
does not have it), plus meta.csv with the member code the public dictionary states. Runs are
serialised with a file lock, because they share one DuckDB file.
"""
from __future__ import annotations

import csv
import fcntl
import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from lab import workspace_sql as ws
from lab.tasks.checks import CHECK_IDS
from lab.tasks.retail import stated_member_code

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "data" / "bruin" / "task"
LOCK = ROOT / "data" / "bruin" / "run.lock"

COLUMNS = {
    "visits": ["visit_id", "customer_id", "store_id", "visit_date", "items", "spend", "points_earned"],
    "customers": ["customer_id", "loyalty_flag", "points_balance", "card_id", "joined", "home_store"],
    "stores": ["store_id", "region", "pos_version", "opened"],
    "loyalty_accounts": ["customer_id", "card_id", "loyalty_flag", "points_balance", "enrolled"],
}
_LINE = re.compile(r"(Finished|Failed|Skipped):\s+(task\.[a-z_]+):(?:custom-check:)?([A-Za-z0-9_.\-:]+)")


def stage(task: Any, dest: Path = STAGE) -> Path:
    src = ws._task_dir(task)
    meta = json.loads((src / "tables.json").read_text())
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    names = [t["name"] for t in meta]
    flag_table = None
    for t in meta:
        if any(c["name"] == "loyalty_flag" for c in t["columns"]):
            flag_table = t["name"]
    for name, cols in COLUMNS.items():
        rows = []
        if name in names:
            with open(src / f"{name}.csv", newline="") as f:
                rows = list(csv.DictReader(f))
        with open(dest / f"{name}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows([[r.get(c, "") for c in cols] for r in rows])
    task_json = json.loads((src / "task.json").read_text())
    code = stated_member_code(task_json.get("dictionary", ""))
    with open(dest / "meta.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stated_member_code", "flag_table", "tables"])
        w.writerow(["" if code is None else code, flag_table or "", " ".join(names)])
    return dest


def parse(output: str) -> dict[str, bool]:
    """check id -> passed, from `bruin run` output lines."""
    out: dict[str, bool] = {}
    ids = set(CHECK_IDS.values())
    for status, _asset, name in _LINE.findall(output):
        if name in ids:
            out[name] = status == "Finished"
    return out


def run(task: Any, timeout: float = 60.0) -> dict:
    run_id = f"bruin-{time.strftime('%H%M%S')}-{uuid.uuid4().hex[:4]}"
    if shutil.which("bruin") is None:
        return {"runId": run_id, "ok": False, "checks": {}, "seconds": 0.0, "error": "bruin is not installed"}
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            stage(task)
            proc = subprocess.run(
                ["bruin", "run", "--tag", "task", "--no-color", "--var", f"stage={json.dumps(str(STAGE))}", "bruin"],
                cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"runId": run_id, "ok": False, "checks": {}, "seconds": round(time.perf_counter() - t0, 2),
                    "error": "bruin run timed out"}
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    text = proc.stdout + "\n" + proc.stderr
    checks = parse(text)
    res = {"runId": run_id, "ok": len(checks) == len(CHECK_IDS), "checks": checks,
           "seconds": round(time.perf_counter() - t0, 2)}
    if not res["ok"]:
        tail = [ln for ln in text.splitlines() if ln.strip()][-3:]
        res["error"] = " | ".join(tail)[:300]
    return res

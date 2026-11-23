"""The learner's read-only SQL box over one task's public tables.

A task directory holds `tables.json` (the table list, as in `contract/mock_task/`)
and one `<name>.csv` per table. Nothing else in it is read, so the sealed key can
never be queried. Tables are loaded once per directory into an in-memory DuckDB;
then file access, extensions and configuration changes are switched off, and every
query runs on its own cursor with a 500-row cap and a 3 s timeout.

Functions for the server (shapes in `contract/api.md`):

    tables(task) -> [{name, about, columns: [{name, type, about?}], rowCount}]
    table_rows(task, table, offset=0, limit=100) -> {rows: [[cell]]}
    profile(task, table) -> {table, columns: [ColumnProfile]}
    run_query(task, sql) -> {columns, rows, ms, truncated} or {error}

`task` is a task directory (str or Path), a dict with `dir`, or an object with a
`public_dir` attribute (a bank task).
"""
from __future__ import annotations

import datetime as _dt
import decimal
import json
import math
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import duckdb

ROW_CAP = 500
TIMEOUT_S = 3.0
MAX_SQL_CHARS = 10_000

_DUCK_TYPE = {"text": "VARCHAR", "int": "BIGINT", "real": "DOUBLE", "date": "DATE"}

# Defense in depth: DuckDB's own lockdown already blocks these, but a clear
# message is kinder than a permission error.
_BLOCKED = {
    "copy", "attach", "detach", "install", "load", "pragma", "export", "import",
    "checkpoint", "vacuum", "call", "set", "reset", "use",
    "read_csv", "read_csv_auto", "read_parquet", "parquet_scan", "read_json",
    "read_json_auto", "read_json_objects", "read_ndjson", "read_text", "read_blob",
    "sniff_csv", "glob", "parquet_metadata", "parquet_schema", "iceberg_scan",
    "delta_scan", "sqlite_scan", "postgres_scan", "mysql_scan", "httpfs",
    "duckdb_secrets", "duckdb_extensions", "getenv", "query_table", "query",
}
_STRING_LIT = re.compile(r"'(?:[^']|'')*'")
_WORD = re.compile(r"[a-z_][a-z0-9_]*")


class TaskTables:
    """One task's public tables, loaded and locked."""

    def __init__(self, task_dir: Path):
        self.dir = task_dir
        meta = json.loads((task_dir / "tables.json").read_text())
        self.meta = {t["name"]: t for t in meta}
        self.order = [t["name"] for t in meta]
        self.con = duckdb.connect(":memory:")
        for t in meta:
            name = t["name"]
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
                raise ValueError(f"bad table name {name!r}")
            cols = {c["name"]: _DUCK_TYPE[c["type"]] for c in t["columns"]}
            path = task_dir / f"{name}.csv"
            self.con.execute(
                f"CREATE TABLE {name} AS SELECT * FROM read_csv(?, header=true, columns=?)",
                [str(path), cols],
            )
        for s in (
            "SET enable_external_access=false",
            "SET autoinstall_known_extensions=false",
            "SET autoload_known_extensions=false",
            "SET allow_community_extensions=false",
            "SET memory_limit='256MB'",
            "SET threads=2",
            "SET lock_configuration=true",
        ):
            self.con.execute(s)
        self.lock = threading.Lock()

    def cursor(self) -> duckdb.DuckDBPyConnection:
        with self.lock:
            return self.con.cursor()

    def table(self, name: str) -> dict:
        if name not in self.meta:
            raise KeyError(f"no table named {name!r}")
        return self.meta[name]

    def order_by(self, name: str) -> str:
        t = self.table(name)
        cols = [c["name"] for c in t["columns"]]
        key = t.get("key") or cols[0]
        rest = [c for c in cols if c != key]
        return ", ".join(f'"{c}"' for c in [key, *rest])


_CACHE: dict[tuple[str, float], TaskTables] = {}
_CACHE_LOCK = threading.Lock()


def _task_dir(task: Any) -> Path:
    if isinstance(task, (str, Path)):
        return Path(task)
    if isinstance(task, dict):
        return Path(task.get("dir") or task["public_dir"])
    return Path(task.public_dir)


def load(task: Any) -> TaskTables:
    d = _task_dir(task).resolve()
    stamp = (d / "tables.json").stat().st_mtime
    key = (str(d), stamp)
    with _CACHE_LOCK:
        tt = _CACHE.get(key)
        if tt is None:
            tt = TaskTables(d)
            _CACHE[key] = tt
        return tt


def cell(v: Any) -> Any:
    """A JSON-safe cell: string, number, boolean or None."""
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, decimal.Decimal):
        f = float(v)
        return f if math.isfinite(f) else None
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).hex()
    if isinstance(v, (uuid.UUID, _dt.timedelta)):
        return str(v)
    if isinstance(v, (list, tuple, dict)):
        return json.dumps(v, default=str)
    return str(v)


def tables(task: Any) -> list[dict]:
    tt = load(task)
    out = []
    for name in tt.order:
        t = tt.meta[name]
        n = tt.cursor().execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        cols = []
        for c in t["columns"]:
            col = {"name": c["name"], "type": c["type"]}
            if c.get("about"):
                col["about"] = c["about"]
            cols.append(col)
        out.append({"name": name, "about": t.get("about", ""), "columns": cols, "rowCount": n})
    return out


def table_rows(task: Any, table: str, offset: int = 0, limit: int = 100) -> dict:
    tt = load(task)
    tt.table(table)
    offset = max(0, int(offset))
    limit = max(0, min(int(limit), ROW_CAP))
    cur = tt.cursor()
    rows = cur.execute(
        f"SELECT * FROM {table} ORDER BY {tt.order_by(table)} LIMIT ? OFFSET ?",
        [limit, offset],
    ).fetchall()
    return {"rows": [[cell(v) for v in r] for r in rows]}


def profile(task: Any, table: str) -> dict:
    tt = load(task)
    t = tt.table(table)
    cur = tt.cursor()
    cols = []
    for c in t["columns"]:
        name, typ = c["name"], c["type"]
        q = f'"{name}"'
        count, nulls, distinct = cur.execute(
            f"SELECT count({q}), count(*) - count({q}), count(DISTINCT {q}) FROM {table}"
        ).fetchone()
        p: dict[str, Any] = {"column": name, "type": typ, "count": count,
                             "nulls": nulls, "distinct": distinct}
        if typ in ("int", "real", "date"):
            lo, hi = cur.execute(f"SELECT min({q}), max({q}) FROM {table}").fetchone()
            p["min"], p["max"] = cell(lo), cell(hi)
        if typ in ("int", "real"):
            m = cur.execute(f"SELECT avg({q}) FROM {table}").fetchone()[0]
            p["mean"] = round(m, 4) if m is not None else None
        top = cur.execute(
            f"SELECT {q}, count(*) AS n FROM {table} WHERE {q} IS NOT NULL "
            f"GROUP BY {q} ORDER BY n DESC, {q} LIMIT 5"
        ).fetchall()
        p["top"] = [{"value": cell(v), "count": n} for v, n in top]
        cols.append(p)
    return {"table": table, "columns": cols}


def check_sql(con: duckdb.DuckDBPyConnection, sql: str) -> str | None:
    """Return a plain-words reason the query is refused, or None when it may run."""
    if not sql or not sql.strip():
        return "Write a query first."
    if len(sql) > MAX_SQL_CHARS:
        return "That query is too long."
    words = set(_WORD.findall(_STRING_LIT.sub("''", sql.lower())))
    bad = sorted(words & _BLOCKED)
    if bad:
        return f"Only plain SELECT queries over this task's tables are allowed ({bad[0]} is blocked)."
    try:
        stmts = con.extract_statements(sql)
    except duckdb.Error as e:
        return _short(e)
    if len(stmts) != 1:
        return "Run one statement at a time."
    if stmts[0].type != duckdb.StatementType.SELECT:
        return "Only SELECT queries are allowed: the tables are read-only."
    return None


def run_query(task: Any, sql: str) -> dict:
    tt = load(task)
    cur = tt.cursor()
    reason = check_sql(cur, sql)
    if reason:
        return {"error": reason}
    timer = threading.Timer(TIMEOUT_S, cur.interrupt)
    t0 = time.perf_counter()
    timer.start()
    try:
        res = cur.execute(sql)
        cols = [d[0] for d in (res.description or [])]
        rows = res.fetchmany(ROW_CAP + 1)
    except duckdb.InterruptException:
        return {"error": f"The query took longer than {TIMEOUT_S:g} seconds and was stopped."}
    except duckdb.Error as e:
        if time.perf_counter() - t0 >= TIMEOUT_S:
            return {"error": f"The query took longer than {TIMEOUT_S:g} seconds and was stopped."}
        return {"error": _short(e)}
    finally:
        timer.cancel()
        try:
            cur.close()
        except duckdb.Error:
            pass
    ms = round((time.perf_counter() - t0) * 1000, 1)
    truncated = len(rows) > ROW_CAP
    rows = rows[:ROW_CAP]
    return {"columns": cols, "rows": [[cell(v) for v in r] for r in rows],
            "ms": ms, "truncated": truncated}


def _short(e: Exception) -> str:
    msg = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
    # DuckDB messages can name local paths; keep only the first line, no paths.
    msg = re.sub(r"(/[^\s\"']+)+", "<path>", msg)
    return msg[:300]

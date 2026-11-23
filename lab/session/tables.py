"""A task's public tables in an in-memory DuckDB: list, rows, profiles and read-only SQL.

This is the session engine's own copy, used for the mock task and whenever
`lab.workspace_sql` (N3) is not there yet. It follows `contract/api.md`:

- rows come ordered by the table's key column, `limit` at most 500;
- SQL is one SELECT-like statement, no file, network or extension access,
  500-row cap (`truncated`), 3 s timeout; a bad or blocked query returns `{error}`.

A task folder holds `tables.json` (the public table list with `key` and columns) and
one `<name>.csv` per table.
"""

from __future__ import annotations

import json
import pathlib
import re
import threading
import time

import duckdb

ROW_CAP = 500
TIMEOUT_S = 3.0
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
ALLOWED = {duckdb.StatementType.SELECT}
# Table functions and statements that reach outside the in-memory tables. The DuckDB settings
# below block them anyway; this list gives a plain error before DuckDB is asked.
BLOCKED_WORDS = re.compile(
    r"\b(read_csv|read_csv_auto|read_parquet|read_json|read_json_auto|read_text|read_blob|glob|"
    r"parquet_scan|csv_scan|sniff_csv|attach|detach|copy|install|load|pragma|export|import|"
    r"httpfs|duckdb_secrets|getenv|sqlite_scan|postgres_scan|mysql_scan|delta_scan|iceberg_scan)\b",
    re.I)
TYPE_MAP = {
    "VARCHAR": "text", "BOOLEAN": "int",
    "TINYINT": "int", "SMALLINT": "int", "INTEGER": "int", "BIGINT": "int", "HUGEINT": "int",
    "UTINYINT": "int", "USMALLINT": "int", "UINTEGER": "int", "UBIGINT": "int",
    "DOUBLE": "real", "FLOAT": "real", "REAL": "real",
    "DATE": "date", "TIMESTAMP": "date", "TIMESTAMP WITH TIME ZONE": "date",
}
SQL_TYPES = {"text": "VARCHAR", "int": "BIGINT", "real": "DOUBLE", "date": "DATE"}


class TableError(Exception):
    """A bad table name or argument (the server answers 400 or 404)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def column_type(duck_type: str) -> str:
    t = str(duck_type).upper()
    if t.startswith("DECIMAL"):
        return "real"
    if t.startswith("TIMESTAMP"):
        return "date"
    return TYPE_MAP.get(t, "text")


def cell(value):
    """A JSON-safe cell: str, number, bool or None."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        return float(value)   # Decimal
    except (TypeError, ValueError):
        return str(value)


class TaskTables:
    """One task's public tables, loaded once into a private in-memory DuckDB."""

    def __init__(self, folder: str | pathlib.Path, tables: list[dict] | None = None):
        self.folder = pathlib.Path(folder)
        self.meta = tables if tables is not None else json.loads((self.folder / "tables.json").read_text())
        self._lock = threading.Lock()
        self.con = duckdb.connect(":memory:")
        for t in self.meta:
            name = t["name"]
            if not NAME_RE.match(name):
                raise TableError(f"bad table name {name!r}")
            cols = ", ".join(f"'{c['name']}': '{SQL_TYPES.get(c.get('type'), 'VARCHAR')}'" for c in t["columns"])
            path = str((self.folder / f"{name}.csv").resolve()).replace("'", "''")
            self.con.execute(f"CREATE TABLE \"{name}\" AS SELECT * FROM read_csv('{path}', header=true, "
                             f"columns={{{cols}}})")
        # Lock the box: no files, no network, no extensions, and the settings cannot be undone.
        for stmt in ("SET enable_progress_bar = false", "SET enable_external_access = false", "SET autoload_known_extensions = false",
                     "SET autoinstall_known_extensions = false", "SET lock_configuration = true"):
            try:
                self.con.execute(stmt)
            except duckdb.Error:
                pass
        self.by_name = {t["name"]: t for t in self.meta}

    # ------------------------------------------------------------------ tables, rows, profile
    def tables(self) -> list[dict]:
        out = []
        for t in self.meta:
            n = self.con.execute(f'SELECT count(*) FROM "{t["name"]}"').fetchone()[0]
            cols = [{k: c[k] for k in ("name", "type", "about") if k in c} for c in t["columns"]]
            out.append({"name": t["name"], "about": t.get("about", ""), "columns": cols, "rowCount": int(n)})
        return out

    def _table(self, name: str) -> dict:
        if name not in self.by_name:
            raise TableError(f"no table {name}", 404)
        return self.by_name[name]

    def rows(self, name: str, offset: int = 0, limit: int = 100) -> dict:
        t = self._table(name)
        offset, limit = max(0, int(offset)), max(0, min(ROW_CAP, int(limit)))
        key = t.get("key") or t["columns"][0]["name"]
        cols = ", ".join(f'"{c["name"]}"' for c in t["columns"])
        with self._lock:
            got = self.con.execute(f'SELECT {cols} FROM "{name}" ORDER BY "{key}" LIMIT ? OFFSET ?',
                                   [limit, offset]).fetchall()
        return {"rows": [[cell(v) for v in r] for r in got]}

    def profile(self, name: str) -> dict:
        t = self._table(name)
        out = []
        with self._lock:
            for c in t["columns"]:
                col, typ = c["name"], c.get("type", "text")
                q = f'"{col}"'
                count, nulls, distinct = self.con.execute(
                    f'SELECT count(*), count(*) - count({q}), count(DISTINCT {q}) FROM "{name}"').fetchone()
                p = {"column": col, "type": typ, "count": int(count), "nulls": int(nulls),
                     "distinct": int(distinct)}
                if typ in ("int", "real", "date"):
                    lo, hi = self.con.execute(f'SELECT min({q}), max({q}) FROM "{name}"').fetchone()
                    p["min"], p["max"] = cell(lo), cell(hi)
                if typ in ("int", "real"):
                    mean = self.con.execute(f'SELECT avg({q}) FROM "{name}"').fetchone()[0]
                    p["mean"] = round(float(mean), 4) if mean is not None else None
                top = self.con.execute(
                    f'SELECT {q}, count(*) AS n FROM "{name}" GROUP BY 1 ORDER BY n DESC, 1 LIMIT 5').fetchall()
                p["top"] = [{"value": cell(v), "count": int(n)} for v, n in top]
                out.append(p)
        return {"table": name, "columns": out}

    # ------------------------------------------------------------------------------- SQL
    def check_sql(self, sql: str) -> str | None:
        """None when the query may run, else the reason in plain words."""
        if not isinstance(sql, str) or not sql.strip():
            return "the query is empty"
        if len(sql) > 10000:
            return "the query is too long"
        if BLOCKED_WORDS.search(sql):
            return "that function or statement is not allowed in the workspace"
        try:
            stmts = duckdb.extract_statements(sql)
        except duckdb.Error as e:
            return str(e).strip().splitlines()[0][:300] if str(e).strip() else "the query does not parse"
        if len(stmts) != 1:
            return "one statement at a time"
        if stmts[0].type not in ALLOWED:
            return "the workspace is read-only: SELECT queries only"
        return None

    def query(self, sql: str) -> dict:
        """{columns, rows, ms, truncated} or {error, ms}."""
        start = time.monotonic()
        blocked = self.check_sql(sql)
        if blocked:
            return {"error": blocked, "ms": 0}
        with self._lock:
            timer = threading.Timer(TIMEOUT_S, self.con.interrupt)
            timer.start()
            try:
                res = self.con.execute(sql.strip().rstrip(";"))
                cols = [d[0] for d in (res.description or [])]
                got = res.fetchmany(ROW_CAP + 1)
            except duckdb.InterruptException:
                return {"error": f"the query took longer than {TIMEOUT_S:g} s", "ms": int((time.monotonic() - start) * 1000)}
            except duckdb.Error as e:
                msg = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
                return {"error": msg[:300], "ms": int((time.monotonic() - start) * 1000)}
            finally:
                timer.cancel()
        truncated = len(got) > ROW_CAP
        return {"columns": cols, "rows": [[cell(v) for v in r] for r in got[:ROW_CAP]],
                "ms": int((time.monotonic() - start) * 1000), "truncated": truncated}

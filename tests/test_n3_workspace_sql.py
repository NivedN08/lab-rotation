import json
import os
from pathlib import Path

import pytest

from lab import workspace_sql as ws

MOCK = Path(__file__).resolve().parent.parent / "contract" / "mock_task"


def test_tables_match_contract():
    t = ws.tables(MOCK)
    assert [x["name"] for x in t] == ["visits", "customers", "stores"]
    v = t[0]
    assert v["rowCount"] == 300
    assert set(v) == {"name", "about", "columns", "rowCount"}
    assert v["columns"][0] == {"name": "visit_id", "type": "text", "about": "One store visit"}
    assert [c["type"] for c in v["columns"]] == ["text", "text", "text", "date", "int", "real"]


def test_rows_fixed_order_and_cap():
    a = ws.table_rows(MOCK, "visits", offset=0, limit=10)["rows"]
    b = ws.table_rows(MOCK, "visits", offset=5, limit=5)["rows"]
    assert a[5:] == b
    assert a[0][0] == "v0001" and a[0][3] == "2026-08-18"
    assert isinstance(a[0][4], int) and isinstance(a[0][5], float)
    assert len(ws.table_rows(MOCK, "visits", limit=10_000)["rows"]) == 300  # capped at 500
    assert ws.table_rows(MOCK, "visits", offset=299, limit=5)["rows"][0][0] == "v0300"
    with pytest.raises(KeyError):
        ws.table_rows(MOCK, "secret")


def test_profile_shape():
    p = ws.profile(MOCK, "visits")
    assert p["table"] == "visits"
    by = {c["column"]: c for c in p["columns"]}
    spend = by["spend"]
    assert spend["count"] == 300 and spend["nulls"] == 0
    assert {"min", "max", "mean"} <= set(spend)
    assert "mean" not in by["visit_date"] and "min" in by["visit_date"]
    assert "min" not in by["store_id"]
    top = by["store_id"]["top"]
    assert 1 <= len(top) <= 5
    assert top == sorted(top, key=lambda x: -x["count"])
    json.dumps(p)  # JSON-safe


def test_select_works():
    r = ws.run_query(MOCK, "SELECT region, count(*) AS n FROM stores GROUP BY region ORDER BY region")
    assert r["columns"] == ["region", "n"]
    assert r["truncated"] is False and r["ms"] >= 0
    assert sum(row[1] for row in r["rows"]) == 12


def test_join_and_cte():
    r = ws.run_query(MOCK, """
        WITH v AS (SELECT * FROM visits)
        SELECT c.loyalty_member, round(avg(v.spend), 2) FROM v
        JOIN customers c USING (customer_id) GROUP BY 1 ORDER BY 1;""")
    assert "error" not in r and len(r["rows"]) == 2


def test_row_cap_truncates():
    r = ws.run_query(MOCK, "SELECT * FROM visits a, stores b")
    assert len(r["rows"]) == 500 and r["truncated"] is True


def test_timeout(monkeypatch):
    monkeypatch.setattr(ws, "TIMEOUT_S", 0.3)
    r = ws.run_query(MOCK, "SELECT sum(a.range * b.range) FROM range(200000) a, range(200000) b")
    assert "error" in r and "seconds" in r["error"]


@pytest.mark.parametrize("sql", [
    "DROP TABLE visits",
    "DELETE FROM visits",
    "UPDATE visits SET spend = 0",
    "INSERT INTO stores VALUES ('x','y','z',1)",
    "CREATE TABLE x AS SELECT 1",
    "SELECT 1; DROP TABLE visits",
    "SELECT 1; SELECT 2",
    "COPY visits TO 'out.csv'",
    "ATTACH 'other.duckdb'",
    "INSTALL httpfs",
    "LOAD httpfs",
    "PRAGMA database_list",
    "SET enable_external_access = true",
    "SELECT * FROM read_csv('/etc/hosts')",
    "SELECT * FROM read_text('.env')",
    "SELECT * FROM glob('*')",
    "SELECT * FROM '.env'",
    "SELECT * FROM 'contract/mock_task/visits.csv'",
    "SELECT * FROM query('SELECT 1')",
    "SELECT getenv('HOME')",
    "EXPORT DATABASE 'x'",
    "PIVOT stores ON region",
    "EXPLAIN SELECT 1",
    "",
    "   ",
])
def test_escapes_blocked(sql):
    r = ws.run_query(MOCK, sql)
    assert "error" in r, sql
    assert "/Users" not in r["error"]


def test_tables_survive_blocked_writes():
    ws.run_query(MOCK, "DROP TABLE visits")
    ws.run_query(MOCK, "DELETE FROM visits")
    assert ws.run_query(MOCK, "SELECT count(*) FROM visits")["rows"] == [[300]]


def test_no_file_access_even_through_strings():
    secret = MOCK.parent.parent / ".env"
    r = ws.run_query(MOCK, f"SELECT * FROM read_csv_auto('{secret}')")
    assert "error" in r
    # a quoted literal that names a blocked word is fine
    r = ws.run_query(MOCK, "SELECT 'copy and load' AS note")
    assert r["rows"] == [["copy and load"]]


def test_only_public_files_are_read(tmp_path):
    d = tmp_path / "task"
    d.mkdir()
    (d / "tables.json").write_text(json.dumps([{
        "name": "stores", "about": "x", "rowCount": 1, "key": "store_id",
        "columns": [{"name": "store_id", "type": "text"}]}]))
    (d / "stores.csv").write_text("store_id\nst01\n")
    (d / "key.json").write_text('{"trap": "unit_mismatch"}')
    r = ws.run_query(d, "SELECT * FROM key")
    assert "error" in r
    assert ws.run_query({"dir": str(d)}, "SELECT * FROM stores")["rows"] == [["st01"]]


def test_secret_env_not_reachable(monkeypatch):
    monkeypatch.setenv("LAB_FAKE_KEY", "nope")
    for sql in ["SELECT getenv('LAB_FAKE_KEY')", "SELECT current_setting('LAB_FAKE_KEY')"]:
        r = ws.run_query(MOCK, sql)
        assert "nope" not in json.dumps(r)

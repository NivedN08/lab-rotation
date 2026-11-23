"""One data-quality check per trap, run over a task's public tables. Ines's evidence.

    run_checks(task) -> [check.result data]   # {check, trap, passed, detail, rows, columns}
    failing(task) -> [check id]

The same SQL is attached to the Bruin task assets (`bruin/assets/task_*.sql`) as custom checks,
so `bruin run` over a task gives the same pass/fail; `lab.tasks.bruin_run` runs that. `task` is
anything `lab.workspace_sql` accepts (a public task folder or a bank task). Checks read only the
public tables and the public data dictionary: what a careful analyst could run.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from lab import workspace_sql as ws
from lab.tasks.retail import POS_NEW, UNIT_RATIO_LIMIT, stated_member_code

CHECK_IDS = {
    "duplicate_rows": "duplicate_rows.visits_unique_measured",
    "unit_mismatch": "unit_mismatch.spend_range_by_region",
    "dictionary_flip": "dictionary_flip.flag_matches_points",
    "confounder": "confounder.member_share_by_pos",
    "hidden_variable": "hidden_variable.flag_in_main_tables",
}
SHARE_GAP = 0.3
SPEND_RATIO = 1.3

# The SQL each check runs, in DuckDB; a check fails when its query returns any row.
SQL = {
    "duplicate_rows": """
        SELECT visit_id, customer_id, store_id, visit_date, items, spend FROM visits
        WHERE (store_id, visit_date, items, spend) IN (
            SELECT (store_id, visit_date, items, spend) FROM visits
            GROUP BY store_id, visit_date, items, spend HAVING count(*) > 1)
        ORDER BY store_id, visit_date, spend, visit_id""",
    "unit_mismatch": """
        WITH r AS (SELECT s.region, median(v.spend) AS med, min(v.spend) AS lo, max(v.spend) AS hi
                   FROM visits v JOIN stores s USING (store_id) GROUP BY s.region),
             ref AS (SELECT median(med) AS m FROM r)
        SELECT r.region, round(r.med, 2) AS median_spend, r.lo AS min_spend, r.hi AS max_spend
        FROM r, ref WHERE abs(ln(r.med / ref.m)) > ln({ratio}) ORDER BY r.region""",
}


def _where(con, column: str, tables: list[str]) -> str | None:
    for t in tables:
        cols = [r[0] for r in con.execute(f"DESCRIBE {t}").fetchall()]
        if column in cols:
            return t
    return None


def _flag_join(con, tables: list[str]) -> tuple[str | None, str]:
    """SQL fragment giving (customer_id, loyalty_flag, points_balance?) wherever the flag lives."""
    ft = _where(con, "loyalty_flag", tables)
    if ft is None:
        return None, ""
    cols = [r[0] for r in con.execute(f"DESCRIBE {ft}").fetchall()]
    pts = "points_balance" if "points_balance" in cols else "NULL"
    if "customer_id" in cols:
        return ft, f"SELECT customer_id, loyalty_flag, {pts} AS points FROM {ft}"
    ccols = [r[0] for r in con.execute("DESCRIBE customers").fetchall()]
    key = next(c for c in cols if c in ccols)
    return ft, (f"SELECT c.customer_id, a.loyalty_flag, a.{pts} AS points FROM customers c "
                f"JOIN {ft} a USING ({key})" if pts != "NULL" else
                f"SELECT c.customer_id, a.loyalty_flag, NULL AS points FROM customers c JOIN {ft} a USING ({key})")


def _result(trap: str, passed: bool, detail: str, rows=None, columns=None) -> dict:
    out = {"check": CHECK_IDS[trap], "trap": trap, "passed": bool(passed), "detail": detail}
    if rows:
        out["rows"] = [[ws.cell(v) for v in r] for r in rows[:5]]
        out["columns"] = columns
    return out


def _dup(con, tables, dictionary) -> dict:
    cur = con.execute(SQL["duplicate_rows"])
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    n = con.execute("SELECT count(*) FROM visits").fetchone()[0]
    if not rows:
        return _result("duplicate_rows", True, f"no two visits share store, date, items and spend ({n} visits)")
    groups = len({(r[2], r[3], r[4], r[5]) for r in rows})
    return _result("duplicate_rows", False,
                   f"{len(rows)} visits fall in {groups} groups that repeat store, date, items and spend "
                   f"to the cent ({n} visits in all)", rows, cols)


def _units(con, tables, dictionary) -> dict:
    if "stores" not in tables or _where(con, "region", ["stores"]) is None:
        return _result("unit_mismatch", True, "no region column, so there is nothing to compare")
    cur = con.execute(SQL["unit_mismatch"].format(ratio=UNIT_RATIO_LIMIT))
    bad = cur.fetchall()
    if not bad:
        lo, hi = con.execute("""SELECT min(m), max(m) FROM (SELECT median(spend) AS m FROM visits
                                JOIN stores USING (store_id) GROUP BY region)""").fetchone()
        return _result("unit_mismatch", True, f"median spend per region runs {lo:.2f} to {hi:.2f} dollars")
    region = bad[0][0]
    other = con.execute("""SELECT min(spend), max(spend) FROM visits JOIN stores USING (store_id)
                           WHERE region <> ?""", [region]).fetchone()
    cur = con.execute("""SELECT visit_id, store_id, region, spend FROM visits JOIN stores USING (store_id)
                         WHERE region = ? ORDER BY spend DESC, visit_id LIMIT 5""", [region])
    rows = cur.fetchall()
    ratio = bad[0][1] / max(1e-9, con.execute(
        "SELECT median(spend) FROM visits JOIN stores USING (store_id) WHERE region <> ?", [region]).fetchone()[0])
    return _result("unit_mismatch", False,
                   f"{region} spend runs {_n(bad[0][2])} to {_n(bad[0][3])}; every other region runs "
                   f"{_n(other[0])} to {_n(other[1])} (median about {ratio:.0f}x)",
                   rows, [d[0] for d in cur.description])


def _coding(con, tables, dictionary) -> dict:
    code = stated_member_code(dictionary)
    ft, frag = _flag_join(con, tables)
    if ft is None or code is None:
        return _result("dictionary_flip", True, "no loyalty flag to check against points")
    if con.execute(f"SELECT count(points) FROM ({frag})").fetchone()[0] > 0:
        share, n = con.execute(f"SELECT avg((points > 0)::INT), count(*) FROM ({frag}) WHERE loyalty_flag = ?",
                               [code]).fetchone()
        cur = con.execute(f"SELECT customer_id, loyalty_flag, points AS points_balance FROM ({frag}) "
                          f"WHERE loyalty_flag = ? AND points = 0 ORDER BY customer_id LIMIT 5", [code])
        unit = "customers"
    elif _where(con, "points_earned", ["visits"]):
        share, n = con.execute(f"""SELECT avg((v.points_earned > 0)::INT), count(*) FROM visits v
                                   JOIN ({frag}) f USING (customer_id) WHERE f.loyalty_flag = ?""",
                               [code]).fetchone()
        cur = con.execute(f"""SELECT v.visit_id, v.customer_id, f.loyalty_flag, v.points_earned FROM visits v
                              JOIN ({frag}) f USING (customer_id) WHERE f.loyalty_flag = ? AND v.points_earned = 0
                              ORDER BY v.visit_id LIMIT 5""", [code])
        unit = "visits"
    else:
        return _result("dictionary_flip", True, "no points column to check the flag against")
    rows = cur.fetchall()
    share = share or 0.0
    if share >= 0.5:
        return _result("dictionary_flip", True,
                       f"{share:.0%} of {unit} coded {code} (members, per the dictionary) have points")
    return _result("dictionary_flip", False,
                   f"the dictionary says {code} = member, but only {share:.0%} of the {n} {unit} coded {code} "
                   f"have any points: the coding is backwards", rows, [d[0] for d in cur.description])


def _confounder(con, tables, dictionary) -> dict:
    ft, frag = _flag_join(con, tables)
    if "stores" not in tables or ft is None or _where(con, "pos_version", ["stores"]) is None:
        return _result("confounder", True, "no POS version and flag to compare")
    cur = con.execute(f"""SELECT s.pos_version, count(*) AS visits, round(avg(f.loyalty_flag), 3) AS flag_share,
                                 round(median(v.spend), 2) AS median_spend
                          FROM visits v JOIN stores s USING (store_id) JOIN ({frag}) f USING (customer_id)
                          GROUP BY s.pos_version ORDER BY s.pos_version""")
    rows = cur.fetchall()
    if len(rows) < 2:
        return _result("confounder", True, "only one POS version")
    shares = [r[2] for r in rows]
    meds = [r[3] for r in rows]
    gap = max(shares) - min(shares)
    ratio = max(meds) / max(1e-9, min(meds))
    desc = ", ".join(f"POS {r[0]}: flag=1 share {r[2]:.0%}, median spend {r[3]:.2f}" for r in rows)
    if gap > SHARE_GAP and ratio > SPEND_RATIO:
        return _result("confounder", False,
                       f"spend and loyalty mix both shift with POS version ({desc}); compare within POS",
                       rows, [d[0] for d in cur.description])
    return _result("confounder", True, f"no POS version shifts both spend and loyalty mix ({desc})")


def _hidden(con, tables, dictionary) -> dict:
    main = [t for t in ("visits", "customers") if t in tables]
    if _where(con, "loyalty_flag", main):
        return _result("hidden_variable", True, f"loyalty_flag is in {_where(con, 'loyalty_flag', main)}")
    ft = _where(con, "loyalty_flag", [t for t in tables if t not in main])
    if ft is None:
        return _result("hidden_variable", False, "loyalty_flag is in no table")
    cols = [r[0] for r in con.execute(f"DESCRIBE {ft}").fetchall()]
    ccols = [r[0] for r in con.execute("DESCRIBE customers").fetchall()]
    key = next((c for c in cols if c in ccols), "?")
    cur = con.execute(f"SELECT * FROM {ft} ORDER BY 1 LIMIT 5")
    return _result("hidden_variable", False,
                   f"loyalty_flag is not in visits or customers; it sits in {ft} (join on {key})",
                   cur.fetchall(), [d[0] for d in cur.description])


RUNNERS = {"duplicate_rows": _dup, "unit_mismatch": _units, "dictionary_flip": _coding,
           "confounder": _confounder, "hidden_variable": _hidden}


def _n(v: float) -> str:
    return f"{v:.0f}" if float(v).is_integer() or abs(v) >= 100 else f"{v:.2f}"


def _dictionary(task: Any) -> str:
    if hasattr(task, "dictionary"):
        return task.dictionary
    d = ws._task_dir(task)
    return json.loads((d / "task.json").read_text()).get("dictionary", "")


def run_checks(task: Any, fresh: bool = False) -> list[dict]:
    """Run every trap's check over the task's public tables. One check.result `data` per trap."""
    tt = ws.TaskTables(ws._task_dir(task).resolve()) if fresh else ws.load(task)
    con = tt.cursor()
    names = tt.order
    dictionary = _dictionary(task)
    try:
        return [RUNNERS[t](con, names, dictionary) for t in CHECK_IDS]
    finally:
        con.close()
        if fresh:
            tt.con.close()


def failing(task: Any, fresh: bool = False) -> list[str]:
    return [r["check"] for r in run_checks(task, fresh=fresh) if not r["passed"]]

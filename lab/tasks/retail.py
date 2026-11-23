"""Retail tasks with planted traps, clean twins, careful and careless analyses, and the keep filter.

Re-themed from summit-lab's planted-fault suite (`lab/adapters/planted.py`): the same design,
moved from a clinical cohort to a retail chain. Every task is one claim about a small chain
("Loyalty members spend more per visit than other customers") over up to three tables:

    visits     visit_id, customer_id, store_id, visit_date, items, spend
    customers  customer_id, loyalty_flag, points_balance, joined, home_store
    stores     store_id, region, pos_version, opened

The task may hide one planted trap, or none (a clean twin, where the claim's plain reading is
right):

    duplicate_rows   some visits appear twice under new visit ids (tier 3: whole customers are
                     cloned under new ids, with their visits); a repeat of store, date, items and
                     spend to the cent gives them away.
    unit_mismatch    one region's spend is in cents, not dollars; its median sits ~100x away.
    dictionary_flip  the data dictionary states the loyalty_flag coding the wrong way round;
                     the points column (0 exactly for non-members) shows the true coding
                     (tier 3 tasks keep points in visits, a second table).
    confounder       one POS version inflates spend and members are concentrated at the stores
                     running it; comparing within POS version removes the effect.
    hidden_variable  the loyalty flag is not in visits or customers but in a third table,
                     loyalty_accounts (tier 3: joined through customers.card_id).

Tiers: 1 the trap alone with a strong footprint; 2 the trap plus a decoy (a real oddity that
changes nothing: a busy store, repeat shoppers, a POS shift that is balanced by group); 3 the
trap spans two tables (cloned customers, points in visits, the two-hop join) or, for unit and
confounder traps, a weaker footprint plus a decoy.

The truth is not asserted. `analyse(dir, careful=True)` is one careful analysis, blind to the
trap and the same for every task (read every table, drop repeated visits, check the flag coding
against points, convert a region whose spend sits ~100x away, compare within POS version), and
the generator keeps a draw only when it gives the intended verdict clearly, its notes match the
planted footprint exactly, the careless analysis (visits and customers only, the dictionary
trusted, everything pooled) is clearly wrong on a trapped task and clearly right on a clean one,
and the Bruin-style checks fail for exactly the planted trap.
"""
from __future__ import annotations

import csv
import json
import math
import pathlib
import re
import shutil

import numpy as np
from scipy import stats

TRAPS = ("duplicate_rows", "unit_mismatch", "dictionary_flip", "confounder", "hidden_variable")
SKILLS = TRAPS + ("none",)
TIERS = (1, 2, 3)
HOLDS, FAILS, CANT_TELL = "holds", "fails", "cant_tell"

REGIONS = ("North", "South", "East", "West")
POS_OLD, POS_NEW = "4.2", "5.0"
DATE0 = np.datetime64("2026-08-01")
DAYS = 92

# The draw. Real retail figures could come from N2's Glasser client; these are the fallback.
PARAMS = {
    "visits": (260, 340), "customers": (55, 80), "member_share": (0.40, 0.55),
    "basket_mean": 38.0, "basket_sigma": 0.35, "price_per_item": (5.0, 9.0),
    "effect": 1.35,                 # spend multiplier of the claimed-higher group when the claim holds
    "pos_shift": {1: 1.9, 2: 1.8, 3: 1.7},
    "group_share": {1: 0.85, 2: 0.85, 3: 0.8},   # share of one group at the cents region / new POS
    "duplicate_share": {1: (0.15, 0.18), 2: (0.12, 0.15), 3: (0.12, 0.15)},
    "decoy_store": 1.5, "decoy_pos": 1.5, "decoy_repeats": 6,
}
UNIT_FACTOR = 100.0
UNIT_RATIO_LIMIT = 3.0
ALPHA = 0.05
CAREFUL_P = 1e-4
CARELESS_P = 1e-3
NULL_P = 0.2
MAX_ATTEMPTS = 400

MAIN_TABLES = ("visits", "customers")
DECOYS = {"busy_store": "unit_mismatch", "repeat_shoppers": "duplicate_rows", "pos_balanced": "confounder"}

TITLES = ("Loyalty spend check", "Member basket check", "Program value check", "Loyalty uplift check")
BRIEFS = (
    "Marketing wants this on a board slide on Friday. Check it first.",
    "The loyalty team is asking for a bigger budget on the strength of this. Is it true?",
    "A regional manager quoted this in the weekly call. Check it before it spreads.",
    "Finance will use this to price next year's loyalty perks. Check it.",
)
SECONDS = {1: 300, 2: 360, 3: 420}


# ----------------------------------------------------------------------------- the draw

def _claim(higher: str, rng: np.random.Generator) -> str:
    if higher == "members":
        return str(rng.choice(["Loyalty members spend more per visit than other customers.",
                               "Customers outside the loyalty program spend less per visit than members."]))
    return str(rng.choice(["Customers outside the loyalty program spend more per visit than members.",
                           "Loyalty members spend less per visit than other customers."]))


def _dictionary(stated_code: int, flag_table: str, points_where: str, has_stores: bool, card: bool) -> str:
    other = 1 - stated_code
    lines = ["# Data dictionary", "",
             "- **visits.spend**: basket total in US dollars, tax included.",
             "- **visits.items**: items in the basket.",
             f"- **{flag_table}.loyalty_flag**: {stated_code} = loyalty member, {other} = not a member."]
    if points_where == "visits":
        lines.append("- **visits.points_earned**: loyalty points earned on the visit (0 outside the program).")
    else:
        lines.append(f"- **{points_where}.points_balance**: loyalty points on the account "
                     "(0 for customers outside the program).")
    if card:
        lines.append("- **customers.card_id**: the customer's loyalty card (loyalty_accounts.card_id).")
    if has_stores:
        lines += ["- **stores.region**: sales region.",
                  "- **stores.pos_version**: point-of-sale software that exported the visit."]
    return "\n".join(lines) + "\n"


GLASSER_RECORDED = pathlib.Path(__file__).resolve().parents[1] / "sponsors" / "recorded" / "glasser_retail.json"


def glasser_params(path: pathlib.Path = GLASSER_RECORDED) -> tuple[dict, dict]:
    """PARAMS calibrated with the retail numbers N2's Glasser client recorded (item prices, basket),
    and where they came from. Falls back to the fixed PARAMS when nothing is recorded."""
    try:
        rec = json.loads(path.read_text())
        medians = sorted(float(x["median"]) for x in rec.get("prices", []) if x.get("median"))
        if len(medians) < 2:
            raise ValueError("too few prices")
        params = {**PARAMS, "price_per_item": (round(medians[0], 2), round(float(np.median(medians)), 2))}
        basket = rec.get("basket") or {}
        if basket.get("avgBasketUsd"):
            params["basket_mean"] = float(basket["avgBasketUsd"])
        return params, {"source": "glasser (recorded)", "sources": rec.get("sources", []),
                        "basket": basket.get("source")}
    except (OSError, ValueError, KeyError, TypeError):
        return dict(PARAMS), {"source": "fixed"}


def draw(trap: str, truth: str, tier: int, rng: np.random.Generator, params: dict | None = None) -> dict:
    """One task's tables, claim, dictionary and planted footprint, from one random draw."""
    P = params or PARAMS
    decoy = None
    if tier >= 2 and not (tier == 3 and trap in ("duplicate_rows", "dictionary_flip", "hidden_variable")):
        choices = [d for d, t in DECOYS.items() if t != trap]
        decoy = str(rng.choice(choices))
    higher = str(rng.choice(["members", "others"]))
    n_v = int(rng.integers(P["visits"][0], P["visits"][1] + 1))
    n_c = int(rng.integers(P["customers"][0], P["customers"][1] + 1))
    hidden = trap == "hidden_variable"
    card = hidden and tier == 3
    # Tier 3 keeps loyalty points in visits for every trap, so the flag and its companion
    # sit in two tables (and points_earned is no tell for the dictionary flip).
    points_where = "loyalty_accounts" if hidden else ("visits" if tier == 3 else "customers")

    # Stores: three per region, both POS versions in every region.
    region_of = np.repeat(np.arange(4), 3)
    pos_new = np.zeros(12, dtype=bool)
    for r in range(4):
        idx = np.flatnonzero(region_of == r)
        k_new = int(rng.choice([1, 2]))
        pos_new[rng.permutation(idx)[:k_new]] = True
    perm = rng.permutation(12)
    region_of, pos_new = region_of[perm], pos_new[perm]
    opened = rng.integers(2004, 2025, 12)
    store_factor = np.exp(rng.normal(0, 0.08, 12))
    if decoy == "busy_store":
        store_factor[int(rng.integers(12))] *= P["decoy_store"]
    pos_factor = np.ones(12)
    if trap == "confounder":
        pos_factor[pos_new] = P["pos_shift"][tier]
    elif decoy == "pos_balanced":
        pos_factor[pos_new] = P["decoy_pos"]

    # Which group each visit belongs to. x = the group the claim says spends more.
    share_x = np.full(12, 0.5)
    cents_region = None
    g = P["group_share"][tier]
    if trap == "confounder":
        hi = g if truth == FAILS else 1 - g
        share_x = np.where(pos_new, hi, 1 - hi)
    if trap == "unit_mismatch":
        cents_region = int(rng.integers(4))
        hi = g if truth == FAILS else 1 - g
        share_x = np.where(region_of == cents_region, hi, 0.5)
    store = rng.integers(0, 12, n_v)
    x = rng.random(n_v) < share_x[store]

    if truth == HOLDS:
        mult = np.where(x, P["effect"], 1.0)
    elif trap == "dictionary_flip" or (hidden and rng.random() < 0.5):
        mult = np.where(x, 1 / P["effect"], 1.0)
    else:
        mult = np.ones(n_v)
    spend = (P["basket_mean"] * mult * pos_factor[store] * store_factor[store]
             * np.exp(rng.normal(0, P["basket_sigma"], n_v)))
    spend = np.round(np.maximum(spend, 2.0), 2)
    items = np.maximum(1, np.round(spend / rng.uniform(*P["price_per_item"], n_v))).astype(int)
    day = rng.integers(0, DAYS, n_v)

    # Customers: members and others; x visits come from the x pool.
    n_m = int(round(n_c * rng.uniform(*P["member_share"])))
    member = np.zeros(n_c, dtype=bool)
    member[rng.permutation(n_c)[:n_m]] = True
    x_is_member = higher == "members"
    pool_x = np.flatnonzero(member == x_is_member)
    pool_o = np.flatnonzero(member != x_is_member)
    cust = np.where(x, rng.choice(pool_x, n_v), rng.choice(pool_o, n_v))

    rows = [{"c": int(cust[i]), "s": int(store[i]), "d": int(day[i]), "items": int(items[i]),
             "spend": float(spend[i])} for i in range(n_v)]

    footprint: dict = {}
    if decoy == "repeat_shoppers":
        for i in rng.choice(n_v, P["decoy_repeats"], replace=False):
            r = dict(rows[i])
            r["d"] = int((r["d"] + rng.integers(7, 22)) % DAYS)
            rows.append(r)

    clones: dict[int, int] = {}
    if trap == "duplicate_rows":
        k = int(round(n_v * rng.uniform(*P["duplicate_share"][tier])))
        y = np.array([r["spend"] for r in rows[:n_v]])
        xi, oi = np.flatnonzero(x), np.flatnonzero(~x)
        top = xi[np.argsort(-y[xi])[:k]]
        bottom = oi[np.argsort(y[oi])[:k]]
        for i in np.concatenate([top, bottom]):
            r = dict(rows[int(i)])
            if tier == 3:
                if r["c"] not in clones:
                    clones[r["c"]] = n_c + len(clones)
                r["c"] = clones[r["c"]]
            rows.append(r)
        footprint = {"duplicated_visits": 2 * k, "cloned_customers": len(clones)}

    # Customer attributes (clones copy their source).
    stated = int(rng.integers(0, 2))
    actual = 1 - stated if trap == "dictionary_flip" else stated
    if trap == "dictionary_flip":
        footprint = {"stated_member_code": stated, "actual_member_code": actual}
    src = list(range(n_c)) + [c for c, _ in sorted(clones.items(), key=lambda kv: kv[1])]
    n_all = len(src)
    points = np.where(member, rng.integers(40, 4000, n_c), 0)
    joined = DATE0 - rng.integers(30, 2400, n_c).astype("timedelta64[D]")
    visit_counts = np.zeros((n_all, 12), dtype=int)
    for r in rows:
        visit_counts[r["c"], r["s"]] += 1
    home = [int(np.argmax(visit_counts[c])) if visit_counts[c].any() else int(rng.integers(12))
            for c in range(n_all)]
    cid_num = rng.permutation(np.arange(1, n_all + 1))
    cids = [f"c{int(n):03d}" for n in cid_num]
    cards = [f"k{int(n)}" for n in rng.choice(np.arange(1000, 10000), n_all, replace=False)]
    sids = [f"st{i + 1:02d}" for i in range(12)]

    # Visits in date order; duplicates sit near their originals.
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["d"], rng.random()))
    visit_cols = ["visit_id", "customer_id", "store_id", "visit_date", "items", "spend"]
    if points_where == "visits":
        visit_cols.insert(5, "points_earned")
    visits = []
    for n, i in enumerate(order):
        r = rows[i]
        sp = r["spend"]
        is_member = bool(member[src[r["c"]]])
        if cents_region is not None and region_of[r["s"]] == cents_region:
            sp_text = f"{round(sp * UNIT_FACTOR)}"
        else:
            sp_text = f"{sp:.2f}"
        row = [f"v{n + 1:04d}", cids[r["c"]], sids[r["s"]], str(DATE0 + np.timedelta64(r["d"], "D")), str(r["items"])]
        if points_where == "visits":
            row.append(str(int(math.floor(sp)) if is_member else 0))
        row.append(sp_text)
        visits.append(row)
    if cents_region is not None:
        footprint = {"cents_region": REGIONS[cents_region], "factor": UNIT_FACTOR}

    flag = [actual if member[src[c]] else 1 - actual for c in range(n_all)]
    cust_cols = ["customer_id"]
    if not hidden:
        cust_cols += ["loyalty_flag"] + (["points_balance"] if points_where == "customers" else [])
    if card:
        cust_cols.append("card_id")
    cust_cols += ["joined", "home_store"]
    customers = []
    for c in range(n_all):
        row = [cids[c]]
        if not hidden:
            row.append(str(flag[c]))
            if points_where == "customers":
                row.append(str(int(points[src[c]])))
        if card:
            row.append(cards[c])
        row += [str(joined[src[c]]), sids[home[c]]]
        customers.append(row)

    tables = {
        "visits": {"about": "One row per store visit", "key": "visit_id", "columns": visit_cols, "rows": visits},
        "customers": {"about": "One row per customer", "key": "customer_id", "columns": cust_cols,
                      "rows": customers},
    }
    if hidden:
        key_col = "card_id" if card else "customer_id"
        la = [[cards[c] if card else cids[c], str(flag[c]), str(int(points[src[c]])),
               str(joined[src[c]] + np.timedelta64(int(rng.integers(0, 30)), "D"))] for c in range(n_all)]
        tables["loyalty_accounts"] = {"about": "One row per loyalty account", "key": key_col,
                                      "columns": [key_col, "loyalty_flag", "points_balance", "enrolled"],
                                      "rows": la}
        footprint = {"flag_table": "loyalty_accounts", "join": key_col}
    else:
        tables["stores"] = {"about": "One row per store", "key": "store_id",
                            "columns": ["store_id", "region", "pos_version", "opened"],
                            "rows": [[sids[s], REGIONS[region_of[s]], POS_NEW if pos_new[s] else POS_OLD,
                                      str(opened[s])] for s in range(12)]}
    if trap == "confounder":
        footprint = {"pos_version": POS_NEW, "shift": P["pos_shift"][tier],
                     "higher_group_share_at_new_pos": float(share_x[pos_new][0])}
    if decoy:
        footprint = {**footprint, "decoy": decoy}

    flag_table = "loyalty_accounts" if hidden else "customers"
    expected = {"flag_table": flag_table,
                "duplicates_removed": footprint.get("duplicated_visits", 0),
                "coding_reversed": trap == "dictionary_flip",
                "regions_converted": [REGIONS[cents_region]] if cents_region is not None else []}
    return {"trap": trap, "truth": truth, "tier": tier, "decoy": decoy, "higher": higher,
            "claim": _claim(higher, rng), "title": str(rng.choice(TITLES)), "brief": str(rng.choice(BRIEFS)),
            "dictionary": _dictionary(stated, flag_table, points_where, not hidden, card),
            "tables": tables, "footprint": footprint, "expected_notes": expected}


# ----------------------------------------------------------------------------- writing and reading

_ABOUT = {
    "visit_id": ("text", "One store visit"), "customer_id": ("text", "Customer"),
    "store_id": ("text", "Store"), "visit_date": ("date", "Day of the visit"),
    "items": ("int", "Items in the basket"), "spend": ("real", "Basket total in dollars"),
    "points_earned": ("int", "Loyalty points earned on the visit"),
    "loyalty_flag": ("int", "Loyalty program flag (coding in the data dictionary)"),
    "points_balance": ("int", "Loyalty points on the account"), "joined": ("date", "First purchase"),
    "home_store": ("text", "Store they visit most"), "card_id": ("text", "Loyalty card"),
    "region": ("text", "Sales region"), "pos_version": ("text", "Point-of-sale software version"),
    "opened": ("int", "Year the store opened"), "enrolled": ("date", "Day the account opened"),
}


def write_public(folder: pathlib.Path, d: dict) -> None:
    """The public files: task.json (contract shape, no id), tables.json and one CSV per table."""
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    meta = []
    for name, t in d["tables"].items():
        with open(folder / f"{name}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(t["columns"])
            w.writerows(t["rows"])
        cols = []
        for c in t["columns"]:
            typ, about = _ABOUT[c]
            if name == "visits" and c == "customer_id":
                about = "Who visited (customers.customer_id)"
            if name == "visits" and c == "store_id":
                about = "Where (stores.store_id)"
            cols.append({"name": c, "type": typ, "about": about})
        meta.append({"name": name, "about": t["about"], "rowCount": len(t["rows"]), "key": t["key"],
                     "columns": cols})
    (folder / "tables.json").write_text(json.dumps(meta, indent=2) + "\n")
    task = {"id": None, "title": d["title"], "seconds": SECONDS[d["tier"]], "tier": d["tier"],
            "claim": d["claim"], "brief": d["brief"], "dictionary": d["dictionary"]}
    (folder / "task.json").write_text(json.dumps(task, indent=2) + "\n")


def read_tables(folder: pathlib.Path) -> dict[str, list[dict]]:
    meta = json.loads((folder / "tables.json").read_text())
    out = {}
    for t in meta:
        with open(folder / f"{t['name']}.csv", newline="") as f:
            out[t["name"]] = list(csv.DictReader(f))
    return out


def stated_member_code(dictionary: str) -> int | None:
    m = re.search(r"loyalty_flag\*\*:[^\n]*?\b([01])\s*=\s*loyalty member", dictionary)
    return int(m.group(1)) if m else None


# ----------------------------------------------------------------------------- the analyses

def _ols(y: np.ndarray, x: np.ndarray, groups: np.ndarray | None) -> tuple[float, float]:
    """Coefficient of x and its two-sided p in y ~ x + group fixed effects (summit-lab's _ols)."""
    columns = [np.ones(len(y)), x.astype(float)]
    if groups is not None:
        columns += [(groups == b).astype(float) for b in sorted(set(groups))[1:]]
    design = np.column_stack(columns)
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    resid = y - design @ coef
    df = len(y) - design.shape[1]
    cov = (resid @ resid / df) * np.linalg.inv(design.T @ design)
    t = coef[1] / math.sqrt(cov[1, 1])
    return float(coef[1]), float(2 * stats.t.sf(abs(t), df))


def _flag_lookup(tables: dict[str, list[dict]]) -> tuple[str | None, dict, dict]:
    """Where loyalty_flag lives, and customer_id -> flag / points, joining through a card if needed."""
    for name, rows in tables.items():
        if rows and "loyalty_flag" in rows[0]:
            break
    else:
        return None, {}, {}
    rows = tables[name]
    if "customer_id" in rows[0]:
        flag = {r["customer_id"]: int(r["loyalty_flag"]) for r in rows}
        pts = {r["customer_id"]: float(r["points_balance"]) for r in rows if "points_balance" in r}
    else:
        if "customers" not in tables or not tables["customers"]:
            return None, {}, {}
        key = next((k for k in rows[0] if k in tables["customers"][0]), None)
        if key is None:
            return None, {}, {}
        by_key = {r[key]: r for r in rows}
        flag, pts = {}, {}
        for c in tables["customers"]:
            r = by_key.get(c.get(key))
            if r is not None:
                flag[c["customer_id"]] = int(r["loyalty_flag"])
                if "points_balance" in r:
                    pts[c["customer_id"]] = float(r["points_balance"])
    return name, flag, pts


def analyse(folder: pathlib.Path, careful: bool = True) -> dict:
    """Test the task's claim on its public files. Returns {verdict, estimate, p, n, means, notes}.

    careful=True reads every table, drops repeated visits (same store, date, items and spend),
    checks the flag coding against points, converts a region whose median spend sits ~100x from
    the others', and compares groups within POS version. careful=False reads visits and customers
    only, trusts the dictionary and pools everything (Welch t-test)."""
    folder = pathlib.Path(folder)
    task = json.loads((folder / "task.json").read_text())
    tables = read_tables(folder)
    if not careful:
        tables = {n: t for n, t in tables.items() if n in MAIN_TABLES}
    flag_table, flag, pts = _flag_lookup(tables)
    out = {"verdict": CANT_TELL, "estimate": None, "p": None, "n": 0, "means": None, "notes": {}}
    if flag_table is None or "visits" not in tables:
        return out
    notes = {"flag_table": flag_table}
    visits = tables["visits"]
    if careful:
        seen, kept = set(), []
        for r in visits:
            k = (r["store_id"], r["visit_date"], r["items"], float(r["spend"]))
            if k not in seen:
                seen.add(k)
                kept.append(r)
        notes["duplicates_removed"] = len(visits) - len(kept)
        visits = kept
    code = stated_member_code(task["dictionary"])
    if careful:
        if pts:
            coded = [c for c, f in flag.items() if f == code]
            share = np.mean([pts.get(c, 0) > 0 for c in coded]) if coded else 1.0
        else:
            coded = [r for r in visits if flag.get(r["customer_id"]) == code]
            share = np.mean([float(r.get("points_earned", 0)) > 0 for r in coded]) if coded else 1.0
        notes["coding_reversed"] = bool(share < 0.5)
        if notes["coding_reversed"]:
            code = 1 - code
    visits = [r for r in visits if r["customer_id"] in flag]
    member = np.array([flag[r["customer_id"]] == code for r in visits])
    claim = task["claim"]
    members_higher = ("Loyalty members spend more" in claim) or ("program spend less" in claim)
    x = member if members_higher else ~member
    y = np.array([float(r["spend"]) for r in visits])
    pos = None
    if careful:
        notes["regions_converted"] = []
        stores = {r["store_id"]: r for r in tables.get("stores", [])}
        if stores:
            region = np.array([stores[r["store_id"]]["region"] for r in visits])
            med = {g: float(np.median(y[region == g])) for g in sorted(set(region))}
            ref = float(np.median(list(med.values())))
            for g, m in med.items():
                if m > 0 and ref > 0 and abs(math.log(m / ref)) > math.log(UNIT_RATIO_LIMIT):
                    y[region == g] = y[region == g] / UNIT_FACTOR if m > ref else y[region == g] * UNIT_FACTOR
                    notes["regions_converted"].append(g)
            pos = np.array([stores[r["store_id"]]["pos_version"] for r in visits])
        estimate, p = _ols(y, x, pos)
    else:
        estimate = float(y[x].mean() - y[~x].mean())
        p = float(stats.ttest_ind(y[x], y[~x], equal_var=False).pvalue)
    verdict = HOLDS if estimate > 0 and p < ALPHA else FAILS
    means = {"members": round(float(y[member].mean()), 2), "others": round(float(y[~member].mean()), 2)}
    return {"verdict": verdict, "estimate": estimate, "p": p, "n": len(visits), "means": means,
            "notes": notes}


def clear(result: dict, verdict: str, strict_p: float) -> bool:
    """Whether an analysis gives `verdict` with room to spare."""
    if verdict == CANT_TELL or result["verdict"] == CANT_TELL:
        return result["verdict"] == verdict
    if verdict == HOLDS:
        return result["estimate"] > 0 and result["p"] < strict_p
    return result["estimate"] <= 0 or result["p"] > NULL_P


# ----------------------------------------------------------------------------- answers in words

def careful_note(r: dict, trap: str, fp: dict) -> str:
    steps = []
    n = r["notes"]
    if n.get("flag_table") == "loyalty_accounts":
        steps.append("the loyalty flag is in loyalty_accounts, so I joined it in")
    if n.get("duplicates_removed"):
        steps.append(f"dropped {n['duplicates_removed']} visits that repeat another visit's store, "
                     "date, items and spend exactly")
    if n.get("coding_reversed"):
        steps.append("the dictionary has the flag backwards: the rows it calls members have no points")
    if n.get("regions_converted"):
        steps.append(f"{', '.join(n['regions_converted'])} spend is in cents, so I divided it by 100")
    if trap == "confounder":
        steps.append(f"POS {fp.get('pos_version', POS_NEW)} inflates spend and the groups split unevenly "
                     "across POS versions, so I compared within POS version")
    m = r["means"]
    lead = ("; ".join(steps) + ". ") if steps else "Nothing in the data needed fixing. "
    lead = lead[0].upper() + lead[1:]
    word = "holds" if r["verdict"] == HOLDS else "fails"
    within = " within POS version" if n.get("flag_table") != "loyalty_accounts" else ""
    return (f"{lead}Members average ${m['members']:.2f} per visit and others ${m['others']:.2f} overall; "
            f"compared{within}, the gap in the claim's direction is {r['estimate']:+.2f} dollars "
            f"(p = {r['p']:.2g}). "
            f"The claim {word}.")


def careless_note(r: dict) -> str:
    if r["verdict"] == CANT_TELL:
        return "There's no loyalty column in visits or customers, so the claim can't be checked."
    m = r["means"]
    word = "holds" if r["verdict"] == HOLDS else "fails"
    return (f"I averaged spend over all {r['n']} visits: members ${m['members']:.2f}, others "
            f"${m['others']:.2f}. The claim {word}.")


SUSPICION = {
    "unit_mismatch": "one store's baskets look far too big; probably a unit problem",
    "duplicate_rows": "some customers buy the same basket twice; probably duplicated rows",
    "confounder": "spend jumps on the new POS; that has to be skewing it",
    "dictionary_flip": "I don't trust the loyalty flag coding",
}


def matters(trap: str, d: dict) -> list[str]:
    """table.column names a query should touch to catch this task's trap (the struggle meter)."""
    flag_table = d["expected_notes"]["flag_table"]
    base = ["visits.spend", f"{flag_table}.loyalty_flag"]
    extra = {
        "duplicate_rows": ["visits.store_id", "visits.visit_date", "visits.items"],
        "unit_mismatch": ["stores.region"],
        "dictionary_flip": ["visits.points_earned" if "points_earned" in d["tables"]["visits"]["columns"]
                            else f"{flag_table}.points_balance"],
        "confounder": ["stores.pos_version"],
        "hidden_variable": [f"loyalty_accounts.{d['footprint'].get('join', 'customer_id')}"],
        "none": [],
    }[trap]
    return base + extra


def hints(trap: str, d: dict) -> list[str]:
    """Sam's hint ladder, levels 1 to 3. Level 1 never names the trap."""
    fp = d["footprint"]
    return {
        "duplicate_rows": [
            "Before averaging, ask whether every row is a separate visit.",
            "Group visits by store, date, items and spend and look for counts above 1.",
            f"{fp.get('duplicated_visits', 'Many')} visits repeat another visit exactly under a new visit id; "
            "drop the repeats, then compare.",
        ],
        "unit_mismatch": [
            "Look at the range of spend before you trust an average.",
            "Compare min, median and max spend by region (join visits to stores).",
            f"{fp.get('cents_region', 'One region')}'s spend is about 100 times the others': it is in cents.",
        ],
        "dictionary_flip": [
            "Check that the loyalty flag means what the dictionary says.",
            "Cross the loyalty flag with the points column: who has points?",
            "The rows the dictionary calls members have no points; the coding is backwards.",
        ],
        "confounder": [
            "Ask what else differs between the two groups besides loyalty.",
            "Break spend and the loyalty mix down by stores.pos_version.",
            f"POS {fp.get('pos_version', '5.0')} inflates spend and the groups split unevenly across POS "
            "versions; compare within each version.",
        ],
        "hidden_variable": [
            "List every table before deciding the data can't answer this.",
            "The loyalty flag is not in visits or customers. Is there another table?",
            f"loyalty_accounts holds the flag; join it through {fp.get('join', 'customer_id')}.",
        ],
        "none": [
            "Check the usual suspects, then trust what survives.",
            "Repeats, units, coding, POS mix and missing columns all look fine here.",
            "Nothing is planted in this one: the plain comparison is the right one.",
        ],
    }[trap]

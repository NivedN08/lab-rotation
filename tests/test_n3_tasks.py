import json
import random

import pytest

from lab import workspace_sql as ws
from lab.tasks import bank, retail as R
from lab.tasks.checks import CHECK_IDS, run_checks


@pytest.fixture(scope="module")
def small_bank(tmp_path_factory):
    root = tmp_path_factory.mktemp("bank")
    old = (bank.ROOT, bank.PUBLIC, bank.SEALED, bank._INDEX)
    bank.build(per=2, seed=7, root=root, log=lambda *_: None)
    bank.ROOT, bank.PUBLIC, bank.SEALED, bank._INDEX = root, root / "public", root / "sealed", None
    yield root
    bank.ROOT, bank.PUBLIC, bank.SEALED, bank._INDEX = old


def all_tasks():
    return [bank.load(i) for i in bank.ids()]


def test_bank_covers_every_skill_and_tier(small_bank):
    for skill in R.SKILLS:
        for tier in R.TIERS:
            assert len(bank.ids(skill, tier)) == 2, (skill, tier)


def test_keep_filter_holds_on_every_task(small_bank):
    for t in all_tasks():
        k = t.key
        careful = R.analyse(t.public_dir, careful=True)
        careless = R.analyse(t.public_dir, careful=False)
        assert careful["verdict"] == k["correctVerdict"]
        assert R.clear(careful, k["correctVerdict"], R.CAREFUL_P)
        if t.skill == "none":
            # the plain reading is right; Riley's suspicion must not score
            assert careless["verdict"] == k["correctVerdict"]
            assert k["careless"]["verdict"] != k["correctVerdict"] and k["careless"]["trap"] != "none"
        else:
            assert careless["verdict"] != k["correctVerdict"]
            assert k["careless"]["verdict"] == careless["verdict"] and k["careless"]["trap"] == "none"
        assert k["careful"]["verdict"] == k["correctVerdict"] and k["careful"]["trap"] == t.skill


def test_checks_fail_for_exactly_the_planted_trap(small_bank):
    for t in all_tasks():
        failed = [c["check"] for c in run_checks(t) if not c["passed"]]
        assert failed == ([CHECK_IDS[t.skill]] if t.skill != "none" else []), (t.id, t.skill)
        assert t.key["failingCheck"] == (failed[0] if failed else None)


def test_check_result_shape(small_bank):
    t = bank.pick("unit_mismatch", 1)
    res = {c["check"]: c for c in run_checks(t)}
    bad = res["unit_mismatch.spend_range_by_region"]
    assert bad["passed"] is False and bad["trap"] == "unit_mismatch"
    assert bad["detail"] and 1 <= len(bad["rows"]) <= 5
    json.dumps(list(res.values()))


def test_public_files_hide_the_key(small_bank):
    words = ("duplicate", "cents", "trap", "confound", "hidden", "flip", "backwards", "decoy")
    for t in all_tasks():
        files = {p.name for p in t.public_dir.iterdir()}
        assert "task.json" in files and "tables.json" in files
        assert not any("key" in f or "sealed" in f for f in files)
        pub = t.public("t2")
        assert set(pub) == {"id", "title", "brief", "seconds", "claim", "tier", "dictionary"}
        assert pub["id"] == "t2" and pub["tier"] == t.tier
        text = json.dumps(pub).lower() + (t.public_dir / "tables.json").read_text().lower()
        assert not any(w in text for w in words), t.id
        assert t.id not in text


def test_tables_shape_and_limits(small_bank):
    for t in all_tasks():
        info = ws.tables(t)
        assert 2 <= len(info) <= 3
        assert sum(x["rowCount"] for x in info) < 600
        for x in info:
            assert all(c["type"] in ("text", "int", "real", "date") for c in x["columns"])


def test_sql_box_runs_on_bank_task(small_bank):
    t = bank.pick("dictionary_flip", 1)
    r = ws.run_query(t, "SELECT loyalty_flag, count(*) FROM customers GROUP BY 1 ORDER BY 1")
    assert "error" not in r and len(r["rows"]) == 2


def test_pick_prefers_unseen_then_nearest_tier(small_bank):
    rng = random.Random(1)
    a = bank.pick("confounder", 2, rng=rng)
    b = bank.pick("confounder", 2, seen=[a.id], rng=rng)
    assert a.id != b.id and b.tier == 2
    c = bank.pick("confounder", 2, seen=[a.id, b.id], rng=rng)
    assert c.tier in (1, 3) and c.skill == "confounder"
    every = bank.ids("confounder")
    d = bank.pick("confounder", 2, seen=every, rng=rng)
    assert d.skill == "confounder"
    with pytest.raises(KeyError):
        bank.load("nope")


def test_generation_is_deterministic(tmp_path):
    a = bank.generate_one("unit_mismatch", 2, R.FAILS, 11, 0, tmp_path / "a")
    b = bank.generate_one("unit_mismatch", 2, R.FAILS, 11, 0, tmp_path / "b")
    assert a == b
    assert (tmp_path / "a" / "visits.csv").read_text() == (tmp_path / "b" / "visits.csv").read_text()


def test_clear_rule():
    assert R.clear({"verdict": "holds", "estimate": 3.0, "p": 1e-6}, "holds", 1e-4)
    assert not R.clear({"verdict": "holds", "estimate": 3.0, "p": 1e-3}, "holds", 1e-4)
    assert R.clear({"verdict": "fails", "estimate": -1.0, "p": 0.01}, "fails", 1e-4)
    assert not R.clear({"verdict": "fails", "estimate": 1.0, "p": 0.1}, "fails", 1e-4)
    assert R.clear({"verdict": "cant_tell", "estimate": None, "p": None}, "cant_tell", 1e-4)


def test_careless_misses_each_trap(tmp_path):
    """Each trap really bites: without it (same draw), the careless reading would be right."""
    for trap in R.TRAPS:
        truth = R.FAILS if trap == "duplicate_rows" else R.HOLDS
        k = bank.generate_one(trap, 1, truth, 5, 0, tmp_path / trap)
        assert k["careless"]["verdict"] != truth
        assert k["careful"]["verdict"] == truth


@pytest.mark.skipif(__import__("shutil").which("bruin") is None, reason="bruin not installed")
def test_bruin_agrees_with_python_checks(small_bank):
    for skill in R.SKILLS:
        t = bank.pick(skill, 3, rng=random.Random(0))
        res = run_checks(t, bruin=True)
        for r in res:
            assert "bruinError" not in r, r
            assert r["bruinPassed"] == r["passed"], (skill, r["check"])


def test_glasser_params_calibrate_prices(tmp_path):
    rec = {"prices": [{"item": "a", "median": 5.69}, {"item": "b", "median": 3.92},
                      {"item": "c", "median": 9.38}, {"item": "d", "median": 15.1}],
           "basket": {"avgBasketUsd": 38.0, "source": "fixed value"}, "sources": ["https://example.test/run"]}
    p = tmp_path / "glasser_retail.json"
    p.write_text(json.dumps(rec))
    params, src = R.glasser_params(p)
    assert params["price_per_item"] == (3.92, 7.54) and params["basket_mean"] == 38.0
    assert src["source"] == "glasser (recorded)"
    params, src = R.glasser_params(tmp_path / "missing.json")
    assert params == R.PARAMS and src == {"source": "fixed"}
    k = bank.generate_one("confounder", 1, R.HOLDS, 3, 0, tmp_path / "t", R.glasser_params(p)[0])
    assert k["careful"]["verdict"] == R.HOLDS


def test_key_has_matters_and_hints(small_bank):
    for t in all_tasks():
        cols = {(x["name"], c["name"]) for x in ws.tables(t) for c in x["columns"]}
        for m in t.key["matters"]:
            assert tuple(m.split(".")) in cols, (t.skill, m)
        assert len(t.key["hints"]) == 3
        assert t.skill not in t.key["hints"][0] and "cents" not in t.key["hints"][0]


def test_schema_is_no_tell_within_a_tier(small_bank):
    """Within a tier, every task but hidden_variable has the same tables and columns."""
    for tier in R.TIERS:
        shapes = {}
        for t in all_tasks():
            if t.tier == tier and t.skill != "hidden_variable":
                shapes.setdefault(json.dumps([(x["name"], [c["name"] for c in x["columns"]])
                                              for x in ws.tables(t)]), []).append(t.skill)
        assert len(shapes) == 1, (tier, shapes)

import random

import pytest

from lab import learner as L
from lab.learner import bkt, model


@pytest.fixture(autouse=True)
def tmp_learners(tmp_path, monkeypatch):
    monkeypatch.setattr(model, "DIR", tmp_path / "learners")


def test_bkt_matches_the_mock_session():
    # contract/mock_session.jsonl: unit mix-up mastery 0.15 -> 0.61 after one correct answer
    assert round(bkt.update(0.15, True, "unit_mismatch"), 2) == 0.61


def test_bkt_direction_and_bounds():
    p = 0.15
    up = bkt.update(p, True, "confounder")
    down = bkt.update(p, False, "confounder")
    assert down < up
    assert 0 < down < 1 and 0 < up < 1
    seq = 0.15
    for _ in range(10):
        seq = bkt.update(seq, True, "confounder")
    assert seq > 0.95
    # learning transition means a wrong answer from a low prior still nudges up a little
    assert bkt.update(0.15, False, "confounder") >= 0.15 * 0.9


def test_mastery_shape_new_learner():
    m = L.mastery("new-person")
    assert [t["trap"] for t in m["traps"]] == list(bkt.SKILLS)
    assert all(t["score"] == 0.15 and t["attempts"] == 0 for t in m["traps"])


def test_record_returns_mastery_updates_and_persists():
    ups = L.record("ana", "unit_mismatch", True, tier=1, session="s1", task="t1")
    assert ups == [{"trap": "unit_mismatch", "from": 0.15, "to": 0.61, "correct": True, "attempts": 1}]
    ups = L.record("ana", "unit_mismatch", score=0.2)
    assert ups[0]["from"] == 0.61 and ups[0]["to"] < 0.61 and ups[0]["correct"] is False
    m = {t["trap"]: t for t in L.mastery("ana")["traps"]}
    assert m["unit_mismatch"]["attempts"] == 2
    assert m["none"]["attempts"] == 0
    assert len(L.history("ana")) == 2
    with pytest.raises(ValueError):
        L.record("ana", "made_up", True)
    with pytest.raises(ValueError):
        L.record("ana", "none")


def test_learner_ids_are_sanitised():
    L.record("../../etc/passwd", "none", True)
    assert all(p.parent == model.DIR for p in model.DIR.iterdir())


def test_bandit_leans_to_low_mastery():
    for _ in range(4):
        for s in bkt.SKILLS:
            if s != "hidden_variable":
                L.record("bo", s, True)
        L.record("bo", "hidden_variable", False)
    rng = random.Random(3)
    picks = [L.pick_next("bo", tier=1, rng=rng)["skill"] for _ in range(200)]
    assert picks.count("hidden_variable") > 120


def test_pick_next_shape_and_reasons():
    p = L.pick_next("cy", rng=random.Random(0))
    assert p["skill"] in bkt.SKILLS and p["tier"] == 1 and p["fallback"] is False
    assert set(p["bandit"]) == set(bkt.SKILLS)
    assert all({"mean", "sample"} == set(v) for v in p["bandit"].values())
    assert p["task"].skill == p["skill"] and p["bankId"] == p["task"].id
    # the public reason never names the trap
    for words in bkt.LABELS.values():
        assert words not in p["reason"]
    for s in bkt.SKILLS:
        assert s not in p["reason"]
    assert bkt.LABELS[p["skill"]] in p["pickReason"]


def test_tier_follows_mastery_unless_forced():
    for _ in range(6):
        L.record("di", "confounder", True)
    p = L.pick_next("di", avoid=[s for s in bkt.SKILLS if s != "confounder"], rng=random.Random(1))
    assert p["skill"] == "confounder" and p["tier"] == 3
    p = L.pick_next("di", tier=2, avoid=[s for s in bkt.SKILLS if s != "confounder"], rng=random.Random(1))
    assert p["tier"] == 2


def test_avoid_and_seen():
    rng = random.Random(5)
    p1 = L.pick_next("ed", tier=1, rng=rng)
    p2 = L.pick_next("ed", tier=1, avoid=[p1["skill"]], seen=[p1["bankId"]], rng=rng)
    assert p2["skill"] != p1["skill"] and p2["bankId"] != p1["bankId"]


def test_rules_fallback():
    L.record("fa", "duplicate_rows", True)
    p = L.pick_next("fa", use_bandit=False, rng=random.Random(0))
    assert p["fallback"] is True and p["bandit"] is None
    assert p["skill"] == "unit_mismatch"  # lowest mastery, fewest attempts, fixed order
    assert "fallback" in p["reason"]


def test_refresh_flattens_the_mock_session(tmp_path):
    from pathlib import Path

    from lab.learner import refresh
    root = Path(__file__).resolve().parent.parent
    out = refresh.stage(sessions=root / "contract", bench=tmp_path / "missing.csv", dest=tmp_path / "learn")
    assert out == {"sessions": 1, "events": 68, "bench": 0}
    import csv
    rows = list(csv.DictReader(open(tmp_path / "learn" / "session_events.csv")))
    end = [r for r in rows if r["k"] == "task.end"]
    assert len(end) == 1 and end[0]["trap"] == "unit_mismatch" and end[0]["learner"] == "guest"
    assert (tmp_path / "learn" / "bench.csv").read_text().startswith("split,dimension,system")
    # the batch replay (Bruin's bkt_mastery) gives the same mastery as the live model
    st = bkt.trace([{"skill": r["trap"], "correct": float(r["score"]) >= bkt.CORRECT_SCORE} for r in end])
    assert round(st["unit_mismatch"]["score"], 2) == 0.61

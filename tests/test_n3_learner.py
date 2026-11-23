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
    """Counts come from the mock file itself, so the test holds when N1 regenerates it."""
    import csv
    import json
    import shutil
    from pathlib import Path

    from lab.learner import refresh
    mock = Path(__file__).resolve().parent.parent / "contract" / "mock_session.jsonl"
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    shutil.copy(mock, sessions / "mock-1.jsonl")
    raw = [json.loads(line) for line in mock.read_text().splitlines() if line.strip()]
    start = next(e for e in raw if e["k"] == "session.start")
    ends = [e for e in raw if e["k"] == "task.end"]
    assert ends, "the mock session should grade at least one task"

    out = refresh.stage(sessions=sessions, bench=tmp_path / "missing.csv", dest=tmp_path / "learn")
    assert out == {"sessions": 1, "events": len(raw), "bench": 0}
    with open(tmp_path / "learn" / "session_events.csv", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == refresh.EVENT_COLUMNS
        rows = list(reader)
    assert [int(r["seq"]) for r in rows] == [e["seq"] for e in raw]
    flat_ends = [r for r in rows if r["k"] == "task.end"]
    assert [(r["trap"], float(r["score"])) for r in flat_ends] == \
        [(e["data"]["trap"], e["data"]["score"]) for e in ends]
    assert all(r["learner"] == start["data"]["learner"] and r["session_id"] == "mock-1" for r in flat_ends)
    assert (tmp_path / "learn" / "bench.csv").read_text().startswith("split,dimension,system")

    # the batch replay (Bruin's bkt_mastery) gives the same mastery as the live model
    batch = bkt.trace([{"skill": r["trap"], "correct": float(r["score"]) >= bkt.CORRECT_SCORE}
                       for r in flat_ends])
    for e in ends:
        L.record("mock-learner", e["data"]["trap"], score=e["data"]["score"])
    live = {t["trap"]: t for t in L.mastery("mock-learner")["traps"]}
    for s in bkt.SKILLS:
        assert live[s]["score"] == round(batch[s]["score"], 3)
        assert live[s]["attempts"] == batch[s]["attempts"]



NEWS = {"trap": "unit_mismatch", "headline": "Grocer's sales report mixed cents and dollars",
        "url": "https://example.test/news", "trace": "https://example.test/trace"}
LEAK_WORDS = ("cents", "dollars", "news", "headline", "telem", "case of the day", "unit", "duplicate",
              "dictionary", "flip", "confound", "hidden", "nudge")


def test_nudge_raises_pick_rate_and_never_leaks():
    def rate(nudge, seed):
        rng = random.Random(seed)
        picks = [L.pick_next("gil", tier=1, rng=rng, nudge=nudge) for _ in range(400)]
        return picks, sum(p["skill"] == "unit_mismatch" for p in picks) / len(picks)

    plain, base = rate(None, 11)
    nudged, boosted = rate(NEWS, 11)
    assert boosted > base + 0.1, (base, boosted)
    assert boosted < 0.8                                   # modest: other skills still come up
    assert any(p["skill"] == "none" for p in nudged)       # a clean task stays possible
    for p in nudged:
        assert p["nudge"] == NEWS
        assert p["nudged"] == (p["skill"] == "unit_mismatch")
        assert p["bandit"]["unit_mismatch"]["boost"] == model.NUDGE_BOOST
        low = p["reason"].lower()
        assert NEWS["headline"].lower() not in low
        assert not any(w in low for w in LEAK_WORDS), p["reason"]
        assert not any(s in low for s in bkt.SKILLS if s != "none")
        assert NEWS["headline"] in p["pickReason"]
    assert any(p["nudgeDecided"] for p in nudged)
    assert all(p["nudged"] is False and p["nudge"] is None for p in plain)


def test_nudge_does_not_overrule_mastery():
    for _ in range(8):
        L.record("hal", "unit_mismatch", True)
    rng = random.Random(2)
    picks = [L.pick_next("hal", tier=1, rng=rng, nudge=NEWS) for _ in range(200)]
    assert sum(p["skill"] == "unit_mismatch" for p in picks) < 20
    missed = next(p for p in picks if p["skill"] != "unit_mismatch")
    assert missed["nudged"] is False and "mastery still favoured" in missed["pickReason"]
    for p in picks:
        assert not any(w in p["reason"].lower() for w in LEAK_WORDS)


def test_nudge_edge_cases():
    # avoided skill, unknown trap and the rules fallback: no boost, still a valid pick
    p = L.pick_next("ivy", tier=1, avoid=["unit_mismatch"], rng=random.Random(0), nudge=NEWS)
    assert p["skill"] != "unit_mismatch" and p["nudged"] is False and "no boost" in p["pickReason"]
    p = L.pick_next("ivy", tier=1, rng=random.Random(0), nudge={"trap": "weather", "headline": "x"})
    assert p["nudge"] is None and p["nudged"] is False
    p = L.pick_next("ivy", tier=1, rng=random.Random(0), nudge=NEWS, use_bandit=False)
    assert p["fallback"] is True and p["nudged"] is False and p["nudge"] == NEWS
    assert not any(w in p["reason"].lower() for w in LEAK_WORDS)

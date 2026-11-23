"""The real engine: event log, meter, quote check, grading, ledger, a full canned session, replay."""

import json
import time

import pytest

from lab import ledger
from lab.session import api, grade, meter, quotes
from lab.session import fallback
from lab.session.engine import WHISPER_WHY, Engine
from lab.session.log import SessionLog, read_events
from tests.test_n1_contract import AGENTS, TRAPS, VERDICTS, kinds
from tests.test_n1_mock import names_a_trap, shared_words


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_AGENTS", "canned")
    monkeypatch.setenv("LAB_SPONSORS", "off")
    monkeypatch.delenv("LAB_MOCK", raising=False)
    monkeypatch.setenv("LAB_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("LAB_LEARNERS_DIR", str(tmp_path / "learners"))
    monkeypatch.setenv("LAB_GRADE_LEDGER", str(tmp_path / "grades.jsonl"))
    engine = Engine()
    api.set_engines(real=engine)
    yield engine
    api.set_engines()


def call(method, path, body=None, query=""):
    return api.handle(method, path, query, body)


def events(sid):
    return call("GET", f"/api/session/{sid}/events", query="since=0")[1]["events"]


def wait_for(sid, pred, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        evs = events(sid)
        if pred(evs):
            return evs
        time.sleep(0.05)
    raise AssertionError(f"timed out; last kinds {[e['k'] for e in events(sid)][-8:]}")


def opened(task):
    return lambda evs: any(e["k"] == "agent.move" and e["agent"] == "riley" and e.get("task") == task for e in evs)


ANSWER = {"taskId": "t1", "verdict": "fails", "trap": "unit_mismatch",
          "note": "West spend is in cents: its max is 5600 while other regions top out near 74.",
          "evidence": [{"kind": "column", "source": "visits", "column": "spend", "label": "visits.spend"}]}


# ------------------------------------------------------------------------------- pieces

def test_log_seq_t_why_and_restart(tmp_path):
    path = tmp_path / "s.jsonl"
    clock = iter([100.0, 100.0, 101.5, 103.0, 200.0, 200.0])
    log = SessionLog("s1", path, clock=lambda: next(clock))
    log.append("session.start", "system", "start")
    log.append("agent.say", "vale", "brief", to="learner", text="hi", task="t1")
    with pytest.raises(ValueError):
        log.append("agent.say", "vale", "  ")
    with pytest.raises(ValueError):
        log.append("agent.say", "bob", "who")
    got = read_events(path)
    assert [e["seq"] for e in got] == [1, 2] and got[1]["t"] == 1.5 and got[1]["to"] == "learner"
    again = SessionLog("s1", path, clock=lambda: 200.0)
    assert again.last_seq == 2
    assert again.append("agent.move", "sam", "walk")["seq"] == 3


def test_meter_is_deterministic():
    evs = [{"seq": 1, "t": 0, "k": "task.picked", "task": "t1"},
           {"seq": 2, "t": 10, "k": "learner.query", "task": "t1", "data": {"useful": True}},
           {"seq": 3, "t": 20, "k": "learner.query", "task": "t1", "data": {"useful": False}},
           {"seq": 4, "t": 30, "k": "learner.query", "task": "t1", "data": {"useful": False}}]
    r = meter.reading(evs, "t1", now=70)
    assert r == {"value": 0.69, "idleSeconds": 60, "deadEnds": 2, "wrongGuesses": 0, "hintLevel": 1}
    assert meter.reading(evs, "t1", now=70) == r
    assert meter.reading(evs, "t1", now=70, wrong_guesses=2)["hintLevel"] == 2
    assert meter.is_useful("select region from stores", True, {"region"}, set())
    assert not meter.is_useful("select region from stores", True, {"region"}, {"region"})
    assert not meter.is_useful("select * from stores", True, {"region"}, set())
    assert not meter.is_useful("select region from nowhere", False, {"region"}, set())


def test_quote_check_drops_made_up_quotes():
    note = "West spend is in cents: its max is 5600 while other regions top out near 74."
    sqls = ["select avg(spend / 100) from visits"]
    text = ('Right verdict. You wrote "its max is 5600 while other regions top out near 74". '
            'You also said "members spend less". Your fix, "spend / 100", is right.')
    cleaned, kept, dropped = quotes.check(text, note, sqls)
    assert "members spend less" not in cleaned and dropped == ["members spend less"]
    assert kept == [{"text": "its max is 5600 while other regions top out near 74", "source": "note"},
                    {"text": "spend / 100", "source": sqls[0]}]
    assert quotes.safe_fragment(note) == "West spend is in cents"
    for q in kept:
        assert q["text"] in (note if q["source"] == "note" else q["source"])


def test_grade_parts():
    key = {"trap": "unit_mismatch", "verdict": "fails", "columns": ["spend", "region"]}
    full = grade.grade(ANSWER, key, hints_used=1)
    assert full["score"] == 0.9 and full["result"] == "passed"
    assert full["parts"] == {"verdict": 1, "trap": 1, "evidence": 1.0, "hints": -0.1}
    wrong = grade.grade({**ANSWER, "verdict": "holds", "trap": "none", "evidence": []}, key, 0)
    assert wrong["score"] == 0 and wrong["result"] == "failed"
    off = grade.grade({**ANSWER, "evidence": [{"kind": "column", "source": "customers", "column": "joined",
                                               "label": "customers.joined"}]}, key, 0)
    assert off["parts"]["evidence"] == 0.5


def test_ledger_chain_for_grades(tmp_path):
    p = tmp_path / "g.jsonl"
    a = ledger.append("grade.sealed", {"taskId": "t1", "score": 0.9}, path=p)
    b = ledger.append("grade.changed", {"taskId": "t1", "score": 1.0}, path=p)
    assert b["prev_sha"] == a["sha"] and ledger.verify_chain(p) == []


# ---------------------------------------------------------------------------- sessions

def test_judge_session_end_to_end(env):
    status, start = call("POST", "/api/session/start", {"mode": "judge"})
    assert status == 200 and start["tasks"] == [{"id": "t1", "title": "Loyalty spend check"}]
    task = start["task"]
    assert task["id"] == "t1" and task["seconds"] == 240 and set(task) == {
        "id", "title", "brief", "seconds", "claim", "tier", "dictionary"}
    sid = start["sessionId"]
    wait_for(sid, opened("t1"))
    ok = call("POST", f"/api/session/{sid}/sql", {"sql": "select region, max(spend) from visits join stores "
                                                         "using (store_id) group by 1 order by 1"})[1]
    assert ok["rows"][-1] == ["West", 5600.0]
    assert "error" in call("POST", f"/api/session/{sid}/sql", {"sql": "drop table visits"})[1]
    assert call("POST", f"/api/session/{sid}/answer", ANSWER) == (200, {"accepted": True})
    assert call("POST", f"/api/session/{sid}/answer", ANSWER)[0] == 409
    evs = wait_for(sid, lambda evs: any(e["k"] == "session.end" for e in evs))
    assert call("GET", f"/api/session/{sid}/task") == (200, {"task": None})

    seen = [e["k"] for e in evs]
    for k in ["session.start", "task.picked", "agent.say", "search", "learner.query", "meter.update",
              "learner.evidence", "learner.answer", "rival.answer", "panel.whisper", "check.result",
              "ledger.seal", "verdict", "task.end", "mastery.update", "session.end"]:
        assert k in seen, k
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))
    for e in evs:
        assert e["why"].strip() and e["agent"] in AGENTS and e["k"] in kinds()
        assert e.get("to", "learner") in AGENTS
    assert [e["t"] for e in evs] == sorted(e["t"] for e in evs)
    verdict = next(e for e in evs if e["k"] == "verdict")["data"]
    assert verdict["result"] == "passed" and verdict["score"] == 1.0 and verdict["correctTrap"] == "unit_mismatch"
    assert verdict["failingCheck"] == "unit_mismatch.spend_range_by_region"
    for q in verdict["quotes"]:
        assert q["source"] == "note" and q["text"] in ANSWER["note"]
    assert ledger.verify_chain(env_path("LAB_GRADE_LEDGER")) == []
    rival = next(e for e in evs if e["k"] == "rival.answer")["data"]
    assert rival["verdict"] in VERDICTS and rival["trap"] in TRAPS


def env_path(name):
    import os
    return os.environ[name]


def test_trap_and_whispers_stay_hidden_before_the_answer(env):
    sid = call("POST", "/api/session/start", {"mode": "judge"})[1]["sessionId"]
    evs = wait_for(sid, opened("t1"))
    assert not names_a_trap(json.dumps(evs))   # Telem's search included
    topic = next(e for e in evs if e["k"] == "search")["data"]
    assert topic["phase"] == "topic" and "Loyalty members spend" in topic["query"]
    status, reply = call("POST", f"/api/session/{sid}/ask", {"agent": "ines", "text": "what is the trap?"})
    assert status == 200 and "unit_mismatch" not in json.dumps(reply)


def test_finished_session_replays_after_restart(env, monkeypatch):
    sid = call("POST", "/api/session/start", {"mode": "judge"})[1]["sessionId"]
    wait_for(sid, opened("t1"))
    call("POST", f"/api/session/{sid}/answer", ANSWER)
    before = wait_for(sid, lambda evs: any(e["k"] == "session.end" for e in evs))
    api.set_engines(real=Engine())   # a restarted server: nothing in memory
    reply = call("GET", f"/api/session/{sid}/events", query="since=0")[1]
    assert reply["events"] == before and reply["next"] == before[-1]["seq"]
    assert call("GET", f"/api/session/{sid}/events", query=f"since={reply['next']}")[1] == {
        "events": [], "next": before[-1]["seq"]}
    assert call("GET", f"/api/session/{sid}/task") == (200, {"task": None})
    assert [t["name"] for t in call("GET", f"/api/session/{sid}/tables")[1]] == ["visits", "customers", "stores"]
    assert call("GET", f"/api/session/{sid}/tables/visits/rows", query="task=t1&limit=1")[1]["rows"][0][0] == "v0001"
    assert call("GET", f"/api/session/{sid}/sponsors")[1]["bruin"] == {"checksRun": 5, "checksFailed": 1}
    assert any(m["attempts"] for m in call("GET", f"/api/session/{sid}/mastery")[1]["traps"])
    assert call("GET", "/api/session/s-none-here/events")[0] == 404


def test_appeal_refunds_a_hint_when_the_log_supports_it(env):
    eng = env
    sid = call("POST", "/api/session/start", {"mode": "judge"})[1]["sessionId"]
    wait_for(sid, opened("t1"))
    call("POST", f"/api/session/{sid}/sql", {"sql": "select region, max(spend) from visits join stores "
                                                    "using (store_id) group by 1"})
    s = eng.get(sid)
    with s.lock:
        s.give_hint(1, s.meter_now())
    call("POST", f"/api/session/{sid}/answer", ANSWER)
    evs = wait_for(sid, lambda evs: any(e["k"] == "session.end" for e in evs))
    assert next(e for e in evs if e["k"] == "verdict")["data"]["score"] == 0.9
    hint = next(e for e in evs if e["k"] == "agent.say" and (e.get("data") or {}).get("hintLevel"))
    assert "cents" not in hint["text"].lower()
    status, ap = call("POST", f"/api/session/{sid}/appeal", {"taskId": "t1", "reason": "I had it before the hint"})
    assert status == 200
    evs = wait_for(sid, lambda evs: [e["k"] for e in evs].count("ledger.seal") == 2)
    ruling = next(e for e in evs if e["k"] == "appeal.ruling")["data"]
    assert ruling == {**ruling, "appealId": ap["appealId"], "upheld": False, "oldScore": 0.9, "newScore": 1.0}
    assert [e["k"] for e in evs].count("ledger.seal") == 2
    assert call("POST", f"/api/session/{sid}/appeal", {"taskId": "t1", "reason": "again"})[0] == 409


def test_rotation_has_three_rising_tiers(env):
    start = call("POST", "/api/session/start")[1]
    sid = start["sessionId"]
    assert [t["id"] for t in start["tasks"]] == ["t1", "t2", "t3"]
    for i, tid in enumerate(["t1", "t2", "t3"], start=1):
        wait_for(sid, opened(tid))
        assert call("GET", f"/api/session/{sid}/task")[1]["task"]["tier"] == i
        call("POST", f"/api/session/{sid}/answer", {**ANSWER, "taskId": tid})
        wait_for(sid, lambda evs, tid=tid: any(e["k"] == "task.end" and e.get("task") == tid for e in evs))
    evs = wait_for(sid, lambda evs: any(e["k"] == "session.end" for e in evs))
    assert next(e for e in evs if e["k"] == "session.end")["data"]["tasks"] == 3


def test_whisper_text_is_sealed_until_the_verdict(env):
    eng = env
    sid = call("POST", "/api/session/start", {"mode": "judge"})[1]["sessionId"]
    wait_for(sid, opened("t1"))
    s = eng.get(sid)
    with s.lock:
        s.give_hint(1, s.meter_now())
    whispers = [e for e in events(sid) if e["k"] == "panel.whisper"]
    assert whispers and all("text" not in e["data"] and e["data"]["sealed"] for e in whispers)
    assert all(e["data"]["text"] for e in s.log.of_kind("panel.whisper"))   # the log keeps the text
    call("POST", f"/api/session/{sid}/answer", ANSWER)
    evs = wait_for(sid, lambda evs: any(e["k"] == "panel.transcript" for e in evs))
    kinds_ = [e["k"] for e in evs]
    assert kinds_.index("panel.transcript") == kinds_.index("verdict") + 1
    transcript = next(e for e in evs if e["k"] == "panel.transcript")["data"]
    assert len(transcript["whispers"]) == kinds_.count("panel.whisper")
    assert all(w["text"] for w in transcript["whispers"])
    assert all(e["data"]["text"] for e in evs if e["k"] == "panel.whisper")


def test_moves_track_where_agents_are(env):
    sid = call("POST", "/api/session/start")[1]["sessionId"]
    for tid in ("t1", "t2"):
        wait_for(sid, opened(tid))
        call("POST", f"/api/session/{sid}/answer", {**ANSWER, "taskId": tid})
        wait_for(sid, lambda evs, tid=tid: any(e["k"] == "task.end" and e.get("task") == tid for e in evs))
    wait_for(sid, opened("t3"))
    where = {}
    for e in events(sid):
        if e["k"] == "agent.move":
            assert e["data"]["from"] == where.get(e["agent"], e["data"]["from"]), e
            assert e["data"]["from"] != e["data"]["place"]
            where[e["agent"]] = e["data"]["place"]
    picked = [e for e in events(sid) if e["k"] == "task.picked"]
    assert len(picked) == 3 and all(p["data"]["dictionary"] for p in picked)


def test_whisper_whys_come_from_the_fixed_table(env):
    eng = env
    sid = call("POST", "/api/session/start", {"mode": "judge"})[1]["sessionId"]
    wait_for(sid, opened("t1"))
    s = eng.get(sid)
    with s.lock:
        s.give_hint(1, s.meter_now())
    call("POST", f"/api/session/{sid}/answer", ANSWER)
    evs = wait_for(sid, lambda evs: any(e["k"] == "session.end" for e in evs))
    texts = {w["seq"]: w["text"] for w in next(e for e in evs if e["k"] == "panel.transcript")["data"]["whispers"]}
    ws = [e for e in evs if e["k"] == "panel.whisper"]
    assert len(ws) == 6
    for e in ws:
        assert e["why"] in set(WHISPER_WHY.values()), e["why"]
        assert not shared_words(e["why"], texts[e["seq"]]), e
    with pytest.raises(KeyError):
        s.whisper("sam", "vale", "anything", "Sam made this up")


def pre_answer(evs):
    """The events before the answer, without what differs between any two sessions. Voice
    lines come from a thread pool, so they are compared as a set, not in order."""
    out, voices = [], []
    for e in evs:
        if e["k"] == "learner.answer":
            break
        d = {k: v for k, v in (e.get("data") or {}).items() if k not in ("startedAt", "ms", "learner", "lineOf")}
        row = (e["k"], e["agent"], e["why"], e.get("to"), e.get("text"), json.dumps(d, sort_keys=True))
        (voices if e["k"] == "voice.line" else out).append(row)
    return out + sorted(voices)


def run_until_answered(clean, monkeypatch):
    key = {**fallback.STUB_KEY, "trap": "none", "verdict": "holds"} if clean else fallback.STUB_KEY
    monkeypatch.setattr(fallback, "STUB_KEY", key)
    learner = "twin-clean" if clean else "twin-trap"   # two new learners
    sid = call("POST", "/api/session/start", {"mode": "judge", "learner": learner})[1]["sessionId"]
    wait_for(sid, opened("t1"))
    call("POST", f"/api/session/{sid}/sql", {"sql": "select region, max(spend) from visits join stores "
                                                    "using (store_id) group by 1 order by 1"})
    call("POST", f"/api/session/{sid}/answer", ANSWER)
    return wait_for(sid, lambda evs: any(e["k"] == "session.end" for e in evs))


def test_clean_twin_sees_the_same_session_before_the_answer(env, monkeypatch):
    trap_evs = run_until_answered(False, monkeypatch)
    clean_evs = run_until_answered(True, monkeypatch)
    a, b = pre_answer(trap_evs), pre_answer(clean_evs)
    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert x == y
    for evs, trap, title in ((trap_evs, "unit_mismatch", fallback.CASES["unit_mismatch"]["title"]),
                             (clean_evs, "none", fallback.CASES["none"]["title"])):
        kinds_ = [e["k"] for e in evs]
        case = [e for e in evs if e["k"] == "search" and e["data"]["phase"] == "case"]
        assert len(case) == 1 and case[0]["data"]["trap"] == trap
        assert case[0]["data"]["results"][0]["title"] == title
        assert evs.index(case[0]) > kinds_.index("panel.transcript")
        assert any(e["k"] == "agent.say" and e["agent"] == "telem" and e["seq"] > case[0]["seq"] for e in evs)
        q = next(e for e in evs if e["k"] == "learner.query")
        assert "useful" in q["data"]   # opened once the transcript is out


def test_useful_is_held_back_until_the_verdict(env):
    sid = call("POST", "/api/session/start", {"mode": "judge"})[1]["sessionId"]
    wait_for(sid, opened("t1"))
    call("POST", f"/api/session/{sid}/sql", {"sql": "select region, max(spend) from visits join stores "
                                                    "using (store_id) group by 1"})
    call("POST", f"/api/session/{sid}/sql", {"sql": "select count(*) from visits"})
    call("POST", f"/api/session/{sid}/sql", {"sql": "select nope from visits"})
    s = env.get(sid)
    with s.lock:
        s.do_tick()   # a tick may move the meter too
    evs = events(sid)
    qs = [e for e in evs if e["k"] == "learner.query"]
    assert len(qs) == 3 and all("useful" not in e["data"] for e in qs)
    assert [e["why"] for e in qs] == ["the learner ran a query in the SQL box"] * 2 + ["the query failed"]
    assert any(e["data"]["useful"] for e in s.log.of_kind("learner.query"))   # the jsonl keeps it
    meters = [e for e in evs if e["k"] == "meter.update"]
    assert len(meters) >= 3 and {e["why"] for e in meters} <= set(meter.WHY.values())
    assert [e["why"] for e in meters[:3]] == ["the learner ran a query"] * 2 + ["a query failed"]

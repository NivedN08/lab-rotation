"""The real engine: event log, meter, quote check, grading, ledger, a full canned session, replay."""

import json
import time

import pytest

from lab import ledger
from lab.session import api, grade, meter, quotes
from lab.session import fallback, sources
from lab.session.engine import NEWS_BRIEF, WHISPER_WHY, Engine
from lab.session.log import SessionLog, read_events
from tests.test_n1_contract import AGENTS, TRAPS, VERDICTS, kinds
from tests.test_n1_mock import names_a_trap, shared_words


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_AGENTS", "canned")
    monkeypatch.setenv("LAB_SPONSORS", "off")
    monkeypatch.setenv("LAB_N3", "off")   # the stub task and the local learner model
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
    lines and sponsor calls come from a thread pool, so they are compared as a set."""
    out, voices = [], []
    for e in evs:
        if e["k"] == "learner.answer":
            break
        d = {k: v for k, v in (e.get("data") or {}).items() if k not in ("startedAt", "ms", "learner", "lineOf")}
        row = (e["k"], e["agent"], e["why"], e.get("to"), e.get("text"), json.dumps(d, sort_keys=True))
        (voices if e["k"] in ("voice.line", "sponsor.call") else out).append(row)
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


NEWS = {"title": "A grocer restates sales after an export used cents", "url": "https://example.com/news",
        "trace": "https://app.telem.ai/traces/t1", "summary": "One region's export switched units.",
        "cached": False}
BENCH = {"kind": "basket", "label": "A basket of 4 staples (milk, bread, coffee, paper towels), US online prices",
         "value": 33.87, "low": 25.62, "high": 67.04, "unit": "USD",
         "source": "Google Shopping via Glasser (serper /shopping)", "cost": 0.008,
         "trace": "https://app.glasser.ai/runs/b1", "cached": False}
STAPLES = "a basket of 4 staples (milk, bread, coffee, paper towels), US online prices: about $34 ($26 to $67)"


def run_with_news(monkeypatch, trap, learner, clean=False):
    monkeypatch.setattr(sources, "case_of_day", lambda sp: {**NEWS, **({"trap": trap} if trap else {})})
    key = {**fallback.STUB_KEY, "trap": "none", "verdict": "holds"} if clean else fallback.STUB_KEY
    monkeypatch.setattr(fallback, "STUB_KEY", key)
    sid = call("POST", "/api/session/start", {"mode": "judge", "learner": learner})[1]["sessionId"]
    wait_for(sid, opened("t1"))
    call("POST", f"/api/session/{sid}/answer", ANSWER)
    return wait_for(sid, lambda evs: any(e["k"] == "session.end" for e in evs))


def test_news_nudges_the_pick_but_waits_for_the_verdict(env, monkeypatch):
    steered = run_with_news(monkeypatch, "unit_mismatch", "news-a")
    plain = run_with_news(monkeypatch, None, "news-b")
    clean = run_with_news(monkeypatch, "unit_mismatch", "news-c", clean=True)
    assert pre_answer(steered) == pre_answer(plain) == pre_answer(clean)
    for evs in (steered, plain, clean):
        kinds_ = [e["k"] for e in evs]
        before = evs[:kinds_.index("panel.transcript")]
        assert "monitor.hit" not in kinds_[:kinds_.index("panel.transcript")]
        assert NEWS["title"] not in json.dumps(before) and not names_a_trap(json.dumps(evs[:kinds_.index("learner.answer")]))
        brief = next(e for e in evs if e["k"] == "agent.say" and e["agent"] == "vale")
        assert brief["text"].endswith(NEWS_BRIEF)
        hit = next(e for e in evs if e["k"] == "monitor.hit")
        assert hit["data"]["title"] == NEWS["title"] and hit["data"]["trace"] == NEWS["trace"]
        reveal = next(e for e in evs if e["k"] == "agent.say" and e["agent"] == "vale" and e["seq"] > hit["seq"])
        end = next(e for e in evs if e["k"] == "task.end")["data"]
        assert end["news"]["steered"] == hit["data"]["steered"]
        assert ("I picked this task because" in reveal["text"]) == hit["data"]["steered"]
    assert next(e for e in plain if e["k"] == "monitor.hit")["data"]["steered"] is False
    assert "Telem's case of the day" in next(e for e in steered if e["k"] == "task.end")["data"]["pickReason"]


def test_local_picker_boost_tilts_the_draw(env):
    import random
    nudged = 0
    for seed in range(40):
        got = sources.pick_next("nobody-" + str(seed), [], [], 1, random.Random(seed),
                                nudge={"trap": "confounder", "headline": "Store mix fooled a chain", "url": "",
                                       "trace": ""})
        assert got["nudged"] == (got["skill"] == "confounder")
        assert "Store mix fooled a chain" in got["pickReason"] and "Store mix" not in got["reason"]
        nudged += got["nudged"]
    assert 10 <= nudged < 40   # a tilt, not an override


def test_telem_answers_from_a_search(env, monkeypatch):
    found = {"query": "q", "trace": "https://app.telem.ai/traces/a", "cached": False,
             "results": [{"title": "How POS exports store money", "url": "https://example.com/pos",
                          "snippet": "Some systems store amounts in cents."},
                         {"title": "Minor units in payments", "url": "https://example.com/minor", "snippet": "x"}]}
    monkeypatch.setattr(sources, "telem_answer", lambda sp, q: found)
    sid = call("POST", "/api/session/start", {"mode": "judge"})[1]["sessionId"]
    wait_for(sid, opened("t1"))
    status, reply = call("POST", f"/api/session/{sid}/ask", {"agent": "telem",
                                                            "text": "Do POS exports ever store money in cents?"})
    assert status == 200 and "How POS exports store money" in reply["text"] and "cents" in reply["text"]
    assert reply["links"][0]["url"] == "https://example.com/pos" and reply["trace"] == found["trace"]
    status, reply = call("POST", f"/api/session/{sid}/ask", {"agent": "telem", "text": "How are POS exports stored?"})
    assert reply["text"] == "I can't say that before the verdict." and "links" not in reply   # cents is new here
    answer = [e for e in events(sid) if e["k"] == "ask.answer"][0]
    assert answer["data"]["links"] and answer["data"]["sources"] == ["Telem's web search"]


def test_glasser_fact_in_the_level_2_hint_and_the_verdict(env, monkeypatch):
    calls = []
    monkeypatch.setattr(sources, "glasser_benchmark", lambda sp, kind, by: calls.append((kind, by)) or BENCH)
    sid = call("POST", "/api/session/start", {"mode": "judge"})[1]["sessionId"]
    wait_for(sid, opened("t1"))
    s = env.get(sid)
    with s.lock:
        s.give_hint(1, s.meter_now())
        s.give_hint(2, s.meter_now())
    call("POST", f"/api/session/{sid}/answer", ANSWER)
    evs = wait_for(sid, lambda evs: any(e["k"] == "session.end" for e in evs))
    hint2 = next(e for e in evs if e["k"] == "agent.say" and (e.get("data") or {}).get("hintLevel") == 2)
    assert hint2["text"].startswith(f"I spent $0.008 to check: {STAPLES}. ")
    assert hint2["data"]["bought"]["cost"] == 0.008 and hint2["data"]["bought"]["trace"] == BENCH["trace"]
    hint1 = next(e for e in evs if e["k"] == "agent.say" and (e.get("data") or {}).get("hintLevel") == 1)
    assert "bought" not in hint1["data"]
    verdict = next(e for e in evs if e["k"] == "verdict")["data"]
    assert verdict["benchmark"]["low"] == 25.62 and verdict["text"].endswith(
        f"Reality check: {STAPLES}, from Glasser ($0.008). The $1,067 a quick read gives (members' average "
        "spend per visit, before the fix) should have looked wrong: fixed, it is $37.")
    assert calls == [("basket", "sam"), ("basket", "ines")]


def test_real_n3_bank_checks_and_learner(env, monkeypatch):
    """With N3 there: a real bank task, N3's checks and N3's learner model, and a replay after restart."""
    pytest.importorskip("lab.tasks.bank")
    monkeypatch.delenv("LAB_N3", raising=False)
    sid = call("POST", "/api/session/start", {"mode": "judge", "learner": "n3-real"})[1]["sessionId"]
    wait_for(sid, opened("t1"), timeout=120)   # the first run may build the bank
    s = env.get(sid)
    assert not s.slot.task.stub and s.slot.task.n3 is not None
    picked = next(e for e in events(sid) if e["k"] == "task.picked")["data"]
    assert picked["fallback"] is False
    trap = s.slot.task.key["trap"]
    call("POST", f"/api/session/{sid}/answer", {**ANSWER, "trap": trap,
                                               "verdict": "holds" if trap == "none" else "fails"})
    evs = wait_for(sid, lambda evs: any(e["k"] == "session.end" for e in evs), timeout=120)
    checks = [e["data"] for e in evs if e["k"] == "check.result"]
    assert len(checks) == 5 and sum(not c["passed"] for c in checks) == (0 if trap == "none" else 1)
    traps = {m["trap"]: m for m in call("GET", f"/api/session/{sid}/mastery")[1]["traps"]}
    assert traps[trap]["attempts"] == 1
    api.set_engines(real=Engine())   # a restarted server reads the same task back from N3's bank
    assert call("GET", f"/api/session/{sid}/events", query="since=0")[1]["events"] == evs
    assert call("GET", f"/api/session/{sid}/mastery")[1]["traps"] == list(traps.values())


def test_task_query_opens_only_the_current_or_a_finished_task(env):
    sid = call("POST", "/api/session/start")[1]["sessionId"]   # a rotation: t1, t2, t3
    wait_for(sid, opened("t1"))
    assert call("GET", f"/api/session/{sid}/tables", query="task=t1")[0] == 200
    for path in ("tables", "tables/visits/rows", "tables/visits/profile"):
        status, reply = call("GET", f"/api/session/{sid}/{path}", query="task=t3")
        assert status == 409 and reply["error"], path   # a future task
    assert call("GET", f"/api/session/{sid}/tables", query="task=t9")[0] == 409   # no such task
    assert call("GET", f"/api/session/{sid}/tables", query="task=x")[0] == 400
    call("POST", f"/api/session/{sid}/answer", ANSWER)
    wait_for(sid, opened("t2"))
    assert call("GET", f"/api/session/{sid}/tables", query="task=t1")[0] == 200   # finished
    assert call("GET", f"/api/session/{sid}/tables", query="task=t2")[0] == 200   # current
    assert call("GET", f"/api/session/{sid}/tables", query="task=t3")[0] == 409


def test_benchmark_lines_are_built_from_the_numbers():
    free = {**BENCH, "cost": 0.0}
    assert sources.benchmark_source(free) == "Glasser"   # a repeat in the same session is free
    assert sources.benchmark_source({**BENCH, "cost": 0, "cached": True}) == "Glasser (recorded)"
    assert sources.benchmark_source({"source": "fixed value (not from Glasser)", "cost": 0}).startswith("a recorded")
    kpi = {"label": "Target stores, FY 2025", "value": 1995, "low": None, "high": None, "unit": "stores"}
    assert sources.benchmark_range(kpi) == "1,995 stores"
    assert sources.benchmark_range({"low": 30, "high": 45, "unit": "USD per visit"}) == "$30 to $45 per visit"


def test_one_glasser_per_session(monkeypatch):
    monkeypatch.setenv("LAB_SPONSORS", "on")
    made = []

    class FakeGlasser:
        def __init__(self, on_call=None):
            made.append(self)
            self.on_call = on_call

        def benchmark(self, kind, by="system"):
            first = len(made[0].__dict__.setdefault("bought", [])) == 0
            made[0].bought.append(kind)
            self.on_call({"sponsor": "glasser", "label": "Benchmark", "count": 1 if first else 0,
                          "cost": 0.008 if first else 0.0})
            return {**BENCH, "cost": 0.008 if first else 0.0}

    import types, sys
    monkeypatch.setitem(sys.modules, "lab.sponsors.glasser", types.SimpleNamespace(Glasser=FakeGlasser))
    # The real Telem and Runware clients would read .env into this process; keep them out.
    monkeypatch.setitem(sys.modules, "lab.sponsors.telem", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "lab.sponsors.runware", types.SimpleNamespace())
    seen = []
    sp = sources.Sponsors(seen.append)
    a = sources.glasser_benchmark(sp, "basket", "sam")
    b = sources.glasser_benchmark(sp, "basket", "ines")
    assert len(made) == 1 and a["cost"] == 0.008 and b["cost"] == 0.0
    assert [c["count"] for c in seen] == [1, 0]   # the repeat is reported, free


def test_naive_sentence_only_when_the_quick_number_is_clearly_off():
    from lab.session.engine import naive_sentence
    unit = {"value": 1632.71, "unit": "USD per visit", "label": "members' average spend per visit, before the fix",
            "group": "members", "fixed": 42.53}
    assert naive_sentence({"trap": "unit_mismatch", "naive": unit}) == (
        "The $1,633 a quick read gives (members' average spend per visit, before the fix) should have looked "
        "wrong: fixed, it is $43.")
    assert naive_sentence({"trap": "confounder", "naive": {**unit, "value": 42.53}}) == ""      # value == fixed
    assert naive_sentence({"trap": "duplicate_rows", "naive": {**unit, "value": 47.1}}) == ""   # a few dollars
    assert naive_sentence({"trap": "hidden_variable"}) == ""                                   # no naive key
    assert naive_sentence({"trap": "none", "naive": unit}) == ""
    assert naive_sentence({"trap": "unit_mismatch", "naive": {**unit, "fixed": 0}}) == ""


def test_session_end_comes_after_the_last_voice_line(env):
    sid = call("POST", "/api/session/start", {"mode": "judge"})[1]["sessionId"]
    wait_for(sid, opened("t1"))
    call("POST", f"/api/session/{sid}/answer", ANSWER)
    evs = wait_for(sid, lambda evs: any(e["k"] == "session.end" for e in evs))
    time.sleep(0.5)
    evs = events(sid)
    assert evs[-1]["k"] == "session.end", [e["k"] for e in evs[-4:]]

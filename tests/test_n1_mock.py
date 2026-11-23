"""Mock mode answers every route of contract/api.md and replays the mock session at speed."""

import json

import pytest

from lab.session import api
from lab.session.engine import LEAK, WHISPER_WHY
from lab.session.mock import MockEngine
from lab.session.tables import TaskTables
from tests.test_n1_contract import CONTRACT


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def mock(monkeypatch):
    monkeypatch.setenv("LAB_MOCK", "1")
    monkeypatch.setenv("LAB_MOCK_SPEED", "1")
    clock = Clock()
    engine = MockEngine(clock=clock)
    api.set_engines(mock=engine, real=None)
    yield clock
    api.set_engines()


def call(method, path, body=None, query=""):
    return api.handle(method, path, query, body)


def start():
    status, reply = call("POST", "/api/session/start")
    assert status == 200
    return reply


def test_health_agents_demo(mock, monkeypatch):
    assert call("GET", "/api/health") == (200, {"ok": True, "mock": True, "band": "local"})
    status, agents = call("GET", "/api/agents")
    assert status == 200 and {a["id"] for a in agents} == {"vale", "ines", "sam", "telem", "riley"}
    for a in agents:
        assert {"id", "name", "role", "reads", "portrait"} <= set(a)
    monkeypatch.delenv("LAB_DEMO_SESSION", raising=False)
    assert call("GET", "/api/demo") == (200, {"session": None})
    monkeypatch.setenv("LAB_DEMO_SESSION", "s-abc")
    monkeypatch.setenv("LAB_DEMO_START", "12.5")
    monkeypatch.setenv("LAB_DEMO_SPEED", "2")
    assert call("GET", "/api/demo") == (200, {"session": "s-abc", "start": 12.5, "end": None, "speed": 2.0})


def test_start_and_task(mock):
    reply = start()
    task = json.loads((CONTRACT / "mock_task" / "task.json").read_text())
    assert reply["sessionId"].startswith("mock-")
    assert reply["tasks"] == [{"id": "t1", "title": task["title"]}]
    assert reply["task"] == task
    assert call("GET", f"/api/session/{reply['sessionId']}/task") == (200, {"task": task})


def test_events_release_at_real_speed(mock, monkeypatch):
    sid = start()["sessionId"]
    status, first = call("GET", f"/api/session/{sid}/events", query="since=0")
    assert status == 200 and [e["seq"] for e in first["events"]] == [1]   # only t=0 so far
    assert first["next"] == 1
    script = [json.loads(line) for line in (CONTRACT / "mock_session.jsonl").read_text().splitlines() if line]
    upto13 = [e["seq"] for e in script if e["t"] <= 13]
    mock.now += 13
    _, more = call("GET", f"/api/session/{sid}/events", query="since=1")
    assert [e["seq"] for e in more["events"]] == upto13[1:]
    _, none = call("GET", f"/api/session/{sid}/events", query=f"since={more['next']}")
    assert none == {"events": [], "next": upto13[-1]}
    monkeypatch.setenv("LAB_MOCK_SPEED", "100")
    _, rest = call("GET", f"/api/session/{sid}/events", query=f"since={upto13[-1]}")
    assert rest["events"][-1]["k"] == "session.end" and rest["next"] == script[-1]["seq"]
    assert call("GET", f"/api/session/{sid}/task") == (200, {"task": None})


def test_totals_and_mastery_follow_the_replay(mock):
    sid = start()["sessionId"]
    mock.now += 1000
    _, totals = call("GET", f"/api/session/{sid}/sponsors")
    assert totals["band"]["messages"] == 7
    assert totals["bruin"] == {"checksRun": 5, "checksFailed": 1}
    assert totals["runware"]["lines"] == 5
    assert totals["telem"]["searches"] == 2
    assert totals["glasser"]["calls"] == 2
    _, mastery = call("GET", f"/api/session/{sid}/mastery")
    by_trap = {m["trap"]: m for m in mastery["traps"]}
    assert len(by_trap) == 6 and by_trap["unit_mismatch"] == {"trap": "unit_mismatch", "score": 0.61, "attempts": 1}


def test_tables_rows_profile_sql(mock):
    sid = start()["sessionId"]
    _, tables = call("GET", f"/api/session/{sid}/tables")
    assert [t["name"] for t in tables] == ["visits", "customers", "stores"]
    assert tables[0]["rowCount"] == 300 and "key" not in tables[0]
    _, rows = call("GET", f"/api/session/{sid}/tables/visits/rows", query="offset=0&limit=2")
    assert rows["rows"][0][0] == "v0001" and len(rows["rows"]) == 2
    _, rows = call("GET", f"/api/session/{sid}/tables/visits/rows", query="limit=9999")
    assert len(rows["rows"]) == 300
    _, prof = call("GET", f"/api/session/{sid}/tables/visits/profile")
    spend = next(c for c in prof["columns"] if c["column"] == "spend")
    assert spend["type"] == "real" and spend["max"] == 5600.0 and "mean" in spend and len(spend["top"]) <= 5
    status, res = call("POST", f"/api/session/{sid}/sql", {"sql": "select count(*) as n from visits"})
    assert status == 200 and res["columns"] == ["n"] and res["rows"] == [[300]] and res["truncated"] is False
    status, res = call("POST", f"/api/session/{sid}/sql", {"sql": "select * from nope"})
    assert status == 200 and "error" in res
    assert call("GET", f"/api/session/{sid}/tables/nope/rows")[0] == 404


def test_canned_posts(mock):
    sid = start()["sessionId"]
    answer = {"taskId": "t1", "verdict": "fails", "trap": "unit_mismatch", "evidence": [], "note": "West is in cents"}
    assert call("POST", f"/api/session/{sid}/answer", answer) == (200, {"accepted": True})
    status, appeal = call("POST", f"/api/session/{sid}/appeal", {"taskId": "t1", "reason": "the hint came late"})
    assert status == 200 and appeal["appealId"]
    assert call("POST", f"/api/session/{sid}/appeal/{appeal['appealId']}/message", {"text": "see q5"}) == \
        (200, {"ok": True})
    status, reply = call("POST", f"/api/session/{sid}/ask", {"agent": "vale", "text": "why this task?"})
    assert status == 200 and reply["agent"] == "vale" and reply["text"] and isinstance(reply["sources"], list)


def test_bad_requests(mock):
    sid = start()["sessionId"]
    assert call("POST", f"/api/session/{sid}/answer", {"taskId": "t1", "verdict": "maybe", "trap": "none"})[0] == 400
    assert call("POST", f"/api/session/{sid}/ask", {"agent": "learner", "text": "hi"})[0] == 400
    assert call("GET", f"/api/session/{sid}/events", query="since=-1")[0] == 400
    assert call("GET", "/api/session/bad id!/task")[0] == 400
    assert call("GET", "/api/nothing")[0] == 404
    assert call("POST", "/api/session/start", {"mode": "party"})[0] == 400


@pytest.mark.parametrize("sql", [
    "drop table visits", "select 1; select 2", "attach 'x.db'", "copy visits to 'out.csv'",
    "select * from read_csv('/etc/passwd')", "select * from 'contract/mock_task/visits.csv'",
    "install httpfs", "set enable_external_access = true", "select getenv('HOME')",
    "create table x as select 1", "pragma database_list",
])
def test_sql_box_blocks_escapes(sql):
    res = TaskTables(CONTRACT / "mock_task").query(sql)
    assert "error" in res and "rows" not in res


def test_sql_box_caps_rows():
    res = TaskTables(CONTRACT / "mock_task").query("select * from visits a, visits b")
    assert len(res["rows"]) == 500 and res["truncated"] is True


def test_mock_whispers_sealed_until_the_transcript(mock):
    sid = start()["sessionId"]
    mock.now += 215   # after the panel confers, before the verdict at 220
    _, before = call("GET", f"/api/session/{sid}/events", query="since=0")
    ws = [e for e in before["events"] if e["k"] == "panel.whisper"]
    assert ws and all("text" not in e["data"] and e["data"]["sealed"] for e in ws)
    mock.now += 10
    _, after = call("GET", f"/api/session/{sid}/events", query="since=0")
    kinds_ = [e["k"] for e in after["events"]]
    assert kinds_.index("panel.transcript") == kinds_.index("verdict") + 1
    transcript = next(e for e in after["events"] if e["k"] == "panel.transcript")["data"]
    assert transcript["taskId"] == "t1" and [w["seq"] for w in transcript["whispers"]] == [e["seq"] for e in ws]
    opened = [e for e in after["events"] if e["k"] == "panel.whisper"]
    assert all(e["data"]["text"] and "sealed" not in e["data"] for e in opened)


GENERIC = {"learner", "verdict", "panel", "grade", "check", "level", "hint", "hints"}


def shared_words(why, text):
    """Words of five or more letters in a whisper's why that also appear in its text."""
    def words(x):
        return {w for w in "".join(c if c.isalpha() else " " for c in x.lower()).split() if len(w) >= 5}
    return (words(why) - GENERIC) & words(text)


def names_a_trap(text):
    low = text.lower()
    return [w for ws in LEAK.values() for w in ws if w in low]


def test_whisper_whys_are_fixed_templates():
    for (agent, purpose), why in WHISPER_WHY.items():
        assert why.lower().startswith(agent) and not names_a_trap(why), why


def test_mock_whisper_whys_come_from_the_table(mock):
    sid = start()["sessionId"]
    mock.now += 1000
    evs = call("GET", f"/api/session/{sid}/events", query="since=0")[1]["events"]
    texts = {w["seq"]: w["text"] for w in next(e for e in evs if e["k"] == "panel.transcript")["data"]["whispers"]}
    whys = set(WHISPER_WHY.values())
    ws = [e for e in evs if e["k"] == "panel.whisper"]
    assert len(ws) == 6
    for e in ws:
        assert e["why"] in whys, e["why"]
        assert not shared_words(e["why"], texts[e["seq"]]), e


def test_mock_says_nothing_of_the_trap_before_the_answer(mock):
    sid = start()["sessionId"]
    mock.now += 1000
    evs = call("GET", f"/api/session/{sid}/events", query="since=0")[1]["events"]
    answered = next(e["seq"] for e in evs if e["k"] == "learner.answer")
    for e in evs:
        if e["seq"] >= answered:
            break
        if e["k"] == "agent.say" and (e.get("data") or {}).get("hintLevel"):
            continue   # Sam's hints point the way on purpose
        assert not names_a_trap(json.dumps(e)), e
    searches = [e for e in evs if e["k"] == "search"]
    assert [e["data"]["phase"] for e in searches] == ["topic", "case"]
    claim = json.loads((CONTRACT / "mock_task" / "task.json").read_text())["claim"]
    assert claim in searches[0]["data"]["query"]
    kinds_ = [e["k"] for e in evs]
    assert evs.index(searches[1]) > kinds_.index("panel.transcript") and searches[1]["data"]["trap"] == "unit_mismatch"


def test_mock_holds_back_useful_until_the_verdict(mock):
    sid = start()["sessionId"]
    mock.now += 1000
    evs = call("GET", f"/api/session/{sid}/events", query="since=0")[1]["events"]
    qs = [e for e in evs if e["k"] == "learner.query"]
    assert qs and all("useful" not in e["data"] for e in qs)
    assert {e["why"] for e in qs} <= {"the learner ran a query in the SQL box", "the query failed"}

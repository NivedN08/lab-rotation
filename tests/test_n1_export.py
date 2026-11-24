"""The static replay export: the route shapes as plain files, and a leak scan that never passes
the answer key, the bank's sealed files or a `.env` value."""

import json
import time

import pytest

from lab.session import api, export_static, sources
from lab.session.engine import Engine
from lab.session.fallback import STUB_KEY

AGENT_IDS = ("vale", "ines", "sam", "telem", "riley")
ANSWER = {"taskId": "t1", "verdict": "fails", "trap": "unit_mismatch",
          "note": "West spend is in cents: its max is 5600 while other regions top out near 74.",
          "evidence": [{"kind": "column", "source": "visits", "column": "spend", "label": "visits.spend"}]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_AGENTS", "canned")
    monkeypatch.setenv("LAB_SPONSORS", "off")
    monkeypatch.setenv("LAB_N3", "off")
    monkeypatch.delenv("LAB_MOCK", raising=False)
    monkeypatch.setenv("LAB_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("LAB_LEARNERS_DIR", str(tmp_path / "learners"))
    monkeypatch.setenv("LAB_GRADE_LEDGER", str(tmp_path / "grades.jsonl"))
    audio = tmp_path / "audio"
    audio.mkdir()

    def tts(_sponsors, agent, text, line_of=None):   # a voice file for every line, as Runware gives
        name = f"{agent}-{line_of}.mp3"
        (audio / name).write_bytes(b"ID3 not really audio")
        return {"file": name, "seconds": 1.0, "provider": "runware", "cost": 0.001}

    monkeypatch.setattr(sources, "tts", tts)
    portraits = tmp_path / "portraits"
    portraits.mkdir()
    for a in AGENT_IDS[:-1]:                         # riley's portrait is missing on purpose
        (portraits / f"{a}.png").write_bytes(b"\x89PNG portrait")
    api.set_engines(real=Engine())
    yield {"tmp": tmp_path, "audio": audio, "portraits": portraits}
    api.set_engines()


def call(method, path, body=None, query=""):
    return api.handle(method, path, query, body)


def wait_for(sid, pred, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        evs = call("GET", f"/api/session/{sid}/events", query="since=0")[1]["events"]
        if pred(evs):
            return evs
        time.sleep(0.05)
    raise AssertionError("timed out")


def opened(task):
    return lambda evs: any(e["k"] == "agent.move" and e["agent"] == "riley" and e.get("task") == task for e in evs)


def ended(evs):
    return any(e["k"] == "session.end" for e in evs)


def finished_session(mode="judge"):
    start = call("POST", "/api/session/start", {"mode": mode})[1]
    sid = start["sessionId"]
    for t in start["tasks"]:
        wait_for(sid, opened(t["id"]))
        call("POST", f"/api/session/{sid}/answer", {**ANSWER, "taskId": t["id"]})
        wait_for(sid, lambda evs, tid=t["id"]: any(e["k"] == "task.end" and e.get("task") == tid for e in evs))
    wait_for(sid, ended)
    api.set_engines(real=Engine())   # export reads from disk, like a later run of the command
    return sid


def export(env, sid, **kw):
    out = env["tmp"] / "site" / "recorded"
    got = export_static.export(sid, out, audio_dir=env["audio"], portraits_dir=env["portraits"], **kw)
    return out, got


def strings(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from strings(v)
    elif isinstance(x, str):
        yield x


def json_files(out):
    return {p.relative_to(out).as_posix(): json.loads(p.read_text()) for p in out.rglob("*.json")}


# ------------------------------------------------------------------------------- the export

def test_export_is_the_route_shapes_as_static_files(env, monkeypatch):
    monkeypatch.setattr(export_static, "PAGE", 50)   # several pages per table
    sid = finished_session()
    out, got = export(env, sid, start=2.0, speed=2.0)
    assert got["missing"] == ["portraits/riley.png"]
    files = json_files(out)
    demo = files["demo.json"]
    assert demo["session"] == sid and demo["start"] == 2.0 and demo["speed"] == 2.0
    evs = files[f"{sid}/events.json"]
    assert evs == call("GET", f"/api/session/{sid}/events", query="since=0")[1]
    assert demo["end"] > max(e["t"] for e in evs["events"])
    assert files[f"{sid}/task.json"] == {"task": None}
    for route in ("mastery", "sponsors"):
        assert files[f"{sid}/{route}.json"] == call("GET", f"/api/session/{sid}/{route}")[1]
    assert files["bench.json"] == call("GET", "/api/bench")[1]
    tables = files[f"{sid}/tables.json"]
    assert [t["name"] for t in tables] == ["visits", "customers", "stores"]
    for t in tables:   # every row, not one page
        assert len(files[f"{sid}/rows/{t['name']}.json"]["rows"]) == t["rowCount"]
        assert f"{sid}/profile/{t['name']}.json" in files
    agents = {a["id"]: a["portrait"] for a in files["agents.json"]}
    assert agents == {**{a: f"recorded/portraits/{a}.png" for a in AGENT_IDS[:-1]}, "riley": None}
    for a in AGENT_IDS[:-1]:
        assert (out / "portraits" / f"{a}.png").read_bytes() == b"\x89PNG portrait"
    voiced = {e["data"]["file"] for e in evs["events"] if e["k"] == "voice.line"}
    assert voiced and {p.name for p in (out / "audio").iterdir()} == voiced
    assert files[f"{sid}/t1/tables.json"] == tables   # the per-task copy, so the page never meets a 404
    assert not (out.parent / "recorded.export-tmp").exists()


def test_rotation_export_has_each_tasks_tables(env):
    sid = finished_session("rotation")
    out, _ = export(env, sid)
    files = json_files(out)
    for t in ("t1", "t2", "t3"):
        tables = files[f"{sid}/{t}/tables.json"]
        assert tables == call("GET", f"/api/session/{sid}/tables", query=f"task={t}")[1]
        for tab in tables:
            assert len(files[f"{sid}/{t}/rows/{tab['name']}.json"]["rows"]) == tab["rowCount"]


def test_export_holds_no_key_no_env_value_and_no_local_path(env):
    sid = finished_session()
    out, _ = export(env, sid)
    assert export_static.scan(out, sid, [STUB_KEY]) == []
    secrets = export_static.env_values()   # the real .env, when there is one: names only in messages
    blobs = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    held = sorted({name for name, v in secrets.items() for b in blobs.values() if v.encode() in b})
    assert held == [], f"the export holds the value of .env {held}"
    for rel, data in json_files(out).items():
        text = json.dumps(data)
        for word in ("localhost", "127.0.0.1", "file://", str(export_static.ROOT)):
            assert word not in text, (rel, word)
        found: set = set()
        export_static._walk_keys(data, found)
        assert not found, (rel, found)
        for s in strings(data):
            assert not s.startswith("/"), (rel, s[:60])
        for c in STUB_KEY["checks"]:
            assert c["sql"] not in text, rel
    evs = json_files(out)[f"{sid}/events.json"]["events"]
    answered = next(e["seq"] for e in evs if e["k"] == "learner.answer")
    for e in evs:
        if e["seq"] >= answered:
            break
        d = {k: v for k, v in (e.get("data") or {}).items() if not (e["k"] == "panel.whisper" and k == "text")}
        shown = json.dumps({**e, "data": d}).lower()
        assert STUB_KEY["trap"] not in shown and STUB_KEY["careless"]["note"].lower() not in shown, e["seq"]
        assert STUB_KEY["careful"]["note"].lower() not in shown, e["seq"]
    sealed = {"key.json", ".state.json"}
    assert not [p for p in out.rglob("*") if p.name in sealed or p.name.endswith(".state.json")]


def test_scan_catches_each_kind_of_leak(env):
    sid = finished_session()
    out, _ = export(env, sid)
    (out / "key.json").write_text(json.dumps(STUB_KEY))                                    # a sealed file
    sponsors = out / sid / "sponsors.json"
    sponsors.write_text(json.dumps({"careless": STUB_KEY["careless"]}))                   # a key field
    mastery = out / sid / "mastery.json"
    mastery.write_text(json.dumps({"img": "http://localhost:8790/api/x", "p": str(out)}))   # local paths
    tables = out / sid / "tables.json"
    tables.write_text(json.dumps([{"sql": STUB_KEY["checks"][0]["sql"]}]))                 # a check's SQL
    (out / "audio" / next((out / "audio").iterdir()).name).write_bytes(b"x sk-test-not-a-real-key-123 x")
    path = out / sid / "events.json"
    log = json.loads(path.read_text())
    first = next(e for e in log["events"] if e["k"] == "agent.say")
    first["text"] = "Watch the West region: its spend is in cents."                                 # the trap, early
    path.write_text(json.dumps(log))
    problems = export_static.scan(out, sid, [STUB_KEY], {"FAKE_API_KEY": "sk-test-not-a-real-key-123"})
    said = "\n".join(problems)
    assert "key.json: not a file the static replay reads" in said
    assert f"{sid}/sponsors.json: has the answer-key field 'careless'" in said
    assert "mastery.json: has a local path or URL (localhost)" in said
    assert "(/private/)" in said or "(/Users/)" in said
    assert f"{sid}/tables.json: has a check's SQL from the key" in said
    assert "holds the value of .env FAKE_API_KEY" in said and "sk-test" not in said
    assert f"seq {first['seq']} (agent.say): points at the trap before the answer" in said


def test_a_failed_scan_writes_nothing(env, monkeypatch):
    sid = finished_session()
    monkeypatch.setattr(export_static, "scan", lambda *a, **k: ["something leaked"])
    out = env["tmp"] / "site" / "recorded"
    with pytest.raises(export_static.ExportError, match="leak scan"):
        export_static.export(sid, out, audio_dir=env["audio"], portraits_dir=env["portraits"])
    assert not out.exists() and not (out.parent / "recorded.export-tmp").exists()


def test_only_a_finished_session_exports(env):
    sid = call("POST", "/api/session/start", {"mode": "judge"})[1]["sessionId"]
    wait_for(sid, opened("t1"))
    with pytest.raises(export_static.ExportError, match="not finished"):
        export(env, sid)
    other = env["tmp"] / "busy"
    other.mkdir()
    (other / "notes.txt").write_text("keep me")
    with pytest.raises(export_static.ExportError, match="other files"):
        export_static.export(sid, other)
    assert (other / "notes.txt").read_text() == "keep me"
    assert export_static.main([sid, "--out", str(env["tmp"] / "x")]) == 1

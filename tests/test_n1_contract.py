"""The contract files agree with each other."""

import csv
import json
import re
from pathlib import Path

CONTRACT = Path(__file__).resolve().parent.parent / "contract"
ENVELOPE = ["seq", "t", "k", "agent", "why"]
AGENTS = {"vale", "ines", "sam", "telem", "riley", "learner", "system"}
TRAPS = {"duplicate_rows", "unit_mismatch", "dictionary_flip", "confounder", "hidden_variable", "none"}
VERDICTS = {"holds", "fails", "cant_tell"}
COLUMN_TYPES = {"text", "int", "real", "date"}


def kinds() -> set[str]:
    text = (CONTRACT / "events.md").read_text()
    return set(re.findall(r"^- `([a-z]+(?:\.[a-z]+)?)`", text, flags=re.M))


def mock_events() -> list[dict]:
    lines = (CONTRACT / "mock_session.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_events_md_lists_kinds():
    assert {"session.start", "agent.say", "verdict", "sponsor.call", "mastery.update", "ask"} <= kinds()


def test_mock_session_envelope():
    events = mock_events()
    assert events, "mock session is empty"
    for i, e in enumerate(events, start=1):
        for field in ENVELOPE:
            assert field in e, f"event {i} lacks {field}"
        assert e["seq"] == i
        assert e["why"].strip()
        assert e["agent"] in AGENTS
        assert e.get("to", "learner") in AGENTS
        assert e["k"] in kinds(), f"unknown kind {e['k']}"
    times = [e["t"] for e in events]
    assert times == sorted(times), "t goes backwards"


def test_mock_session_covers_the_flow():
    seen = {e["k"] for e in mock_events()}
    for kind in ["session.start", "task.picked", "learner.query", "learner.answer", "rival.answer",
                 "panel.whisper", "check.result", "verdict", "mastery.update", "session.end"]:
        assert kind in seen


def test_values_the_front_end_reads():
    for e in mock_events():
        d = e.get("data", {})
        if e["k"] in ("learner.answer", "rival.answer"):
            assert d["verdict"] in VERDICTS and d["trap"] in TRAPS
        if e["k"] == "verdict":
            assert d["result"] in ("passed", "failed") and d["taskId"]
        if e["k"] == "task.picked":
            assert {"taskId", "title", "brief", "seconds", "dictionary"} <= set(d) and d["seconds"] > 0
        if e["k"] == "mastery.update":
            assert d["trap"] in TRAPS and 0 <= d["from"] <= 1 and 0 <= d["to"] <= 1
        if e["k"] == "sponsor.call":
            assert e["agent"] == "system" and {"sponsor", "label", "count"} <= set(d)


def test_trap_never_sent_before_the_verdict():
    for e in mock_events():
        if e["k"] == "verdict":
            break
        if e["k"] in ("task.picked", "agent.say", "search", "meter.update"):
            assert "unit_mismatch" not in json.dumps(e), f"trap leaked in seq {e['seq']}"


def test_voice_lines_point_at_says():
    events = {e["seq"]: e for e in mock_events()}
    for e in events.values():
        if e["k"] == "voice.line":
            assert events[e["data"]["lineOf"]]["k"] == "agent.say"
            assert e["data"]["file"]


def test_mock_task_tables_match_tables_json():
    task = json.loads((CONTRACT / "mock_task" / "task.json").read_text())
    assert {"id", "title", "brief", "seconds", "claim", "tier", "dictionary"} <= set(task)
    tables = json.loads((CONTRACT / "mock_task" / "tables.json").read_text())
    for table in tables:
        with open(CONTRACT / "mock_task" / f"{table['name']}.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == table["rowCount"]
        assert list(rows[0]) == [c["name"] for c in table["columns"]]
        assert {c["type"] for c in table["columns"]} <= COLUMN_TYPES
        keys = [r[table["key"]] for r in rows]
        assert len(keys) == len(set(keys))


def test_whispers_wait_for_the_transcript():
    events = mock_events()
    opened = set()
    for e in events:
        if e["k"] == "panel.transcript":
            opened |= {w["seq"] for w in e["data"]["whispers"]}
            assert all(w["text"] for w in e["data"]["whispers"])
        if e["k"] == "panel.whisper":
            assert "text" not in e["data"] and e["data"]["sealed"] is True
    assert opened == {e["seq"] for e in events if e["k"] == "panel.whisper"}


def test_checks_agree_with_the_bruin_call():
    events = mock_events()
    checks = [e for e in events if e["k"] == "check.result"]
    assert sorted(c["data"]["trap"] for c in checks) == sorted(TRAPS - {"none"})
    assert sum(not c["data"]["passed"] for c in checks) == 1
    for e in events:
        if e["k"] == "sponsor.call":
            d = e["data"]
            assert not d.get("failed")
            # A Glasser lookup already bought this session is free: count 0, cost 0.
            assert d["count"] == 1 or (d["count"] == 0 and d["sponsor"] == "glasser" and d.get("cost") == 0)


def test_bench_route_reads_bruin_then_the_csv(tmp_path, monkeypatch):
    import duckdb
    from lab.session import api, bench
    header = "split,dimension,system,macro_f1,n,record\n"
    csv_file = tmp_path / "results.csv"
    csv_file.write_text(header + "test,Actionability,panel-opus-tuned,,1547,70.9\n"
                                 "dev-B,Actionability,panel-opus-tuned,69.8,411,70.9\n")
    monkeypatch.setattr(bench, "WAREHOUSE", tmp_path / "missing.duckdb")
    monkeypatch.setattr(bench, "RESULTS_CSV", csv_file)
    monkeypatch.setattr(bench, "README", tmp_path / "README.md")   # no README: the built-in lines
    status, got = api.handle("GET", "/api/bench", "", None)
    assert status == 200 and got["source"] == "csv" and len(got["lines"]) == 3
    assert got["rows"] == [
        {"split": "dev-B", "dimension": "Actionability", "system": "panel-opus-tuned", "macro_f1": 69.8, "n": 411,
         "record": 70.9},
        {"split": "test", "dimension": "Actionability", "system": "panel-opus-tuned", "macro_f1": None, "n": 1547,
         "record": 70.9}]
    wh = tmp_path / "warehouse.duckdb"
    con = duckdb.connect(str(wh))
    con.execute("create schema learn")
    con.execute("create table learn.bench_results as select 'dev-A' as split, 'Mistake_Location' as dimension, "
                "'single-opus-start' as system, 55.0::double as macro_f1, 400::bigint as n, '59.8' as record")
    con.close()
    monkeypatch.setattr(bench, "WAREHOUSE", wh)
    (tmp_path / "README.md").write_text("# Bench\n\n## Demo lines\n\nText:\n\n    one\n    two\n    three\n\n## Next\n")
    got = api.handle("GET", "/api/bench", "", None)[1]
    assert got["source"] == "bruin" and got["lines"] == ["one", "two", "three"]
    assert got["rows"] == [{"split": "dev-A", "dimension": "Mistake_Location", "system": "single-opus-start",
                            "macro_f1": 55.0, "n": 400, "record": 59.8}]   # record is text in Bruin, a number here

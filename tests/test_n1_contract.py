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

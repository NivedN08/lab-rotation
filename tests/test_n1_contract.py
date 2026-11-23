"""The contract files agree with each other."""

import csv
import json
import re
from pathlib import Path

CONTRACT = Path(__file__).resolve().parent.parent / "contract"
ENVELOPE = ["seq", "ts", "session", "kind", "agent", "why"]
AGENTS = {"vale", "ines", "sam", "telem", "riley", "learner", "system"}


def kinds() -> set[str]:
    text = (CONTRACT / "events.md").read_text()
    return set(re.findall(r"^- \*\*`([a-z.]+)`\*\*", text, flags=re.M))


def mock_events() -> list[dict]:
    lines = (CONTRACT / "mock_session.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_events_md_lists_kinds():
    assert {"session.start", "agent.say", "verdict", "sponsor.call", "mastery.update"} <= kinds()


def test_mock_session_envelope():
    events = mock_events()
    assert events, "mock session is empty"
    for i, e in enumerate(events, start=1):
        for field in ENVELOPE:
            assert field in e, f"event {i} lacks {field}"
        assert e["seq"] == i
        assert e["why"].strip()
        assert e["agent"] in AGENTS
        assert e["kind"] in kinds(), f"unknown kind {e['kind']}"
    stamps = [e["ts"] for e in events]
    assert stamps == sorted(stamps), "timestamps go backwards"


def test_mock_session_covers_the_flow():
    seen = {e["kind"] for e in mock_events()}
    for kind in ["session.start", "task.picked", "learner.query", "learner.answer", "rival.answer",
                 "panel.whisper", "check.result", "verdict", "mastery.update", "session.end"]:
        assert kind in seen


def test_voice_lines_point_at_says():
    events = {e["seq"]: e for e in mock_events()}
    for e in events.values():
        if e["kind"] == "voice.line":
            assert events[e["data"]["line_of"]]["kind"] == "agent.say"


def test_mock_task_tables_match_task_json():
    task = json.loads((CONTRACT / "mock_task" / "task.json").read_text())
    for table in task["tables"]:
        with open(CONTRACT / "mock_task" / f"{table['name']}.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == table["rows"]
        assert list(rows[0]) == [c["name"] for c in table["columns"]]
        keys = [r[table["key"]] for r in rows]
        assert len(keys) == len(set(keys))

"""Mock mode: replay `contract/mock_session.jsonl` at real speed and serve `contract/mock_task/`.

Every route of `contract/api.md` answers. Each mock session has its own clock that starts
when the session starts (or when an unknown id is first polled), and events are released
when their `t` has passed, times `LAB_MOCK_SPEED`. SQL, rows and profiles run for real on
the mock task's tables; answer, appeal and ask take canned replies and change nothing.
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import threading
import time

from lab.session import summary
from lab.session.tables import TaskTables

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contract"
PREFIX = "mock-"

CANNED = {
    "vale": ("You were new, so every skill sat at 0.15. The bandit's draw was highest for unit mix-ups, "
             "a very common trap in real exports.", ["your learner profile", "the bandit's draw for this task"]),
    "ines": ("I grade against the answer key and the Bruin checks. I can't say more before the verdict.",
             ["the answer key (sealed until the verdict)", "the Bruin check output"]),
    "sam": ("Look at how spend is spread, not only its average. Is every row in the same unit?",
            ["your queries so far", "the struggle meter"]),
    "telem": ("A chain once restated a region's sales because its export used cents. The source is on the card.",
              ["Telem's search results"]),
    "riley": ("I took the overall average by loyalty flag. Members came out 2.4 times higher, so it holds.",
              ["the public tables"]),
}


def speed() -> float:
    try:
        return max(0.01, float(os.environ.get("LAB_MOCK_SPEED") or 1.0))
    except ValueError:
        return 1.0


def is_on() -> bool:
    return os.environ.get("LAB_MOCK", "").strip().lower() in ("1", "true", "yes", "on")


class MockEngine:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        lines = (CONTRACT / "mock_session.jsonl").read_text().splitlines()
        self.script = [json.loads(line) for line in lines if line.strip()]
        self.task = json.loads((CONTRACT / "mock_task" / "task.json").read_text())
        self._tables: TaskTables | None = None
        self._starts: dict[str, float] = {}
        self._lock = threading.Lock()
        self._appeals = 0

    @property
    def tables_box(self) -> TaskTables:
        with self._lock:
            if self._tables is None:
                self._tables = TaskTables(CONTRACT / "mock_task")
            return self._tables

    def owns(self, session_id: str) -> bool:
        return session_id.startswith(PREFIX)

    def _start(self, session_id: str) -> float:
        with self._lock:
            return self._starts.setdefault(session_id, self.clock())

    def elapsed(self, session_id: str) -> float:
        return (self.clock() - self._start(session_id)) * speed()

    def released(self, session_id: str) -> list[dict]:
        now = self.elapsed(session_id)
        return [e for e in self.script if e["t"] <= now]

    # ----------------------------------------------------------------------------- routes
    def start_session(self, mode: str = "judge", learner: str | None = None) -> dict:
        sid = PREFIX + secrets.token_hex(4)
        self._start(sid)
        return {"sessionId": sid, "tasks": [{"id": self.task["id"], "title": self.task["title"]}], "task": self.task}

    def current_task(self, session_id: str) -> dict | None:
        done = any(e["k"] == "session.end" for e in self.released(session_id))
        return None if done else self.task

    def tables(self, session_id: str) -> list[dict]:
        return self.tables_box.tables()

    def rows(self, session_id: str, table: str, offset: int, limit: int) -> dict:
        return self.tables_box.rows(table, offset, limit)

    def profile(self, session_id: str, table: str) -> dict:
        return self.tables_box.profile(table)

    def events_since(self, session_id: str, since: int) -> dict:
        out = [e for e in self.released(session_id) if e["seq"] > since]
        return {"events": out, "next": out[-1]["seq"] if out else since}

    def sql(self, session_id: str, sql: str) -> dict:
        res = self.tables_box.query(sql)
        if "error" in res:
            return {"error": res["error"]}
        return res

    def on_answer(self, session_id: str, body: dict) -> dict:
        return {"accepted": True}

    def on_appeal(self, session_id: str, body: dict) -> dict:
        with self._lock:
            self._appeals += 1
            return {"appealId": f"a{self._appeals}"}

    def on_appeal_message(self, session_id: str, appeal_id: str, body: dict) -> dict:
        return {"ok": True}

    def mastery(self, session_id: str) -> dict:
        return summary.mastery_from_events(self.released(session_id))

    def ask(self, session_id: str, agent: str, text: str) -> dict:
        reply, sources = CANNED[agent]
        return {"agent": agent, "text": reply, "sources": sources}

    def sponsor_totals(self, session_id: str) -> dict:
        return summary.sponsor_totals(self.released(session_id))

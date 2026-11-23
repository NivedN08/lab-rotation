"""A session's event log: append-only JSON lines in `data/sessions/<sessionId>.jsonl`.

Events follow `contract/events.md`: `{seq, t, k, agent, why, to?, task?, text?, data?}`.
`seq` runs 1, 2, 3 ... with no gaps, `t` is seconds since the session started, and `why`
is never empty. Appends use the same locking as summit-lab's `lab.eventlog.JsonlEventLog`
(a thread lock plus an exclusive fcntl lock, fsync after each line), so the file is the
record and a restarted server picks the session up from it.

`LAB_SESSIONS_DIR` overrides the folder (tests use a temporary one).
"""

from __future__ import annotations

import fcntl
import json
import os
import pathlib
import re
import threading
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENTS = ("vale", "ines", "sam", "telem", "riley", "learner", "system")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def sessions_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("LAB_SESSIONS_DIR") or ROOT / "data" / "sessions")


def session_path(session_id: str) -> pathlib.Path:
    if not ID_RE.match(session_id or ""):
        raise ValueError("bad session id")
    return sessions_dir() / f"{session_id}.jsonl"


def read_events(path: pathlib.Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, "rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_SH)
        try:
            raw = handle.read()
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    out = []
    for line in raw.decode().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                break   # a torn last line from a crash: stop at the last whole event
    return out


class SessionLog:
    """The events of one session, in memory and on disk."""

    def __init__(self, session_id: str, path: pathlib.Path | None = None, clock=time.time):
        self.id = session_id
        self.path = path or session_path(session_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._clock = clock
        self.events: list[dict] = read_events(self.path)
        self.started = self._clock() - (self.events[-1]["t"] if self.events else 0.0)
        if self.events and self.events[0].get("data", {}).get("startedAt"):
            self.started = float(self.events[0]["data"]["startedAt"])

    @property
    def last_seq(self) -> int:
        return self.events[-1]["seq"] if self.events else 0

    def now(self) -> float:
        return round(max(0.0, self._clock() - self.started), 3)

    def append(self, k: str, agent: str, why: str, *, to: str | None = None, task: str | None = None,
               text: str | None = None, data: dict | None = None, t: float | None = None) -> dict:
        """Add one event and return it."""
        if not isinstance(why, str) or not why.strip():
            raise ValueError(f"event {k} needs a why")
        if agent not in AGENTS:
            raise ValueError(f"unknown agent {agent}")
        if to is not None and to not in AGENTS:
            raise ValueError(f"unknown agent {to}")
        with self._lock:
            when = self.now() if t is None else round(float(t), 3)
            if self.events:
                when = max(when, self.events[-1]["t"])
            event: dict[str, Any] = {"seq": self.last_seq + 1, "t": when, "k": k, "agent": agent, "why": why.strip()}
            if to is not None:
                event["to"] = to
            if task is not None:
                event["task"] = task
            if text is not None:
                event["text"] = text
            if data:
                event["data"] = data
            line = (json.dumps(event, ensure_ascii=False, default=str) + "\n").encode()
            with open(self.path, "ab") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    handle.write(line)
                    handle.flush()
                    os.fsync(handle.fileno())
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)
            self.events.append(event)
            return event

    def since(self, seq: int) -> list[dict]:
        with self._lock:
            return [e for e in self.events if e["seq"] > seq]

    def of_kind(self, *kinds: str) -> list[dict]:
        with self._lock:
            return [e for e in self.events if e["k"] in kinds]

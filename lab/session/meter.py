"""The struggle meter: deterministic, from the session log only.

For the current task:
- a query is **useful** when it ran and touches a column that matters (the key's
  `columns`) that no earlier successful query of this task touched;
- a **dead end** is a query that failed, or ran but was not useful (`select *` included);
- **wrong guesses** are wrong answers earlier in this session;
- **idle seconds** run from the last useful query (or the task's start).

    value = min(1, 0.45 * min(idle / 60, 1) + 0.12 * deadEnds + 0.1 * wrongGuesses)

discounted by a third right after a useful query. Hint level: 0 below 0.6, 1 from 0.6,
2 from 0.75, 3 from 0.9. Sam offers a hint when the level rises above the hints given.
"""

from __future__ import annotations

import re

WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
LEVELS = (0.6, 0.75, 0.9)


def columns_in(sql: str, relevant: set[str]) -> set[str]:
    """The relevant column names a query mentions (case-insensitive, whole words)."""
    words = {w.lower() for w in WORD.findall(sql or "")}
    return {c for c in relevant if c.lower() in words}


def is_useful(sql: str, ok: bool, relevant: set[str], seen: set[str]) -> bool:
    return bool(ok) and bool(columns_in(sql, relevant) - seen)


def hint_level(value: float) -> int:
    return sum(value >= cut for cut in LEVELS)


def reading(events: list[dict], task: str, now: float, wrong_guesses: int = 0) -> dict:
    """The meter for one task at time `now` (seconds since the session started)."""
    start, last_useful, dead_ends, just_useful = None, None, 0, False
    for e in events:
        if e.get("task") != task:
            continue
        if e["k"] == "task.picked" and start is None:
            start = e["t"]
        if e["k"] == "learner.query":
            d = e.get("data") or {}
            if d.get("useful"):
                last_useful, just_useful = e["t"], True
            else:
                dead_ends += 1
                just_useful = False
    anchor = last_useful if last_useful is not None else (start if start is not None else now)
    idle = max(0.0, now - anchor)
    value = 0.45 * min(idle / 60.0, 1.0) + 0.12 * dead_ends + 0.1 * wrong_guesses
    if just_useful:
        value *= 2 / 3
    value = round(min(1.0, value), 2)
    return {"value": value, "idleSeconds": round(idle), "deadEnds": dead_ends,
            "wrongGuesses": wrong_guesses, "hintLevel": hint_level(value)}


def why(reading_: dict, after_query: bool = False) -> str:
    """The reason for a meter.update, in plain words. It never says whether the last query
    was useful: that would tell the learner which columns matter."""
    if after_query:
        return "the learner ran a query"
    parts = []
    if reading_["deadEnds"]:
        parts.append(f"{reading_['deadEnds']} dead end{'s' if reading_['deadEnds'] != 1 else ''}")
    if reading_["idleSeconds"] >= 20:
        parts.append(f"{reading_['idleSeconds']} s without a useful query")
    if reading_["wrongGuesses"]:
        parts.append(f"{reading_['wrongGuesses']} wrong answer{'s' if reading_['wrongGuesses'] != 1 else ''} so far")
    return " and ".join(parts) or "the learner is working"

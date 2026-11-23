"""Read-side views computed from a session's events: sponsor totals, mastery, demo settings."""

from __future__ import annotations

import os

TRAPS = ["duplicate_rows", "unit_mismatch", "dictionary_flip", "confounder", "hidden_variable", "none"]
PRIOR = 0.15


def sponsor_totals(events: list[dict]) -> dict:
    """The `SponsorTotals` shape of `contract/api.md`, summed over `sponsor.call` events."""
    out = {"band": {"messages": 0},
           "telem": {"searches": 0, "monitorHits": 0, "traces": []},
           "bruin": {"checksRun": 0, "checksFailed": 0},
           "runware": {"lines": 0, "cost": 0.0},
           "glasser": {"calls": 0},
           "teamily": {"posts": 0}}
    for e in events:
        if e.get("k") == "monitor.hit":
            out["telem"]["monitorHits"] += 1
            tr = (e.get("data") or {}).get("trace")
            if tr and tr not in out["telem"]["traces"]:
                out["telem"]["traces"].append(tr)
        if e.get("k") == "check.result":
            out["bruin"]["checksRun"] += 1
            if not (e.get("data") or {}).get("passed", True):
                out["bruin"]["checksFailed"] += 1
        if e.get("k") != "sponsor.call":
            continue
        d = e.get("data") or {}
        n = int(d.get("count") or 1)
        sp, op = d.get("sponsor"), d.get("op")
        if sp == "band":
            out["band"]["messages"] += n
        elif sp == "telem":
            if op in ("search", "fetch"):
                out["telem"]["searches"] += n
            if d.get("trace") and d["trace"] not in out["telem"]["traces"]:
                out["telem"]["traces"].append(d["trace"])
        elif sp == "runware":
            if op == "tts":
                out["runware"]["lines"] += n
            out["runware"]["cost"] = round(out["runware"]["cost"] + float(d.get("cost") or 0.0), 6)
        elif sp == "glasser":
            out["glasser"]["calls"] += n
        elif sp == "teamily":
            out["teamily"]["posts"] += n
    return out


def mastery_from_events(events: list[dict], prior: dict | None = None) -> dict:
    """`{traps: [{trap, score, attempts}]}` from `mastery.update` events over a starting point."""
    state = {t: {"trap": t, "score": PRIOR, "attempts": 0} for t in TRAPS}
    for row in (prior or {}).get("traps", []):
        if row.get("trap") in state:
            state[row["trap"]] = {"trap": row["trap"], "score": float(row.get("score", PRIOR)),
                                  "attempts": int(row.get("attempts", 0))}
    for e in events:
        if e.get("k") == "mastery.update":
            d = e.get("data") or {}
            if d.get("trap") in state:
                state[d["trap"]]["score"] = float(d.get("to", state[d["trap"]]["score"]))
                state[d["trap"]]["attempts"] = int(d.get("attempts", state[d["trap"]]["attempts"] + 1))
    return {"traps": [state[t] for t in TRAPS]}


def _num(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def demo() -> dict:
    """`GET /api/demo`: the recorded session to replay, from LAB_DEMO_* settings."""
    session = os.environ.get("LAB_DEMO_SESSION", "").strip()
    if not session:
        return {"session": None}
    return {"session": session, "start": _num("LAB_DEMO_START") or 0.0, "end": _num("LAB_DEMO_END"),
            "speed": _num("LAB_DEMO_SPEED") or 1.0}

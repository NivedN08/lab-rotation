"""Adapters from the engine to N3 (tasks, SQL, checks, learner) and N2 (BAND, Telem, Runware).

Each adapter calls the other stream's module when it is there and falls back to a
built-in stand-in when it is missing or raises, so a session never stops on a missing
piece. What each fallback did is visible in the log (`fallback: true`, `local: true`,
`provider: "browser"`, `cached: true`).
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import random
import threading
import time
import uuid
from dataclasses import dataclass, field

from lab.session import fallback
from lab.session.summary import PRIOR, TRAPS
from lab.session.tables import TaskTables

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _log(msg: str) -> None:
    import sys
    print(f"[engine] {msg}", file=sys.stderr, flush=True)


def _get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


# ------------------------------------------------------------------------------ task bank

@dataclass
class BankTask:
    bank_id: str
    public: dict
    dir: str
    key: dict
    stub: bool = False


def normalize_key(raw) -> dict:
    """The fields the engine reads from a bank key, with safe defaults."""
    raw = raw if isinstance(raw, dict) else (vars(raw) if raw is not None else {})
    careful = raw.get("careful") or {}
    trap = raw.get("trap") or careful.get("trap") or "none"
    verdict = raw.get("verdict") or raw.get("correct_verdict") or raw.get("correctVerdict") or \
        careful.get("verdict") or "holds"
    careless = raw.get("careless") or {"verdict": "holds" if verdict != "holds" else "fails",
                                       "trap": "none" if trap != "none" else "duplicate_rows",
                                       "note": "I compared the averages and stopped there."}
    cols = raw.get("columns") or raw.get("key_columns") or raw.get("keyColumns") or []
    return {"trap": trap, "verdict": verdict, "careful": careful, "careless": careless,
            "columns": [str(c) for c in cols], "hints": raw.get("hints") or fallback.HINTS.get(trap, []),
            "checks": raw.get("checks") or []}


def bank_pick(skill: str, tier: int, seen: list[str]) -> str | None:
    try:
        from lab.tasks import bank   # N3
        got = bank.pick(skill, tier, seen)
        if isinstance(got, (list, tuple)):
            got = got[0] if got else None
        if isinstance(got, dict):
            got = got.get("id") or got.get("bank_id")
        return str(got) if got else None
    except Exception as e:   # missing module or a bad pick: the stub task answers
        _log(f"bank.pick unavailable ({type(e).__name__}); using the stub task")
        return None


def bank_load(bank_id: str | None) -> BankTask:
    if bank_id and bank_id != fallback.STUB_ID:
        try:
            from lab.tasks import bank   # N3
            raw = bank.load(bank_id)
            public = _get(raw, "public") or _get(raw, "task")
            folder = _get(raw, "dir") or _get(raw, "public_dir")
            key = _get(raw, "key")
            if public and folder and key is not None:
                if isinstance(public, (str, pathlib.Path)):
                    public = json.loads(pathlib.Path(public).read_text())
                return BankTask(bank_id, dict(public), str(folder), normalize_key(key))
            _log(f"bank.load({bank_id}) lacked public/dir/key; using the stub task")
        except Exception as e:
            _log(f"bank.load unavailable ({type(e).__name__}); using the stub task")
    s = fallback.stub_task()
    return BankTask(s["id"], s["public"], s["dir"], normalize_key(s["key"]), stub=True)


# ------------------------------------------------------------------------- SQL workspace

_boxes: dict[str, TaskTables] = {}
_boxes_lock = threading.Lock()


def _box(folder: str) -> TaskTables:
    with _boxes_lock:
        if folder not in _boxes:
            _boxes[folder] = TaskTables(folder)
        return _boxes[folder]


def _ws():
    try:
        from lab import workspace_sql   # N3
        return workspace_sql
    except Exception:
        return None


def ws_tables(folder: str) -> list[dict]:
    ws = _ws()
    return ws.tables(folder) if ws else _box(folder).tables()


def ws_rows(folder: str, table: str, offset: int, limit: int) -> dict:
    ws = _ws()
    return ws.table_rows(folder, table, offset, limit) if ws else _box(folder).rows(table, offset, limit)


def ws_profile(folder: str, table: str) -> dict:
    ws = _ws()
    return ws.profile(folder, table) if ws else _box(folder).profile(table)


def ws_query(folder: str, sql: str) -> dict:
    ws = _ws()
    res = ws.run_query(folder, sql) if ws else _box(folder).query(sql)
    if "error" in res:
        return {"error": res["error"], "ms": res.get("ms", 0)}
    return res


# --------------------------------------------------------------------------------- checks

def run_checks(task: BankTask) -> tuple[list[dict], dict]:
    """(check.result data list, sponsor.call data for the Bruin run)."""
    start = time.monotonic()
    if not task.stub:
        try:
            from lab.tasks import checks   # N3
            got = checks.run(task.bank_id)
            out = [dict(c) for c in got]
            if out:
                ms = int((time.monotonic() - start) * 1000)
                failed = sum(1 for c in out if not c.get("passed", True))
                return out, {"sponsor": "bruin", "label": f"ran {len(out)} quality checks, {failed} failed",
                             "count": 1, "op": "check", "by": "ines", "ms": ms, "fallback": False}
        except Exception as e:
            _log(f"checks.run unavailable ({type(e).__name__}); running the key's checks locally")
    out = []
    run_id = "local-" + uuid.uuid4().hex[:6]
    for c in task.key.get("checks") or []:
        if not isinstance(c, dict) or not c.get("sql"):
            continue
        res = ws_query(task.dir, c["sql"])
        if "error" in res:
            continue
        rows = res.get("rows") or []
        passed = not rows
        out.append({"check": c["check"], "trap": c.get("trap", task.key["trap"]), "passed": passed,
                    "detail": c["pass"] if passed else c["fail"], "bruinRun": run_id,
                    **({} if passed else {"rows": rows[:5]})})
    if not out:   # no runnable checks: report the key's trap as one failing check
        trap = task.key["trap"]
        out.append({"check": f"{trap}.key", "trap": trap, "passed": trap == "none",
                    "detail": "the answer key's own check", "bruinRun": run_id})
    ms = int((time.monotonic() - start) * 1000)
    return out, {"sponsor": "bruin", "label": f"ran {len(out)} quality checks (local copy)", "count": 1,
                 "op": "check", "by": "ines", "ms": ms, "fallback": True}


# -------------------------------------------------------------------------- learner model

LEARNERS = ROOT / "data" / "learners"
BKT = {"learn": 0.2, "slip": 0.1, "guess": 0.2}
_learn_lock = threading.Lock()


def _learner_file(learner: str) -> pathlib.Path:
    return pathlib.Path(os.environ.get("LAB_LEARNERS_DIR") or LEARNERS) / f"{learner}.json"


def _fallback_state(learner: str) -> dict:
    p = _learner_file(learner)
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {t: {"score": PRIOR, "attempts": 0} for t in TRAPS}


def mastery(learner: str) -> dict:
    try:
        from lab import learner as lm   # N3
        got = lm.mastery(learner)
        if got and got.get("traps"):
            return got
    except Exception:
        pass
    st = _fallback_state(learner)
    return {"traps": [{"trap": t, "score": round(st.get(t, {}).get("score", PRIOR), 2),
                       "attempts": st.get(t, {}).get("attempts", 0)} for t in TRAPS]}


def learner_update(learner: str, trap: str, correct: bool) -> dict:
    """{trap, from, to, attempts, bruinRun?, fallback}."""
    try:
        from lab import learner as lm   # N3
        got = lm.update(learner, trap, correct)
        if got and "to" in got:
            return {"fallback": False, **got}
    except Exception:
        pass
    with _learn_lock:
        st = _fallback_state(learner)
        cur = st.get(trap, {"score": PRIOR, "attempts": 0})
        p = cur["score"]
        if correct:
            post = p * (1 - BKT["slip"]) / (p * (1 - BKT["slip"]) + (1 - p) * BKT["guess"])
        else:
            post = p * BKT["slip"] / (p * BKT["slip"] + (1 - p) * (1 - BKT["guess"]))
        new = post + (1 - post) * BKT["learn"]
        st[trap] = {"score": round(new, 4), "attempts": cur["attempts"] + 1}
        f = _learner_file(learner)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(st))
    return {"trap": trap, "from": round(p, 2), "to": round(new, 2), "correct": correct,
            "attempts": st[trap]["attempts"], "fallback": True}


def pick_next(learner: str, seen_traps: list[str], tier: int, rng: random.Random) -> dict:
    """{skill, tier, reason, fallback, bandit?}. N3's bandit, else Thompson draws over mastery."""
    try:
        from lab import learner as lm   # N3
        got = lm.pick_next(learner, seen_traps, tier)
        if got and got.get("skill") in TRAPS:
            return {"tier": tier, "fallback": False, **got}
    except Exception:
        pass
    st = mastery(learner)["traps"]
    bandit = {}
    for row in st:
        m = row["score"]
        a, b = 1 + (1 - m) * 4, 1 + m * 4   # weight towards low mastery
        bandit[row["trap"]] = {"mean": round(m, 2), "sample": round(rng.betavariate(a, b), 2)}
    choices = {t: v for t, v in bandit.items() if t not in seen_traps} or bandit
    skill = max(choices, key=lambda t: choices[t]["sample"])
    lowest = min(r["score"] for r in st)
    reason = (f"every skill sits near {lowest:.2f}, so the draw decides: this one came out highest"
              if all(abs(r["score"] - lowest) < 0.01 for r in st)
              else "the draw favours the skills you have shown least")
    return {"skill": skill, "tier": tier, "reason": reason, "fallback": True, "bandit": bandit}


# -------------------------------------------------------------------------------- sponsors

class LocalRoom:
    """The panel room when BAND is not there: same message shape, `local: True`."""

    def __init__(self):
        self.n = 0

    def health(self) -> str:
        return "local"

    def post(self, agent, text, mentions=(), **_):
        self.n += 1
        return {"id": f"local-{self.n}", "local": True}

    def relay_appeal(self, text, by="vale"):
        return self.post(by, text)


def band_room(on_call):
    """N2's BandRoom when it loads, else a LocalRoom."""
    try:
        from lab.sponsors.band import BandRoom   # N2
        return BandRoom(on_call=on_call)
    except Exception as e:
        _log(f"BAND client unavailable ({type(e).__name__}); using a local room")
        return LocalRoom()


def band_post(room, agent: str, text: str, mentions: list[str]) -> dict:
    """{id, local} for one post; never raises."""
    try:
        msg = room.post(agent, text, mentions=mentions)
        return {"id": _get(msg, "id"), "local": bool(_get(msg, "local", False))}
    except Exception as e:
        _log(f"BAND post failed ({type(e).__name__})")
        return {"id": None, "local": True}


def band_relay(room, text: str) -> dict:
    try:
        msg = room.relay_appeal(text)
        return {"id": _get(msg, "id"), "local": bool(_get(msg, "local", False))}
    except Exception as e:
        _log(f"BAND relay failed ({type(e).__name__})")
        return {"id": None, "local": True}


def telem_search(query: str, trap_for_fallback: str, on_call) -> dict:
    """{query, results, trace, cached}. Results are untrusted text; callers quote them as data."""
    try:
        from lab.sponsors import telem   # N2
        got = telem.search(query, on_call=on_call)
        if got and got.get("results") is not None:
            return {"query": got.get("query", query), "results": list(got["results"])[:3],
                    "trace": got.get("trace") or "", "cached": bool(got.get("cached", False))}
    except Exception as e:
        _log(f"Telem unavailable ({type(e).__name__}); using a recorded case")
    rec = fallback.case_for(trap_for_fallback)
    if on_call:
        on_call({"sponsor": "telem", "label": "used a recorded case", "count": 1, "op": "search",
                 "by": "telem", "ms": 0, "fallback": True})
    return rec


def tts(agent: str, text: str, on_call) -> dict:
    """{file, seconds, cost?, provider}. Browser speech when Runware is not there."""
    try:
        from lab.sponsors import runware   # N2
        got = runware.tts(agent, text, on_call=on_call)
        if got and got.get("file"):
            return {"file": pathlib.Path(str(got["file"])).name, "seconds": float(got.get("seconds") or 0),
                    "cost": float(got.get("cost") or 0), "provider": "runware"}
    except Exception:
        pass
    words = len(text.split())
    return {"file": "", "seconds": round(max(1.5, words / 2.6), 1), "provider": "browser"}


def riley_model(prompt: str, on_call) -> dict | None:
    """{text, model} from Runware's open model, or None."""
    try:
        from lab.sponsors import runware   # N2
        fn = getattr(runware, "riley", None)
        if fn:
            got = fn(prompt, on_call=on_call)
            if got and got.get("text"):
                return {"text": str(got["text"]), "model": str(got.get("model") or "open model via Runware")}
    except Exception:
        pass
    return None

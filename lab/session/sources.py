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

def n3_on() -> bool:
    """False with LAB_N3=off (tests): the stub task, local checks and the local learner model."""
    return os.environ.get("LAB_N3", "").strip().lower() not in ("off", "0", "no", "false")


@dataclass
class BankTask:
    bank_id: str
    public: dict
    dir: str
    key: dict
    stub: bool = False
    n3: object = field(default=None, repr=False)   # N3's own BankTask, for its checks


def _n3_task(raw) -> BankTask | None:
    """N3's BankTask (or a dict with the same fields) as the engine's BankTask."""
    bank_id = _get(raw, "id") or _get(raw, "bank_id") or _get(raw, "bankId")
    key = _get(raw, "key")
    folder = _get(raw, "public_dir") or _get(raw, "dir")
    pub = _get(raw, "public")
    if callable(pub):
        pub = pub("t1")   # the engine replaces the slot id
    elif pub is None:
        pub = _get(raw, "task")
    if isinstance(pub, (str, pathlib.Path)):
        pub = json.loads(pathlib.Path(pub).read_text())
    if not (bank_id and key is not None and folder and isinstance(pub, dict)):
        return None
    return BankTask(str(bank_id), dict(pub), str(folder), normalize_key(key), n3=raw)


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
    if not cols and raw.get("matters"):   # N3: ["table.column", ...]
        cols = sorted({str(c).split(".")[-1] for c in raw["matters"]})
    out = {"trap": trap, "verdict": verdict, "careful": careful, "careless": careless,
           "columns": [str(c) for c in cols], "hints": raw.get("hints") or fallback.HINTS.get(trap, []),
           "checks": raw.get("checks") or []}
    for k in ("failingCheck", "benchmark", "naive"):
        if raw.get(k) is not None:
            out[k] = raw[k]
    return out


def bank_pick(skill: str, tier: int, seen: list[str]) -> str | None:
    if not n3_on():
        return None
    try:
        from lab.tasks import bank   # N3
        got = bank.pick(skill, tier, seen)
        if isinstance(got, (list, tuple)):
            got = got[0] if got else None
        if got is not None and not isinstance(got, str):
            got = _get(got, "id") or _get(got, "bank_id")
        return str(got) if got else None
    except Exception as e:   # missing module or a bad pick: the stub task answers
        _log(f"bank.pick unavailable ({type(e).__name__}); using the stub task")
        return None


def bank_load(bank_id: str | None) -> BankTask:
    if bank_id and bank_id != fallback.STUB_ID and n3_on():
        try:
            from lab.tasks import bank   # N3
            got = _n3_task(bank.load(bank_id))
            if got:
                return got
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
    if not n3_on():
        return None
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
    if not task.stub and n3_on():
        try:
            from lab.tasks import checks   # N3
            got = checks.run_checks(task.n3 or task.dir, bruin=True)
            out = [dict(c) for c in got]
            if out:
                ms = int((time.monotonic() - start) * 1000)
                ran = not any("bruinError" in c for c in out)
                label = (f"ran {len(out)} quality checks in Bruin" if ran
                         else f"ran {len(out)} quality checks; the Bruin run failed, so DuckDB answered")
                return out, {"sponsor": "bruin", "label": label, "count": 1, "op": "check", "by": "ines",
                             "ms": ms, "fallback": not ran, **({} if ran else {"failed": True})}
        except Exception as e:
            _log(f"checks.run_checks unavailable ({type(e).__name__}); running the key's checks locally")
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
        if not n3_on():
            raise ImportError("LAB_N3=off")
        from lab import learner as lm   # N3
        got = lm.mastery(learner)
        if got and got.get("traps"):
            return got
    except Exception:
        pass
    st = _fallback_state(learner)
    return {"traps": [{"trap": t, "score": round(st.get(t, {}).get("score", PRIOR), 2),
                       "attempts": st.get(t, {}).get("attempts", 0)} for t in TRAPS]}


def learner_update(learner: str, trap: str, correct: bool, **info) -> list[dict]:
    """[mastery.update data], one per skill whose score changed: {trap, from, to, correct,
    attempts, fallback}. `info` (score, tier, session, task) goes to N3's history."""
    if n3_on():
        try:
            from lab import learner as lm   # N3
            got = lm.record(learner, trap, correct, **info)
            return [{"fallback": False, **dict(u)} for u in (got or [])]
        except Exception as e:
            _log(f"learner.record unavailable ({type(e).__name__}); using the local model")
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
    return [{"trap": trap, "from": round(p, 2), "to": round(new, 2), "correct": correct,
             "attempts": st[trap]["attempts"], "fallback": True}]


def learner_refresh(on_call) -> None:
    """N3's Bruin refresh of the learner tables (5 to 15 s), logged as one sponsor.call."""
    if not n3_on():
        return
    start = time.monotonic()
    try:
        from lab.learner import refresh   # N3
        got = refresh.refresh() or {}
    except Exception as e:
        _log(f"learner refresh unavailable ({type(e).__name__})")
        return
    b = got.get("bruin") or {}
    ok = bool(b.get("ok"))
    if on_call:
        on_call({"sponsor": "bruin", "label": "refreshed the learner model (learn.bkt_mastery)" if ok
                 else "the learner model refresh failed", "count": 1, "op": "run", "by": "system",
                 "ms": int((time.monotonic() - start) * 1000), "fallback": False,
                 **({"runId": b["runId"]} if b.get("runId") else {}), **({} if ok else {"failed": True})})


NUDGE_BOOST = 0.15   # the same tilt as N3's bandit


def pick_next(learner: str, seen_traps: list[str], seen_ids: list[str], tier: int, rng: random.Random,
              nudge: dict | None = None) -> dict:
    """{skill, tier, bankId?, reason, pickReason, fallback, bandit?, nudged, nudgeDecided, nudge}.

    N3's bandit, else Thompson draws over mastery. `nudge` ({trap, headline, url, trace}, from
    Telem's case of the day) adds NUDGE_BOOST to that skill's draw. Only `pickReason` (sent
    with task.end, after the verdict) mentions it."""
    if n3_on():
        try:
            from lab import learner as lm   # N3
            got = lm.pick_next(learner, tier=tier, seen=list(seen_ids), avoid=list(seen_traps), rng=rng,
                               nudge=nudge)
            if got and got.get("skill") in TRAPS:
                out = {k: v for k, v in dict(got).items() if k != "task"}
                out.setdefault("pickReason", out.get("reason", ""))
                return {"tier": tier, "fallback": False, "nudged": False, "nudgeDecided": False, **out}
        except Exception as e:
            _log(f"learner.pick_next unavailable ({type(e).__name__}); using local draws")
    st = mastery(learner)["traps"]
    bandit = {}
    for row in st:
        m = row["score"]
        a, b = 1 + (1 - m) * 4, 1 + m * 4   # weight towards low mastery
        bandit[row["trap"]] = {"mean": round(m, 2), "sample": round(rng.betavariate(a, b), 2)}
    choices = {t: v for t, v in bandit.items() if t not in seen_traps} or bandit
    boosted = nudge.get("trap") if nudge and nudge.get("trap") in choices else None
    if boosted:
        bandit[boosted]["boost"] = NUDGE_BOOST
    skill = max(choices, key=lambda t: choices[t]["sample"] + choices[t].get("boost", 0.0))
    plain = max(choices, key=lambda t: choices[t]["sample"])
    lowest = min(r["score"] for r in st)
    reason = (f"every skill sits near {lowest:.2f}, so the draw decides: this one came out highest"
              if all(abs(r["score"] - lowest) < 0.01 for r in st)
              else "the draw favours the skills you have shown least")
    full = f"{reason} ({skill.replace('_', ' ')}, draw {bandit[skill]['sample']:.2f})"
    nudged, decided = bool(boosted) and skill == boosted, bool(boosted) and skill == boosted and plain != boosted
    if nudge and nudge.get("trap") in bandit:
        news = (f"Telem's case of the day (\"{nudge.get('headline') or 'untitled'}\") pointed at "
                f"{nudge['trap'].replace('_', ' ')}")
        full += (f". {news}, so its draw got +{NUDGE_BOOST:.2f}" + ("; that boost decided the pick" if decided
                 else "; it was ahead without the boost") if nudged else
                 f". {news}; its draw got +{NUDGE_BOOST:.2f} but mastery still favoured another skill"
                 if boosted else f". {news}, a skill already used this session, so no boost")
    return {"skill": skill, "tier": tier, "reason": reason, "pickReason": full, "fallback": True,
            "bandit": bandit, "nudged": nudged, "nudgeDecided": decided, "nudge": nudge}


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
    if not sponsors_on():
        return LocalRoom()
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


def sponsors_on() -> bool:
    """False with LAB_SPONSORS=off (tests): no BAND, Telem or Runware calls at all."""
    return os.environ.get("LAB_SPONSORS", "").strip().lower() not in ("off", "0", "no", "false")


class Sponsors:
    """One session's sponsor clients (N2), each reporting to that session's log."""

    def _gl_report(self, call) -> None:
        self.gl_reports += 1
        if self.on_call:
            self.on_call(call)

    def __init__(self, on_call):
        self.on_call = on_call
        self.lib = self.rw = self.gl = None
        self.gl_reports = 0   # Glasser calls reported so far (a cache hit reports none)
        if not sponsors_on():
            return
        try:
            from lab.sponsors.glasser import Glasser   # N2: one per session, its "already bought" memo
            self.gl = Glasser(on_call=self._gl_report)
        except Exception as e:
            _log(f"Glasser client unavailable ({type(e).__name__})")
        try:
            from lab.sponsors.telem import Librarian   # N2
            self.lib = Librarian(on_call=on_call)
        except Exception as e:
            _log(f"Telem client unavailable ({type(e).__name__})")
        try:
            from lab.sponsors.runware import Runware   # N2
            self.rw = Runware(on_call=on_call)
        except Exception as e:
            _log(f"Runware client unavailable ({type(e).__name__})")


def _telem_result(got: dict | None, query: str) -> dict | None:
    if got and got.get("results"):
        return {"query": got.get("query", query), "results": list(got["results"])[:3],
                "trace": got.get("trace") or "", "cached": bool(got.get("cached", False))}
    return None


def telem_topic(sp: Sponsors, query: str) -> dict:
    """Before the answer: background on the claim's topic. `query` comes from the public claim
    only. {query, results, trace, cached}; results are untrusted text, quoted as data."""
    try:
        got = _telem_result(sp.lib.search(query, goal="background on a retail claim") if sp.lib else None, query)
        if got:
            return got
    except Exception as e:
        _log(f"Telem unavailable ({type(e).__name__}); using recorded background")
    if sp.on_call:
        sp.on_call({"sponsor": "telem", "label": "used recorded background", "count": 1, "op": "search",
                    "by": "telem", "ms": 0, "fallback": True})
    return fallback.topic_for(query)


def telem_case(sp: Sponsors, trap: str) -> dict:
    """After the verdict: a real case of this trap (`none`: trusting a clean result)."""
    try:
        got = sp.lib.case_for(trap) if sp.lib else None
        out = _telem_result(got, (got or {}).get("query", ""))
        if out:
            return out
    except Exception as e:
        _log(f"Telem unavailable ({type(e).__name__}); using a recorded case")
    if sp.on_call:
        sp.on_call({"sponsor": "telem", "label": "used a recorded case", "count": 1, "op": "search",
                    "by": "telem", "ms": 0, "fallback": True})
    return fallback.case_for(trap)


def telem_answer(sp: Sponsors, question: str) -> dict | None:
    """{query, results, trace, cached} for a learner's question (N2's Librarian.answer, else a
    plain search), or None. Only the question goes out; results are untrusted text."""
    if not sp.lib:
        return None
    try:
        fn = getattr(sp.lib, "answer", None)
        got = fn(question, by="telem") if fn else sp.lib.search(question, by="telem",
                                                                 goal="answer a learner's question about retail data")
        return _telem_result(got, question)
    except Exception as e:
        _log(f"Telem answer unavailable ({type(e).__name__})")
        return None


def case_of_day(sp: Sponsors) -> dict | None:
    """{title, url, trace, summary, cached, trap?} from Telem's monitor, or None."""
    try:
        got = sp.lib.case_of_day() if sp.lib else None
        if got and got.get("title"):
            return got
    except Exception as e:
        _log(f"Telem monitor unavailable ({type(e).__name__})")
    return None


def tts(sp: Sponsors, agent: str, text: str, line_of: int | None = None) -> dict:
    """{file, seconds, cost?, provider}. Browser speech when Runware is not there."""
    try:
        got = sp.rw.tts(agent, text, line_of=line_of) if sp.rw else None
        if got and got.get("file") and got.get("provider", "runware") == "runware":
            return {"file": pathlib.Path(str(got["file"])).name, "seconds": float(got.get("seconds") or 0),
                    "cost": float(got.get("cost") or 0), "provider": "runware"}
        if got:
            return {"file": "", "seconds": float(got.get("seconds") or 0) or max(1.5, len(text.split()) / 2.6),
                    "provider": "browser"}
    except Exception as e:
        _log(f"Runware voice unavailable ({type(e).__name__})")
    words = len(text.split())
    return {"file": "", "seconds": round(max(1.5, words / 2.6), 1), "provider": "browser"}


def riley_model(sp: Sponsors, system: str, user: str) -> dict | None:
    """{text, model, provider} from Runware's open model (or N2's own claude fallback), or None."""
    try:
        got = sp.rw.riley(system=system, user=user) if sp.rw else None
        if got and got.get("text"):
            prov = got.get("provider") if got.get("provider") in ("runware", "claude_fallback") else "runware"
            return {"text": str(got["text"]), "model": str(got.get("model") or "open model via Runware"),
                    "provider": prov}
    except Exception as e:
        _log(f"Runware Riley unavailable ({type(e).__name__})")
    return None


def teamily_post(session: str, tasks: list, mastery_: dict, learner: str, on_call) -> dict | None:
    if not sponsors_on():
        return None
    try:
        from lab.sponsors.teamily import Teamily   # N2
        return Teamily(on_call=on_call).post_summary(session, tasks, mastery_, learner)
    except Exception as e:
        _log(f"Teamily unavailable ({type(e).__name__})")
        return None


def glasser_params(sp: Sponsors) -> dict | None:
    """Glasser's retail numbers (N2 caches them per day), logged as one sponsor.call.

    N2's client reports live calls itself; a cache hit reports nothing, so this logs it.
    """
    if not sp.gl:
        return None
    before, start = sp.gl_reports, time.monotonic()
    try:
        got = sp.gl.retail_params()
    except Exception as e:
        _log(f"Glasser unavailable ({type(e).__name__})")
        return None
    if sp.gl_reports == before and sp.on_call:
        sp.on_call({"sponsor": "glasser", "label": "read today's retail numbers (cached)", "count": 1, "op": "run",
                    "by": "system", "ms": int((time.monotonic() - start) * 1000), "fallback": True})
    return got if isinstance(got, dict) else None


def glasser_benchmark(sp: Sponsors, kind: str, by: str) -> dict | None:
    """{kind, label, value, low, high, unit, source, cost, trace, cached} from N2's
    Glasser.benchmark on the session's one Glasser (a repeat in the session is free), or None:
    then no reality check is shown, since numbers are never made up."""
    if not sp.gl or not hasattr(sp.gl, "benchmark"):
        return None
    before, start = sp.gl_reports, time.monotonic()
    try:
        got = dict(sp.gl.benchmark(kind, by=by) or {})
    except Exception as e:
        _log(f"Glasser benchmark unavailable ({type(e).__name__})")
        return None
    if got.get("value") is None and (got.get("low") is None or got.get("high") is None):
        return None
    out = {"kind": kind, **{k: got.get(k) for k in ("label", "value", "low", "high", "unit", "source", "cost",
                                                     "trace", "cached")}}
    if sp.gl_reports == before and sp.on_call:
        sp.on_call({"sponsor": "glasser", "label": f"read the {kind} benchmark (cached)", "count": 1, "op": "run",
                    "by": by, "ms": int((time.monotonic() - start) * 1000), "fallback": True})
    return out


def from_glasser(b: dict) -> bool:
    """True when a benchmark came from a Glasser run (not a fixed planning value)."""
    src = str(b.get("source") or "") + " " + str(b.get("trace") or "")
    return "glasser.ai" in src or bool(b.get("cost"))


def _amount(x: float, money: bool) -> str:
    if money:
        return f"${x:,.0f}" if abs(x) >= 10 else f"${x:,.2f}"
    return f"{x:,.4g}"


def _money(unit: str) -> tuple[bool, str]:
    unit = str(unit or "").strip()
    if unit.upper().startswith("USD"):
        return True, unit[3:].strip()
    if unit.startswith("$"):
        return True, unit[1:].strip()
    return False, unit


def benchmark_range(b: dict) -> str:
    """'about $34 ($26 to $67)', '$30 to $45 per visit' or '1,995 stores'; built in code so the
    numbers are exactly Glasser's."""
    money, rest = _money(b.get("unit"))
    tail = f" {rest}" if rest else ""
    has_range = b.get("low") is not None and b.get("high") is not None
    rng = f"{_amount(float(b['low']), money)} to {_amount(float(b['high']), money)}" if has_range else ""
    if b.get("value") is not None:
        val = _amount(float(b["value"]), money) + tail
        return f"about {val} ({rng})" if rng else val
    return rng + tail


def benchmark_source(b: dict) -> str:
    """'Glasser ($0.008)', 'Glasser (recorded)', 'Glasser' (a free repeat) or 'a recorded planning value'."""
    if not from_glasser(b):
        return "a recorded planning value, not a live lookup"
    cost = b.get("cost")
    return "Glasser" + (f" (${float(cost):.3f})" if cost else " (recorded)" if b.get("cached") else "")


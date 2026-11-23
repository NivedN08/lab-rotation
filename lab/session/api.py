"""The `/api` routes of `contract/api.md`, as one function the HTTP server calls.

    status, reply = handle(method, path, query, body)

`web/server.py` keeps the HTTP side (summit-lab's stdlib server); this module checks the
input, picks the engine and shapes the reply. A session whose id starts with `mock-`, any
session while `LAB_MOCK=1`, and a start with `{"mock": true}` go to the mock replay;
everything else goes to the real engine (`lab.session.engine`).
"""

from __future__ import annotations

import re
import threading
from urllib.parse import parse_qs

from lab.session import cast, summary
from lab.session.mock import MockEngine, is_on as mock_on
from lab.session.tables import TableError

VERDICTS = {"holds", "fails", "cant_tell"}
TRAPS = set(summary.TRAPS)
MODES = {"rotation", "judge"}
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_TEXT = 4000
MAX_SQL = 10000


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


_mock: MockEngine | None = None
_real = None
_lock = threading.Lock()


def mock_engine() -> MockEngine:
    global _mock
    with _lock:
        if _mock is None:
            _mock = MockEngine()
        return _mock


def real_engine():
    """The live engine, built on first use. None when it cannot load (then routes answer 503)."""
    global _real
    with _lock:
        if _real is None:
            try:
                from lab.session.engine import Engine
            except ImportError:
                return None
            _real = Engine()
        return _real


def set_engines(mock=None, real=None) -> None:
    """Tests swap in their own engines."""
    global _mock, _real
    with _lock:
        _mock, _real = mock, real


def engine_for(session_id: str):
    if not ID_RE.match(session_id or ""):
        raise ApiError(400, "bad session id")
    m = mock_engine()
    if mock_on() or m.owns(session_id):
        return m
    real = real_engine()
    if real is None:
        raise ApiError(503, "the session engine is not ready yet")
    if not real.has(session_id):
        raise ApiError(404, f"no session {session_id}")
    return real


def band_status() -> str:
    try:
        from lab.sponsors import band   # N2
        status = getattr(band, "status", None)
        if callable(status):
            return "live" if status() == "live" else "local"
    except Exception:
        pass
    return "local"


# ------------------------------------------------------------------------------- inputs

def _int(query: dict, name: str, default: int, lo: int = 0, hi: int | None = None) -> int:
    raw = (query.get(name) or [None])[0]
    if raw in (None, ""):
        return default
    try:
        v = int(raw)
    except ValueError:
        raise ApiError(400, f"{name} must be a whole number") from None
    if v < lo:
        raise ApiError(400, f"{name} must be at least {lo}")
    return min(v, hi) if hi is not None else v


def _obj(body) -> dict:
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise ApiError(400, "the body must be a JSON object")
    return body


def _text(body: dict, name: str, limit: int = MAX_TEXT, required: bool = True) -> str:
    v = body.get(name)
    if v is None and not required:
        return ""
    if not isinstance(v, str) or (required and not v.strip()):
        raise ApiError(400, f"{name} must be a non-empty string")
    if len(v) > limit:
        raise ApiError(400, f"{name} is longer than {limit} characters")
    return v


def parse_answer(body: dict) -> dict:
    task_id = _text(body, "taskId", 16)
    verdict, trap = body.get("verdict"), body.get("trap")
    if verdict not in VERDICTS:
        raise ApiError(400, "verdict must be holds, fails or cant_tell")
    if trap not in TRAPS:
        raise ApiError(400, "trap must be one of the trap ids")
    evidence = body.get("evidence") or []
    if not isinstance(evidence, list) or len(evidence) > 20:
        raise ApiError(400, "evidence must be a list of at most 20 items")
    clean = []
    for item in evidence:
        if not isinstance(item, dict) or item.get("kind") not in ("row", "column", "cell") \
                or not isinstance(item.get("source"), str):
            raise ApiError(400, "each evidence item needs kind (row, column or cell) and source")
        keep = {k: item[k] for k in ("kind", "source", "sql", "row", "column", "value", "label") if k in item}
        if isinstance(keep.get("sql"), str) and len(keep["sql"]) > MAX_SQL:
            raise ApiError(400, "an evidence query is too long")
        keep["label"] = str(keep.get("label") or "")[:300]
        clean.append(keep)
    note = _text(body, "note", MAX_TEXT, required=False)
    return {"taskId": task_id, "verdict": verdict, "trap": trap, "evidence": clean, "note": note}


# ------------------------------------------------------------------------------- routes

def handle(method: str, path: str, query: str | dict = "", body=None) -> tuple[int, object]:
    """(status, JSON reply) for one `/api` request. Never raises for a bad request."""
    try:
        q = parse_qs(query) if isinstance(query, str) else query
        return 200, route(method, path.rstrip("/") or "/", q, body)
    except ApiError as e:
        return e.status, {"error": e.message}
    except TableError as e:
        return e.status, {"error": str(e)}


def route(method: str, path: str, q: dict, body):
    parts = [p for p in path.split("/") if p][1:]   # drop "api"
    if method == "GET" and parts == ["health"]:
        return {"ok": True, "mock": mock_on(), "band": band_status()}
    if method == "GET" and parts == ["agents"]:
        return cast.agents()
    if method == "GET" and parts == ["demo"]:
        return summary.demo()
    if parts[:1] != ["session"] or len(parts) < 2:
        raise ApiError(404, "unknown endpoint")

    if parts == ["session", "start"]:
        if method != "POST":
            raise ApiError(405, "use POST")
        b = _obj(body)
        mode = b.get("mode") or "rotation"
        if mode not in MODES:
            raise ApiError(400, "mode must be rotation or judge")
        learner = b.get("learner")
        if learner is not None and (not isinstance(learner, str) or not ID_RE.match(learner)):
            raise ApiError(400, "learner must be a short id")
        if mock_on() or b.get("mock") is True:
            return mock_engine().start_session(mode, learner)
        real = real_engine()
        if real is None:
            raise ApiError(503, "the session engine is not ready yet")
        return real.start_session(mode, learner)

    sid, rest = parts[1], parts[2:]
    eng = engine_for(sid)

    if method == "GET":
        if rest == ["task"]:
            return {"task": eng.current_task(sid)}
        if rest == ["tables"]:
            return eng.tables(sid)
        if len(rest) == 3 and rest[0] == "tables" and rest[2] in ("rows", "profile"):
            table = rest[1]
            if not NAME_RE.match(table):
                raise ApiError(400, "bad table name")
            if rest[2] == "rows":
                return eng.rows(sid, table, _int(q, "offset", 0), _int(q, "limit", 100, 0, 500))
            return eng.profile(sid, table)
        if rest == ["events"]:
            return eng.events_since(sid, _int(q, "since", 0))
        if rest == ["mastery"]:
            return eng.mastery(sid)
        if rest == ["sponsors"]:
            return eng.sponsor_totals(sid)
        raise ApiError(404, "unknown endpoint")

    if method != "POST":
        raise ApiError(405, "method not allowed")
    b = _obj(body)
    if rest == ["sql"]:
        return eng.sql(sid, _text(b, "sql", MAX_SQL))
    if rest == ["answer"]:
        return eng.on_answer(sid, parse_answer(b))
    if rest == ["appeal"]:
        return eng.on_appeal(sid, {"taskId": _text(b, "taskId", 16), "reason": _text(b, "reason")})
    if len(rest) == 3 and rest[0] == "appeal" and rest[2] == "message":
        if not ID_RE.match(rest[1]):
            raise ApiError(400, "bad appeal id")
        return eng.on_appeal_message(sid, rest[1], {"text": _text(b, "text")})
    if rest == ["ask"]:
        agent = b.get("agent")
        if agent not in cast.BY_ID:
            raise ApiError(400, "agent must be vale, ines, sam, telem or riley")
        return eng.ask(sid, agent, _text(b, "text", 2000))
    raise ApiError(404, "unknown endpoint")

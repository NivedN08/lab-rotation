"""Export a finished session as plain static files for the hosted replay (`VITE_STATIC=1`).

    uv run python -m lab.session.export_static <sessionId> [--out web/public/recorded]
        [--start S --end E --speed X] [--audio DIR] [--portraits DIR]

The layout is P3's `web/src/api/staticFiles.ts` (STATIC_FILES). Every JSON file is what the
matching route answers for the finished session, read through `lab.session.api` itself, so
the export holds only what the browser could already see: never the answer key, the bank's
sealed files, `.state.json` or anything from `.env`. The files are built in a scratch folder
and scanned for leaks (`scan`) before they replace `--out`; a failed scan writes nothing.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
AUDIO = ROOT / "data" / "audio"
PORTRAITS = ROOT / "data" / "portraits"
PAGE = 500                                   # the rows route's largest page
KEY_FIELDS = {"careless", "careful", "naive", "matters"}   # answer-key fields: never in a route's reply
LOCAL = ("localhost", "127.0.0.1", "file://", "/Users/", "/private/", str(ROOT))
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ExportError(RuntimeError):
    pass


def _get(path: str, query: str = "") -> object:
    from lab.session import api
    status, reply = api.handle("GET", path, query, None)
    if status != 200:
        raise ExportError(f"GET {path} answered {status}: {reply}")
    return reply


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def _safe(name: str, what: str) -> str:
    if not SAFE_NAME.match(name or ""):
        raise ExportError(f"unsafe {what} name {name!r}")
    return name


def _tables(base: Path, sid: str, task: str | None) -> None:
    """tables.json, rows/<table>.json (every row) and profile/<table>.json for one task."""
    q = f"task={quote(task)}" if task else ""
    tables = _get(f"/api/session/{sid}/tables", q)
    _write(base / "tables.json", tables)
    for t in tables:
        name = _safe(t["name"], "table")
        rows, offset = [], 0
        while True:
            page = _get(f"/api/session/{sid}/tables/{name}/rows",
                        "&".join(x for x in (f"offset={offset}", f"limit={PAGE}", q) if x))["rows"]
            rows += page
            offset += len(page)
            if len(page) < PAGE:
                break
        _write(base / "rows" / f"{name}.json", {"rows": rows})
        _write(base / "profile" / f"{name}.json", _get(f"/api/session/{sid}/tables/{name}/profile", q))


def build(sid: str, out: Path, *, start: float = 0.0, end: float | None = None, speed: float = 1.0,
          audio_dir: Path = AUDIO, portraits_dir: Path = PORTRAITS, base: str | None = None) -> dict:
    """Write the export into `out` (which must not exist yet). Returns {files, bytes, missing}."""
    from lab.session import api
    from lab.session.engine import Engine
    _safe(sid, "session")
    engine = Engine()
    before = (api._mock, api._real)
    api.set_engines(real=engine)   # a fresh engine reads the finished session from disk
    try:
        session = engine.get(sid)
        events = _get(f"/api/session/{sid}/events", "since=0")["events"]
        if not session.finished or not any(e["k"] == "session.end" for e in events):
            raise ExportError(f"session {sid} is not finished")
        base = base if base is not None else f"{out.name}/"
        home = out / sid
        last_t = max(e["t"] for e in events)
        _write(out / "demo.json", {"session": sid, "start": start,
                                   "end": end if end is not None else float(math.ceil(last_t + 1)),
                                   "speed": speed})
        agents, missing = [], []
        for a in _get("/api/agents"):
            a = dict(a)
            png = portraits_dir / f"{_safe(a['id'], 'agent')}.png"
            if png.is_file():
                (out / "portraits").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(png, out / "portraits" / png.name)
                a["portrait"] = f"{base}portraits/{png.name}"   # relative to the page, like STATIC_BASE
            else:
                a["portrait"] = None
                missing.append(f"portraits/{png.name}")
            agents.append(a)
        extra = portraits_dir / "learner.png"   # the learner's own portrait, when there is one
        if extra.is_file():
            (out / "portraits").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(extra, out / "portraits" / extra.name)
        _write(out / "agents.json", agents)
        _write(out / "bench.json", _get("/api/bench"))
        _write(home / "events.json", {"events": events, "next": events[-1]["seq"]})
        _write(home / "task.json", _get(f"/api/session/{sid}/task"))
        _write(home / "mastery.json", _get(f"/api/session/{sid}/mastery"))
        _write(home / "sponsors.json", _get(f"/api/session/{sid}/sponsors"))
        _tables(home, sid, None)   # the plain names: the last task
        for t in (x.id for x in session.slots if x.task is not None):   # tried first by the front end
            _tables(home / _safe(t, "task"), sid, t)
        for e in events:
            f = (e.get("data") or {}).get("file") if e["k"] == "voice.line" else None
            if not f:
                continue
            src = audio_dir / _safe(Path(f).name, "audio file")
            if src.is_file():
                (out / "audio").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, out / "audio" / src.name)
            else:
                missing.append(f"audio/{src.name}")
        keys = [x.task.key for x in session.slots if x.task is not None]
    finally:
        api.set_engines(*before)
    files = [p for p in out.rglob("*") if p.is_file()]
    return {"files": len(files), "bytes": sum(p.stat().st_size for p in files), "missing": missing, "keys": keys}


# ------------------------------------------------------------------------------------ the scan

def env_values() -> dict[str, str]:
    """`.env` names to values, for the scan only (never printed). Short values are too common to scan."""
    try:
        from dotenv import dotenv_values
        got = dotenv_values(ROOT / ".env")
    except Exception:
        return {}
    return {k: v for k, v in got.items() if v and len(v.strip()) >= 8}


def _allowed(rel: str, sid: str) -> bool:
    task_files = r"(tables\.json|(rows|profile)/[A-Za-z0-9._-]+\.json)"
    pats = [r"(demo|agents|bench)\.json", r"audio/[A-Za-z0-9._-]+\.(mp3|wav|ogg)", r"portraits/[a-z]+\.png",
            rf"{re.escape(sid)}/((events|task|mastery|sponsors)\.json|{task_files})",
            rf"{re.escape(sid)}/t[0-9]+/{task_files}"]
    return any(re.fullmatch(p, rel) for p in pats)


def _walk_keys(x, found: set) -> None:
    if isinstance(x, dict):
        found |= KEY_FIELDS & set(x)
        for v in x.values():
            _walk_keys(v, found)
    elif isinstance(x, list):
        for v in x:
            _walk_keys(v, found)


def scan(out: Path, sid: str, keys: list[dict] = (), secrets: dict[str, str] | None = None) -> list[str]:
    """Problems in an export, in words that never quote a secret. Empty means clean."""
    secrets = env_values() if secrets is None else secrets
    problems = []
    for p in sorted(x for x in out.rglob("*") if x.is_file()):
        rel = p.relative_to(out).as_posix()
        if not _allowed(rel, sid):
            problems.append(f"{rel}: not a file the static replay reads")
        raw = p.read_bytes()
        for name, value in secrets.items():
            if value.encode() in raw:
                problems.append(f"{rel}: holds the value of .env {name}")
        if p.suffix != ".json":
            continue
        text = raw.decode("utf-8", "replace")
        problems += [f"{rel}: has a local path or URL ({w})" for w in LOCAL if w in text]
        found: set = set()
        _walk_keys(json.loads(text), found)
        problems += [f"{rel}: has the answer-key field {k!r}" for k in sorted(found)]
        for key in keys:
            for c in key.get("checks") or []:
                if isinstance(c, dict) and c.get("sql") and c["sql"] in text:
                    problems.append(f"{rel}: has a check's SQL from the key")
    events_file = out / sid / "events.json"
    if events_file.is_file() and keys:
        problems += _before_answer(json.loads(events_file.read_text())["events"], keys)
    return problems


def _before_answer(events: list[dict], keys: list[dict]) -> list[str]:
    """Before each task's answer only sealed parts (whisper text, `useful`) may point at the trap or
    quote the key's analyses; after the verdict the panel explains the key by design."""
    from lab.session.engine import leaks
    problems, by_task = [], {}
    tasks = [e.get("data", {}).get("taskId") for e in events if e["k"] == "task.picked"]
    for t, key in zip(tasks, keys):
        by_task[t] = key
    answered, current = set(), tasks[0] if tasks else None
    for e in events:
        if e["k"] == "task.picked":
            current = e.get("data", {}).get("taskId") or current
        t = e.get("task") or current   # an event with no task belongs to the task under way
        if e["k"] == "learner.answer":
            answered.add(t)
        key = by_task.get(t)
        if key is None or t in answered or key.get("trap") in (None, "none"):
            continue
        d = dict(e.get("data") or {})
        if e["k"] == "panel.whisper":
            d.pop("text", None)
        if e["k"] == "learner.query":
            d.pop("useful", None)
        shown = json.dumps({**e, "data": d}).lower()
        notes = [str((key.get(k) or {}).get("note") or "").lower() for k in ("careless", "careful")]
        if leaks(shown, key["trap"]) or any(len(n) > 20 and n in shown for n in notes):
            problems.append(f"{t}/events.json seq {e['seq']} ({e['k']}): points at the trap before the answer")
    return problems


# ------------------------------------------------------------------------------------ command line

def export(sid: str, out: Path, **kw) -> dict:
    """Build in a scratch folder next to `out`, scan it, and only then put it in place."""
    out = out.resolve()
    if out.exists() and any(out.iterdir()) and not (out / "demo.json").is_file():
        raise ExportError(f"{out} has other files in it; give an empty folder or an earlier export")
    tmp = out.with_name(out.name + ".export-tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        got = build(sid, tmp, base=kw.pop("base", None) or f"{out.name}/", **kw)
        problems = scan(tmp, sid, got.pop("keys"))
        if problems:
            raise ExportError("the export failed its leak scan:\n  " + "\n  ".join(problems))
        shutil.rmtree(out, ignore_errors=True)
        tmp.rename(out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {**got, "out": str(out)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export a finished session for the static replay (VITE_STATIC=1).")
    ap.add_argument("session")
    ap.add_argument("--out", default=str(ROOT / "web" / "public" / "recorded"))
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None, help="default: just after the last event")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--audio", default=str(AUDIO), help="folder with the voice files")
    ap.add_argument("--portraits", default=str(PORTRAITS), help="folder with <agent>.png")
    ap.add_argument("--base", default=None, help="the folder as the page sees it (default: the --out name + /)")
    args = ap.parse_args(argv)
    try:
        got = export(args.session, Path(args.out), start=args.start, end=args.end, speed=args.speed,
                     audio_dir=Path(args.audio), portraits_dir=Path(args.portraits), base=args.base)
    except ExportError as e:
        print(f"export_static: {e}", file=sys.stderr)
        return 1
    print(f"wrote {got['files']} files, {got['bytes'] / 1e6:.2f} MB, to {got['out']}")
    for m in got["missing"]:
        print(f"  missing (not copied): {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

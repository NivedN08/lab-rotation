"""Recorded sessions, for picking the demo replay.

    uv run python -m lab.session list            # every session in data/sessions/
    uv run python -m lab.session show <id>       # one session's events, one line each

Put the chosen id in `.env` as LAB_DEMO_SESSION (with LAB_DEMO_START, LAB_DEMO_END and
LAB_DEMO_SPEED for the part worth showing); `GET /api/demo` then names it.
"""

from __future__ import annotations

import sys

from lab.session.log import read_events, session_path, sessions_dir


def summary(path) -> str:
    evs = read_events(path)
    if not evs:
        return f"{path.stem}  (empty)"
    start = evs[0].get("data") or {}
    end = next((e for e in evs if e["k"] == "session.end"), None)
    grades = [f"{e['data']['taskId']}={e['data']['score']}" for e in evs if e["k"] == "verdict"]
    state = f"done, total {end['data']['totalScore']}" if end else "not finished"
    return (f"{path.stem}  {start.get('mode', '?'):8} {len(evs):4} events  {evs[-1]['t']:7.1f} s  "
            f"{state}  {' '.join(grades)}")


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "list":
        for p in sorted(sessions_dir().glob("*.jsonl"), key=lambda p: p.stat().st_mtime):
            print(summary(p))
        return 0
    if argv[0] == "show" and len(argv) == 2:
        for e in read_events(session_path(argv[1])):
            print(f"{e['seq']:4} {e['t']:7.1f} {e['k']:16} {e['agent']:8} {(e.get('text') or e['why'])[:90]}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

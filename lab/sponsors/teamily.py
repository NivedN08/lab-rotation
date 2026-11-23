"""Teamily: a practice summary post after a rotation.

Teamily's API is not known yet (no public docs found, no key in `.env`), so this is a
stub with the final interface. It always writes the post to `data/teamily/<session>.md`
(`provider: "recorded"`). If `TEAMILY_POST_URL` is set, it also POSTs
`{title, text, session}` there as JSON (with `TEAMILY_API_KEY` as a bearer token when set),
and reports `provider: "teamily"`.

    post = Teamily(on_call=engine.sponsor_call).post_summary(session_id, tasks, mastery)
"""

from __future__ import annotations

import os
from typing import Optional

from lab.sponsors.calls import DATA, Reporter, SponsorCall, Timer, report, short_error

OUT = DATA / "teamily"
TRAP_NAMES = {"duplicate_rows": "duplicated rows", "unit_mismatch": "mixed units",
              "dictionary_flip": "a flipped dictionary code", "confounder": "a confounder",
              "hidden_variable": "a hidden variable in a second table", "none": "a clean result"}


def practice_summary(tasks: list, mastery: Optional[dict] = None, learner: str = "learner") -> tuple[str, str]:
    """(title, text). tasks: [{title, trap, score}], mastery: {trap: {from, to}}."""
    total = sum(float(t.get("score") or 0) for t in tasks)
    title = f"Rotation summary: {total:.1f} of {len(tasks)}"
    lines = [f"{learner} finished a rotation of {len(tasks)} task{'s' if len(tasks) != 1 else ''}.", ""]
    for i, t in enumerate(tasks, 1):
        trap = TRAP_NAMES.get(t.get("trap", ""), t.get("trap", "?"))
        lines.append(f"{i}. {t.get('title', 'Task')}: the trap was {trap}. Score {float(t.get('score') or 0):.2f}.")
    if mastery:
        lines += ["", "Skills that moved:"]
        for trap, m in mastery.items():
            lines.append(f"- {TRAP_NAMES.get(trap, trap)}: {float(m['from']):.2f} to {float(m['to']):.2f}")
    return title, "\n".join(lines)


class Teamily:
    def __init__(self, *, on_call: Reporter = None, out_dir=OUT, poster=None):
        from lab.env import load_env

        load_env()
        self.on_call = on_call
        self.out_dir = out_dir
        self.url = os.environ.get("TEAMILY_POST_URL", "")
        self._poster = poster  # tests pass a callable(url, json, headers)

    def post_summary(self, session: str, tasks: list, mastery: Optional[dict] = None,
                     learner: str = "learner") -> dict:
        """{title, text, file, provider, posted}."""
        title, text = practice_summary(tasks, mastery, learner)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{session}.md"
        path.write_text(f"# {title}\n\n{text}\n")
        out = {"title": title, "text": text, "file": path.name, "provider": "recorded", "posted": False}
        if not self.url:
            report(self.on_call, SponsorCall("teamily", "post", "Saved the practice summary (Teamily not set up)",
                                             fallback=True))
            return out
        t = Timer()
        try:
            headers = {"Content-Type": "application/json"}
            if os.environ.get("TEAMILY_API_KEY"):
                headers["Authorization"] = f"Bearer {os.environ['TEAMILY_API_KEY']}"
            body = {"title": title, "text": text, "session": session}
            if self._poster:
                self._poster(self.url, body, headers)
            else:
                import httpx

                httpx.post(self.url, json=body, headers=headers, timeout=10).raise_for_status()
            report(self.on_call, SponsorCall("teamily", "post", "Posted the practice summary", ms=t.ms))
            return dict(out, provider="teamily", posted=True)
        except Exception as exc:  # noqa: BLE001
            report(self.on_call, SponsorCall("teamily", "post", "Posted the practice summary", ok=False, ms=t.ms,
                                             fallback=True, error=short_error(exc)))
            return out

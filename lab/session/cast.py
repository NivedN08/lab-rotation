"""The panel: who each agent is, its floor role, and what it may read (in plain words).

`reads` is shown to the learner; `lab.session.visibility` enforces it in code.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORTRAITS = ROOT / "data" / "portraits"

AGENTS = [
    {"id": "vale", "name": "Dr. Vale", "role": "director", "title": "Lab head",
     "reads": "your learner profile, the panel's whispers and the check results"},
    {"id": "ines", "name": "Ines", "role": "referee", "title": "Examiner",
     "reads": "the answer key and the Bruin check output"},
    {"id": "sam", "name": "Sam", "role": "head", "title": "Methods reviewer",
     "reads": "your queries, your actions, your answer, the struggle meter and the whispers"},
    {"id": "telem", "name": "Telem", "role": "library", "title": "Librarian",
     "reads": "only its own search results about real cases"},
    {"id": "riley", "name": "Riley", "role": "team-b", "title": "AI intern",
     "reads": "only the public tables, the same ones you see"},
]
BY_ID = {a["id"]: a for a in AGENTS}
NAMES = {a["id"]: a["name"] for a in AGENTS} | {"learner": "you", "system": "the lab"}


def portrait(agent_id: str) -> str | None:
    for ext in ("png", "jpg", "webp"):
        if (PORTRAITS / f"{agent_id}.{ext}").is_file():
            return f"/api/portraits/{agent_id}.{ext}"
    return None


def agents() -> list[dict]:
    """The `GET /api/agents` reply."""
    return [{"id": a["id"], "name": a["name"], "role": a["role"], "title": a["title"], "reads": a["reads"],
             "portrait": portrait(a["id"])} for a in AGENTS]

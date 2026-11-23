"""Grading against the sealed key. Deterministic; Ines only words the feedback.

    score = 0.4 * verdict + 0.4 * trap + 0.2 * evidence - 0.1 per hint given

clipped to 0..1; passed when score >= 0.6. Evidence scores 1 when an item touches a
column that matters (the key's `columns`), 0.5 when there is evidence but none does,
0 with no evidence. For a clean twin (`none`) any evidence scores 1.
"""

from __future__ import annotations

from lab.session.meter import columns_in

PASS = 0.6
HINT_COST = 0.1


def evidence_score(evidence: list[dict], trap: str, columns: list[str]) -> float:
    if not evidence:
        return 0.0
    if trap == "none" or not columns:
        return 1.0
    rel = set(columns)
    for item in evidence:
        blob = " ".join(str(item.get(k) or "") for k in ("column", "sql", "label", "source"))
        if columns_in(blob, rel):
            return 1.0
    return 0.5


def grade(answer: dict, key: dict, hints_used: int) -> dict:
    v = 1 if answer["verdict"] == key["verdict"] else 0
    t = 1 if answer["trap"] == key["trap"] else 0
    ev = evidence_score(answer.get("evidence") or [], key["trap"], key.get("columns") or [])
    hints = -round(HINT_COST * hints_used, 2) if hints_used > 0 else 0
    score = round(max(0.0, min(1.0, 0.4 * v + 0.4 * t + 0.2 * ev + hints)), 2)
    return {"score": score, "result": "passed" if score >= PASS else "failed",
            "parts": {"verdict": v, "trap": t, "evidence": ev, "hints": hints},
            "correctVerdict": key["verdict"], "correctTrap": key["trap"]}


def correct_for_mastery(answer: dict, key: dict) -> bool:
    """The skill counts as shown when both the verdict and the trap are right."""
    return answer["verdict"] == key["verdict"] and answer["trap"] == key["trap"]

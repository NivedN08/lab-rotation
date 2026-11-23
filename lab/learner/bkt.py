"""Bayesian Knowledge Tracing, one skill per trap id (plus `none`, trusting a clean result).

Standard ungated BKT: after each attempt the mastery estimate is the posterior given the
answer, then the learning transition. Stdlib only, so the Bruin Python asset can import it.
"""
from __future__ import annotations

SKILLS = ("duplicate_rows", "unit_mismatch", "dictionary_flip", "confounder", "hidden_variable", "none")
LABELS = {"duplicate_rows": "duplicate rows", "unit_mismatch": "unit mix-ups",
          "dictionary_flip": "dictionary flips", "confounder": "confounders",
          "hidden_variable": "hidden variables", "none": "trusting a clean result"}

# prior P(L0), learn P(T), slip P(S), guess P(G). Trusting a clean result is easier to guess.
PARAMS = {s: {"prior": 0.15, "learn": 0.30, "slip": 0.10, "guess": 0.20} for s in SKILLS}
PARAMS["none"] = {"prior": 0.15, "learn": 0.30, "slip": 0.10, "guess": 0.30}
CORRECT_SCORE = 0.6   # a task scored at least this counts as a correct attempt


def update(p: float, correct: bool, skill: str) -> float:
    """Mastery after one attempt: Bayes on the answer, then the learning transition."""
    q = PARAMS[skill]
    if correct:
        post = p * (1 - q["slip"]) / (p * (1 - q["slip"]) + (1 - p) * q["guess"])
    else:
        post = p * q["slip"] / (p * q["slip"] + (1 - p) * (1 - q["guess"]))
    return post + (1 - post) * q["learn"]


def p_correct(p: float, skill: str) -> float:
    q = PARAMS[skill]
    return p * (1 - q["slip"]) + (1 - p) * q["guess"]


def trace(attempts: list[dict]) -> dict[str, dict]:
    """{skill: {score, attempts, correct}} after replaying attempts ({skill, correct}) in order."""
    state = {s: {"score": PARAMS[s]["prior"], "attempts": 0, "correct": 0} for s in SKILLS}
    for a in attempts:
        s = a["skill"]
        if s not in state:
            continue
        st = state[s]
        st["score"] = update(st["score"], bool(a["correct"]), s)
        st["attempts"] += 1
        st["correct"] += int(bool(a["correct"]))
    return state

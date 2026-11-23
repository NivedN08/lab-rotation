"""Learner history, BKT mastery and the bandit. See lab/learner/__init__.py for the API."""
from __future__ import annotations

import json
import os
import random
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterable

from lab.learner.bkt import CORRECT_SCORE, LABELS, PARAMS, SKILLS, trace

DIR = Path(__file__).resolve().parents[2] / "data" / "learners"
TIER_CUTS = (0.4, 0.7)     # mastery below 0.4 -> tier 1, below 0.7 -> tier 2, else tier 3
NUDGE_BOOST = 0.15         # added to the bandit's draw for the skill in the news
_LOCK = threading.Lock()


def _dir() -> Path:
    """data/learners, or LAB_LEARNERS_DIR when set (the session engine and its tests use it)."""
    return Path(os.environ.get("LAB_LEARNERS_DIR") or DIR)


def _path(learner: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(learner or "anon"))[:64] or "anon"
    return _dir() / f"{safe}.json"


def history(learner: str) -> list[dict]:
    p = _path(learner)
    if not p.exists():
        return []
    return json.loads(p.read_text()).get("attempts", [])


def reset(learner: str) -> None:
    with _LOCK:
        _path(learner).unlink(missing_ok=True)


def _save(learner: str, attempts: list[dict]) -> None:
    p = _path(learner)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump({"learner": learner, "attempts": attempts}, f, indent=1)
    os.replace(tmp, p)


def _state(learner: str) -> dict[str, dict]:
    return trace(history(learner))


def mastery(learner: str) -> dict:
    """{"traps": [{trap, score, attempts}]} for all six skill ids, in a fixed order."""
    st = _state(learner)
    return {"traps": [{"trap": s, "score": round(st[s]["score"], 3), "attempts": st[s]["attempts"]}
                      for s in SKILLS]}


def record(learner: str, trap: str, correct: bool | None = None, *, score: float | None = None,
           tier: int | None = None, session: str | None = None, task: str | None = None) -> list[dict]:
    """Add one graded attempt at `trap` (the task's true trap; `none` for a clean task).

    Pass `correct`, or `score` (0 to 1; correct when score >= 0.6). Returns the mastery.update
    data for each skill whose score changed."""
    if trap not in SKILLS:
        raise ValueError(f"unknown trap id {trap!r}")
    if correct is None:
        if score is None:
            raise ValueError("pass correct or score")
        correct = score >= CORRECT_SCORE
    with _LOCK:
        attempts = history(learner)
        before = trace(attempts)
        attempts.append({"skill": trap, "correct": bool(correct), "score": score, "tier": tier,
                         "session": session, "task": task, "at": round(time.time(), 3)})
        after = trace(attempts)
        _save(learner, attempts)
    out = []
    for s in SKILLS:
        a, b = round(before[s]["score"], 3), round(after[s]["score"], 3)
        if a != b or before[s]["attempts"] != after[s]["attempts"]:
            out.append({"trap": s, "from": a, "to": b, "correct": bool(correct),
                        "attempts": after[s]["attempts"]})
    return out


def update(learner: str, trap: str, correct: bool) -> dict:
    """record() for one answer, returning that skill's mastery.update data
    {trap, from, to, correct, attempts} (the form the session engine asks for)."""
    ups = record(learner, trap, correct)
    return next(u for u in ups if u["trap"] == trap)


# ----------------------------------------------------------------------------- picking

def tier_for(score: float) -> int:
    return 1 if score < TIER_CUTS[0] else 2 if score < TIER_CUTS[1] else 3


def bandit_draws(state: dict[str, dict], rng) -> dict[str, dict]:
    """Thompson sampling over skills, weighted to low mastery: each skill's need to practise is
    Beta(1 + (1 - m) w, 1 + m w) with w = 2 + attempts, so it narrows as evidence comes in."""
    out = {}
    for s in SKILLS:
        m, n = state[s]["score"], state[s]["attempts"]
        w = 2 + n
        out[s] = {"mean": round(m, 3), "sample": round(rng.betavariate(1 + (1 - m) * w, 1 + m * w), 3)}
    return out


def _rules(state: dict[str, dict], allowed: list[str]) -> str:
    return min(allowed, key=lambda s: (round(state[s]["score"], 3), state[s]["attempts"], SKILLS.index(s)))


def _clean_nudge(nudge) -> dict | None:
    """The nudge as given, or None when it names no known skill."""
    if not isinstance(nudge, dict) or nudge.get("trap") not in SKILLS:
        return None
    return {k: nudge.get(k) for k in ("trap", "headline", "url", "trace")}


def pick_next(learner: str, tier: int | None = None, seen: Iterable[str] = (), avoid: Iterable[str] = (),
              rng: random.Random | None = None, use_bandit: bool = True, nudge: dict | None = None) -> dict:
    """Choose the next task's skill and tier, and a bank task for it.

    tier: force a tier (rotation mode passes 1, 2, 3); else it follows the skill's mastery.
    seen: bank ids the learner has had (picked last). avoid: skills already used this session
    (skipped when another skill is left).
    nudge: {trap, headline, url, trace} from Telem's case of the day, or None. The bandit adds
    NUDGE_BOOST to that skill's draw, so the news tilts the pick without overruling mastery (a
    mastered skill still loses to an unmastered one, and a clean task can still come up). The
    rules fallback ignores it. The public `reason` never mentions the nudge (the headline names
    the trap); `pickReason` does. `nudged` is true when the boosted skill was picked;
    `nudgeDecided` when the boost changed the pick."""
    from lab.tasks import bank

    rng = rng or random.Random()
    state = _state(learner)
    allowed = [s for s in SKILLS if s not in set(avoid)] or list(SKILLS)
    fresh = all(state[s]["attempts"] == 0 for s in SKILLS)
    nudge = _clean_nudge(nudge)
    boosted = nudge["trap"] if nudge and nudge["trap"] in allowed else None
    draws, fallback, decided = None, False, False
    try:
        if not use_bandit:
            raise RuntimeError("bandit off")
        draws = bandit_draws(state, rng)
        if boosted:
            draws[boosted]["boost"] = NUDGE_BOOST

        def score(s):
            return (draws[s]["sample"] + draws[s].get("boost", 0.0), -SKILLS.index(s))

        skill = max(allowed, key=score)
        plain = max(allowed, key=lambda s: (draws[s]["sample"], -SKILLS.index(s)))
        decided = bool(boosted) and skill == boosted and plain != boosted
    except Exception:
        fallback = True
        skill = _rules(state, allowed)
    nudged = bool(boosted) and not fallback and skill == boosted
    m, n = state[skill]["score"], state[skill]["attempts"]
    chosen_tier = tier if tier in (1, 2, 3) else tier_for(m)
    task = bank.pick(skill, chosen_tier, seen=seen, rng=rng)

    label = LABELS[skill]
    tier_why = f"tier {task.tier}" + ("" if tier in (1, 2, 3) else f" to match a mastery of {m:.2f}")
    if fallback:
        reason = f"rules fallback: the skill with the lowest mastery ({m:.2f}), at {tier_why}"
        full = f"rules fallback picked {label}, the lowest mastery at {m:.2f} after {n} attempts, at {tier_why}"
    elif fresh:
        reason = f"new learner with no history: every skill starts at {PARAMS[skill]['prior']:.2f}, " \
                 f"so the bandit's draw decides, at {tier_why}"
        full = (f"no history, so every trap sat at {PARAMS[skill]['prior']:.2f}; the bandit's draw was "
                f"highest for {label} ({draws[skill]['sample']:.2f}), at {tier_why}")
    else:
        others = sorted((d["sample"] + d.get("boost", 0.0) for s, d in draws.items()
                         if s != skill and s in allowed), reverse=True)
        nxt = f" vs {others[0]:.2f} next" if others else ""
        reason = (f"the bandit leans toward skills not yet mastered; this one is at {m:.2f} after {n} "
                  f"attempts and drew highest, at {tier_why}")
        full = (f"{label} is at {m:.2f} after {n} attempts; the bandit's draw of need was highest there "
                f"({draws[skill]['sample']:.2f}{nxt}), at {tier_why}")
    if nudge:
        news = f"Telem's case of the day (\"{nudge.get('headline') or 'untitled'}\") pointed at {LABELS[nudge['trap']]}"
        if fallback:
            full += f". {news}, but the rules fallback ignores the news"
        elif not boosted:
            full += f". {news}, a skill already used this session, so no boost"
        elif nudged:
            full += (f". {news}, so its draw got +{NUDGE_BOOST:.2f}"
                     + ("; that boost decided the pick" if decided else "; it was ahead without the boost"))
        else:
            full += f". {news}; its draw got +{NUDGE_BOOST:.2f} but mastery still favoured {label}"
    return {"skill": skill, "tier": task.tier, "task": task, "bankId": task.id, "reason": reason,
            "pickReason": full, "fallback": fallback, "bandit": draws,
            "nudged": nudged, "nudgeDecided": decided, "nudge": nudge}

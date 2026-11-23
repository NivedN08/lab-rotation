"""The learner model: BKT mastery per skill and a Thompson-sampling bandit that picks the next task.

Functions for the session engine:

    mastery(learner) -> {"traps": [{trap, score, attempts}]}            # api.md shape, all six ids
    record(learner, trap, correct, *, score=None, tier=None, session=None, task=None)
        -> [mastery.update data]   # [{trap, from, to, correct, attempts}], one per changed skill
    pick_next(learner, tier=None, seen=(), avoid=(), rng=None, nudge=None) -> Pick (a dict):
        {skill, tier, task (a lab.tasks.bank.BankTask), bankId, reason, pickReason, fallback, bandit,
         nudged, nudgeDecided, nudge}
        nudge = {trap, headline, url, trace} from Telem's case of the day boosts that skill's draw;
        it shows only in pickReason, never in reason.

`reason` never names the trap (task.picked); `pickReason` does (task.end, after the verdict).
History lives in data/learners/<learner>.json; mastery is the BKT replay of that history.
"""
from __future__ import annotations

from lab.learner.bkt import CORRECT_SCORE, LABELS, SKILLS
from lab.learner.model import history, mastery, pick_next, record, reset

__all__ = ["mastery", "record", "pick_next", "history", "reset", "SKILLS", "LABELS", "CORRECT_SCORE"]

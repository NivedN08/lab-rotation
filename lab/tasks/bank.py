"""The task bank: retail tasks pre-generated per skill and tier, so a session never waits.

    load(bank_id) -> BankTask
    pick(skill, tier, seen=(), rng=None) -> BankTask
    ids(skill=None, tier=None) -> [bank_id]

A BankTask has `id` (the bank id: server only, it is a key to the answer), `skill`, `tier`,
`public_dir` (task.json, tables.json, CSVs: hand it to lab.workspace_sql), `key` (the sealed
answer key: never send it to the browser before the verdict) and `public(slot)`, the task in the
contract shape with the session's slot id (`t1`, `t2`, `t3`).

The bank lives in data/tasks/ (git-ignored, like every answer key). It builds itself on first
use (about 10 s, deterministic); `ensure()` does it up front, e.g. at server start. Rebuild:

    uv run python -m lab.tasks.bank build [--per 4] [--seed 20261123]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import shutil
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Iterable

ROOT = pathlib.Path(__file__).resolve().parents[2] / "data" / "tasks"
PUBLIC, SEALED = ROOT / "public", ROOT / "sealed"
SEED = 20261123
PER = 4


@dataclass
class BankTask:
    id: str
    skill: str
    tier: int
    public_dir: pathlib.Path
    key: dict = field(repr=False)
    task: dict = field(repr=False)

    @property
    def dictionary(self) -> str:
        return self.task["dictionary"]

    def public(self, slot: str) -> dict:
        """The task as the browser sees it: {id, title, brief, seconds, claim, tier, dictionary}."""
        t = self.task
        return {"id": slot, "title": t["title"], "brief": t["brief"], "seconds": t["seconds"],
                "claim": t["claim"], "tier": t["tier"], "dictionary": t["dictionary"]}


_INDEX: dict | None = None
_BUILD_LOCK = threading.Lock()


def ensure(log=None) -> dict:
    """Build the bank if it is missing; return the index."""
    return index(log)


def index(log=None) -> dict:
    global _INDEX
    if _INDEX is None:
        with _BUILD_LOCK:
            if _INDEX is None:
                if not (SEALED / "index.json").exists():
                    build(log=log or (lambda *_: None))
                _INDEX = json.loads((SEALED / "index.json").read_text())
    return _INDEX


def ids(skill: str | None = None, tier: int | None = None) -> list[str]:
    return sorted(i for i, m in index().items()
                  if (skill is None or m["skill"] == skill) and (tier is None or m["tier"] == tier))


def load(bank_id: str) -> BankTask:
    if bank_id not in index():
        raise KeyError(f"no bank task {bank_id!r}")
    key = json.loads((SEALED / f"{bank_id}.json").read_text())
    d = PUBLIC / bank_id
    task = json.loads((d / "task.json").read_text())
    return BankTask(bank_id, key["trap"], key["tier"], d, key, task)


def pick(skill: str, tier: int, seen: Iterable[str] = (), rng: random.Random | None = None) -> BankTask:
    """An unseen task of this skill at this tier; else the nearest tier; else a seen one."""
    rng = rng or random
    seen = set(seen)
    tiers = sorted({m["tier"] for m in index().values()}, key=lambda t: (abs(t - tier), t))
    for t in tiers:
        fresh = [i for i in ids(skill, t) if i not in seen]
        if fresh:
            return load(rng.choice(fresh))
    pool = ids(skill, tier) or ids(skill)
    if not pool:
        raise KeyError(f"no bank task for skill {skill!r}")
    return load(rng.choice(pool))


# ----------------------------------------------------------------------------- building

def _bank_id(seed: int, skill: str, tier: int, n: int) -> str:
    h = hashlib.sha256(f"{seed}/{skill}/{tier}/{n}".encode()).hexdigest()
    return f"rb{h[:6]}"


def generate_one(skill: str, tier: int, truth: str, seed: int, n: int, folder: pathlib.Path) -> dict:
    """Draw until the keep filter passes; write the public folder; return the sealed key."""
    import numpy as np
    from lab.tasks import retail as R
    from lab.tasks.checks import CHECK_IDS, run_checks

    trap = skill
    want_fail = [CHECK_IDS[skill]] if skill != "none" else []
    opposite = R.FAILS if truth == R.HOLDS else R.HOLDS
    for attempt in range(R.MAX_ATTEMPTS):
        rng = np.random.default_rng([seed, R.SKILLS.index(skill), tier, n, attempt])
        d = R.draw(trap, truth, tier, rng)
        R.write_public(folder, d)
        ref, naive = R.analyse(folder, careful=True), R.analyse(folder, careful=False)
        if not (R.clear(ref, truth, R.CAREFUL_P) and ref["notes"] == d["expected_notes"]):
            continue
        if skill == "hidden_variable":
            bites = naive["verdict"] == R.CANT_TELL
        elif skill != "none":
            bites = R.clear(naive, opposite, R.CARELESS_P)
        else:
            bites = R.clear(naive, truth, R.CARELESS_P)
        if not bites:
            continue
        checks = run_checks(folder, fresh=True)
        if [c["check"] for c in checks if not c["passed"]] != want_fail:
            continue
        break
    else:
        raise RuntimeError(f"no acceptable draw for {skill} tier {tier} #{n} in {R.MAX_ATTEMPTS} attempts")

    def short(r):
        return {"verdict": r["verdict"], "estimate": None if r["estimate"] is None else round(r["estimate"], 4),
                "p": None if r["p"] is None else float(f"{r['p']:.4g}"), "n": r["n"], "means": r["means"],
                "notes": r["notes"]}

    careful = {"verdict": truth, "trap": skill, "note": R.careful_note(ref, skill, d["footprint"]), **short(ref)}
    careful["verdict"] = truth
    if skill == "none":
        guess = R.DECOYS.get(d["decoy"]) or str(rng.choice(list(R.SUSPICION)))
        careless = {"verdict": R.CANT_TELL, "trap": guess, "note": R.SUSPICION[guess].capitalize() + ".",
                    "plainReading": short(naive)}
    else:
        careless = {"verdict": naive["verdict"], "trap": "none", "note": R.careless_note(naive), **short(naive)}
    return {"trap": skill, "tier": tier, "correctVerdict": truth, "correctTrap": skill, "claim": d["claim"],
            "higher": d["higher"], "decoy": d["decoy"], "footprint": d["footprint"],
            "careful": careful, "careless": careless,
            "checks": list(CHECK_IDS.values()), "failingCheck": want_fail[0] if want_fail else None,
            "checkResults": checks, "seed": seed, "n": n, "attempts": attempt + 1}


def plan(per: int, seed: int) -> list[tuple[str, int, str, int]]:
    from lab.tasks.retail import FAILS, HOLDS, SKILLS, TIERS
    rng = random.Random(seed)
    out = []
    for skill in SKILLS:
        for tier in TIERS:
            truths = [FAILS] * per if skill == "duplicate_rows" else (
                [HOLDS, FAILS] * per)[:per]
            rng.shuffle(truths)
            out += [(skill, tier, truths[n], n) for n in range(per)]
    return out


def build(per: int = PER, seed: int = SEED, root: pathlib.Path = ROOT, log=print) -> dict:
    public, sealed = root / "public", root / "sealed"
    for p in (public, sealed):
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True)
    idx = {}
    with tempfile.TemporaryDirectory() as tmp:
        for skill, tier, truth, n in plan(per, seed):
            bid = _bank_id(seed, skill, tier, n)
            work = pathlib.Path(tmp) / bid
            key = generate_one(skill, tier, truth, seed, n, work)
            shutil.move(str(work), public / bid)
            key = {"bankId": bid, **key}
            (sealed / f"{bid}.json").write_text(json.dumps(key, indent=2) + "\n")
            idx[bid] = {"skill": skill, "tier": tier, "truth": truth}
            log(f"{bid} {skill:16s} t{tier} {truth:6s} attempts={key['attempts']}")
    (sealed / "index.json").write_text(json.dumps(dict(sorted(idx.items())), indent=2) + "\n")
    from lab.tasks.retail import PARAMS
    (sealed / "generation.json").write_text(json.dumps(
        {"seed": seed, "per": per, "params": {k: v for k, v in PARAMS.items()}, "params_source": "fixed"},
        indent=2, default=str) + "\n")
    global _INDEX
    _INDEX = None
    return idx


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m lab.tasks.bank")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--per", type=int, default=PER)
    b.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        build(a.per, a.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

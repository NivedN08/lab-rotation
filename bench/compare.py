"""Paired comparison of two systems on the same split, with a bootstrap over dialogues.

    uv run python -m bench.compare --split dev-B --a single-opus-start --b single-opus-tuned

Resamples dialogues (not replies, which share a dialogue) with replacement and reports the
difference b - a in macro-F1 per dimension and in the mean of the four, with a 95% interval.
"""

from __future__ import annotations

import argparse
import random
import sys

from bench import data, run, score
from bench.data import DIMENSIONS, SHORT


def mean_f1(dialogues, preds: dict) -> dict:
    out = {}
    for d in DIMENSIONS:
        g = data.gold(dialogues, d)
        out[SHORT[d]] = 100 * score.macro_f1(g, {k: (preds.get(k) or {}).get(d) for k in g})
    out["mean"] = sum(out[SHORT[d]] for d in DIMENSIONS) / len(DIMENSIONS)
    return out


def bootstrap(dialogues, preds_a: dict, preds_b: dict, reps: int = 1000, seed: int = 0) -> dict:
    """{metric: (difference b - a, low, high)} with a percentile 95% interval."""
    point_a, point_b = mean_f1(dialogues, preds_a), mean_f1(dialogues, preds_b)
    rng = random.Random(seed)
    diffs = {k: [] for k in point_a}
    for _ in range(reps):
        sample = [rng.choice(dialogues) for _ in dialogues]
        # resampled dialogues repeat; give each copy its own reply keys
        renamed, pa, pb = [], {}, {}
        for i, d in enumerate(sample):
            reps_ = []
            for r in d.replies:
                key = f"{i}#{r.key}"
                reps_.append(data.Reply(f"{i}#{r.dialogue_id}", r.tutor, r.text, r.labels))
                pa[key], pb[key] = preds_a.get(r.key), preds_b.get(r.key)
            renamed.append(data.Dialogue(f"{i}#{d.id}", d.history, tuple(reps_)))
        a, b = mean_f1(renamed, pa), mean_f1(renamed, pb)
        for k in diffs:
            diffs[k].append(b[k] - a[k])
    out = {}
    for k, v in diffs.items():
        v.sort()
        out[k] = (round(point_b[k] - point_a[k], 1), round(v[int(0.025 * reps)], 1), round(v[int(0.975 * reps) - 1], 1))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bench.compare")
    ap.add_argument("--split", default="dev-B")
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--reps", type=int, default=1000)
    a = ap.parse_args(argv)
    pa, pb = run.load_preds(a.a, a.split)["preds"], run.load_preds(a.b, a.split)["preds"]
    dialogues = [d for d in data.select(a.split) if all(r.key in pa and r.key in pb for r in d.replies)]
    res = bootstrap(dialogues, pa, pb, a.reps)
    print(f"{a.b} minus {a.a} on {a.split} ({len(dialogues)} dialogues, {a.reps} resamples):")
    for k, (d, lo, hi) in res.items():
        print(f"  {k:5s} {d:+5.1f}  95% [{lo:+.1f}, {hi:+.1f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())

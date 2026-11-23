"""The shared task's metrics: 3-class macro-F1 (the main one), accuracy, and the lenient
2-class versions where "Yes" and "To some extent" count as one class.

A reply with no prediction (missing, or not one of the labels) is a miss for its gold
class and a false positive for none.
"""

from __future__ import annotations

from bench.data import LABELS

LENIENT = {"Yes": "Yes", "To some extent": "Yes", "No": "No"}


def f1_per_class(gold: dict[str, str], pred: dict[str, str], labels=LABELS) -> dict[str, float]:
    out = {}
    for c in labels:
        tp = sum(1 for k, g in gold.items() if g == c and pred.get(k) == c)
        fp = sum(1 for k, g in gold.items() if g != c and pred.get(k) == c)
        fn = sum(1 for k, g in gold.items() if g == c and pred.get(k) != c)
        out[c] = 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)
    return out


def macro_f1(gold: dict[str, str], pred: dict[str, str], labels=LABELS) -> float:
    """Mean F1 over the labels, in 0..1. Scored over the gold keys only."""
    if not gold:
        raise ValueError("no gold labels to score")
    per = f1_per_class(gold, pred, labels)
    return sum(per.values()) / len(per)


def accuracy(gold: dict[str, str], pred: dict[str, str]) -> float:
    if not gold:
        raise ValueError("no gold labels to score")
    return sum(1 for k, g in gold.items() if pred.get(k) == g) / len(gold)


def lenient(labels: dict[str, str]) -> dict[str, str]:
    return {k: LENIENT[v] for k, v in labels.items() if v in LENIENT}


def lenient_macro_f1(gold: dict[str, str], pred: dict[str, str]) -> float:
    return macro_f1(lenient(gold), lenient(pred), labels=("Yes", "No"))


def report(gold: dict[str, str], pred: dict[str, str]) -> dict:
    """Every metric for one dimension, F1 and accuracy as percentages rounded to 0.1."""
    pct = lambda x: round(100 * x, 1)
    return {"n": len(gold), "macro_f1": pct(macro_f1(gold, pred)), "accuracy": pct(accuracy(gold, pred)),
            "lenient_f1": pct(lenient_macro_f1(gold, pred)),
            "missing": sum(1 for k in gold if pred.get(k) not in LABELS)}

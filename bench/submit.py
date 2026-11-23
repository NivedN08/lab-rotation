"""Writes test-set predictions in the shared task's submission format.

    uv run python -m bench.run single --split test --model opus --guide bench/guide_tuned.md --name single-opus-tuned
    uv run python -m bench.submit --name single-opus-tuned

The format is the test file itself with an "annotation" added to every tutor response
(as in the task repository's sample submission): one predictions.json per track, holding
that track's dimension, zipped, in data/bench/submission/<name>/<track>/. Nothing is uploaded;
CodaBench submission is a manual step.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile

from bench import data, run
from bench.data import DIMENSIONS, LABELS, ROOT, SHORT

OUT = ROOT / "data" / "bench" / "submission"
FALLBACK = "Yes"   # the majority label on dev, used only for a reply the system left unlabelled


def build(doc: list, preds: dict, dimensions=DIMENSIONS) -> tuple[list, int]:
    """A copy of the test document with annotations; also the count of fallback labels."""
    out, fallbacks = json.loads(json.dumps(doc)), 0
    for item in out:
        for tutor, r in item["tutor_responses"].items():
            p = preds.get(f"{item['conversation_id']}::{tutor}") or {}
            ann = {}
            for d in dimensions:
                label = p.get(d)
                if label not in LABELS:
                    label, fallbacks = FALLBACK, fallbacks + 1
                ann[d] = label
            r["annotation"] = ann
    return out, fallbacks


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bench.submit")
    ap.add_argument("--name", required=True)
    a = ap.parse_args(argv)
    preds = run.load_preds(a.name, "test")["preds"]
    doc = json.loads(data.TEST_FILE.read_text())
    for dim in DIMENSIONS:
        sub, fallbacks = build(doc, preds, (dim,))
        folder = OUT / a.name / SHORT[dim]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "predictions.json").write_text(json.dumps(sub, indent=1))
        with zipfile.ZipFile(folder / "predictions.zip", "w", zipfile.ZIP_DEFLATED) as z:
            z.write(folder / "predictions.json", "predictions.json")
        print(f"{SHORT[dim]}: {folder / 'predictions.zip'} ({fallbacks} fallback labels)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

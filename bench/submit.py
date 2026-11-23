"""Writes test-set predictions in the shared task's CodaBench submission format.

    uv run python -m bench.run single --split test --model opus --guide bench/guide_tuned.md --name single-opus-tuned
    uv run python -m bench.submit --name single-opus-tuned

The format is the test file itself with an "annotation" holding that track's dimension added
to every tutor response, saved as predictions.json and zipped as predictions.json.zip (as in
the organisers' sample submission and participants' scripts). One zip per track 1-4, in
data/bench/codabench/<name>/<track>/. Track 5 (tutor identity) is not ours. Each file is
checked against the test file before it is zipped. Nothing is uploaded: CodaBench upload is
a manual step (bench/README.md).
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile

from bench import data, run
from bench.data import DIMENSIONS, LABELS, ROOT, SHORT

OUT = ROOT / "data" / "bench" / "codabench"
TRACKS = {"Mistake_Identification": ("track1_mistake_identification", "https://www.codabench.org/competitions/7195/"),
          "Mistake_Location": ("track2_mistake_location", "https://www.codabench.org/competitions/7200/"),
          "Providing_Guidance": ("track3_providing_guidance", "https://www.codabench.org/competitions/7202/"),
          "Actionability": ("track4_actionability", "https://www.codabench.org/competitions/7203/")}
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


def check(sub: list, doc: list, dimension: str) -> list[str]:
    """Problems with a submission against the test file: same dialogues, histories, tutors and
    replies in the same order, one valid label each."""
    problems = []
    if len(sub) != len(doc):
        return [f"{len(sub)} dialogues, the test file has {len(doc)}"]
    for a, b in zip(sub, doc):
        if a["conversation_id"] != b["conversation_id"] or a["conversation_history"] != b["conversation_history"]:
            problems.append(f"dialogue {b['conversation_id']} differs")
        if list(a["tutor_responses"]) != list(b["tutor_responses"]):
            problems.append(f"dialogue {b['conversation_id']}: tutors differ")
            continue
        for t, r in a["tutor_responses"].items():
            if r["response"] != b["tutor_responses"][t]["response"]:
                problems.append(f"{b['conversation_id']}/{t}: response differs")
            if (r.get("annotation") or {}).get(dimension) not in LABELS:
                problems.append(f"{b['conversation_id']}/{t}: no valid {dimension} label")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bench.submit")
    ap.add_argument("--name", required=True)
    a = ap.parse_args(argv)
    preds = run.load_preds(a.name, "test")["preds"]
    doc = json.loads(data.TEST_FILE.read_text())
    n = sum(len(item["tutor_responses"]) for item in doc)
    for dim in DIMENSIONS:
        sub, fallbacks = build(doc, preds, (dim,))
        problems = check(sub, doc, dim)
        if problems:
            print(f"{SHORT[dim]}: not written: {problems[:3]}")
            return 1
        folder = OUT / a.name / TRACKS[dim][0]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "predictions.json").write_text(json.dumps(sub, indent=1, ensure_ascii=False))
        with zipfile.ZipFile(folder / "predictions.json.zip", "w", zipfile.ZIP_DEFLATED) as z:
            z.write(folder / "predictions.json", "predictions.json")
        print(f"{SHORT[dim]}: {folder / 'predictions.json.zip'} ({len(doc)} dialogues, {n} replies, "
              f"{fallbacks} fallback labels) -> {TRACKS[dim][1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

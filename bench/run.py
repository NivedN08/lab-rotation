"""Runs a system on a split and scores it.

    uv run python -m bench.run single --split dev-A --n 50 --model opus --name single-opus-start
    uv run python -m bench.run panel  --split dev-A --n 50 --model opus --name panel-opus-start
    uv run python -m bench.run score  --name single-opus-start --split dev-A

Predictions go to data/bench/preds/<name>__<split>.json; scores are printed and upserted into
data/bench/results.csv (split, dimension, system, macro_f1, n, record). Calls are cached, so a
stopped run resumes. The records are the best BEA 2025 test-set scores (3-class macro-F1); our
dev numbers are not test numbers and are labelled by split.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import pathlib
import sys
import time

from bench import data, judge, llm, score
from bench.data import DIMENSIONS, ROOT

PREDS = ROOT / "data" / "bench" / "preds"
RESULTS = ROOT / "data" / "bench" / "results.csv"
FIELDS = ("split", "dimension", "system", "macro_f1", "n", "record")
# Best 3-class macro-F1 on the BEA 2025 test set, per track (Final_Leaderboards/*_main.pdf).
RECORDS = {"Mistake_Identification": 71.8, "Mistake_Location": 59.8, "Providing_Guidance": 58.3,
           "Actionability": 70.9}


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, file=sys.stderr, flush=True)


def grade_all(dialogues, grade_one, jobs: int = 4) -> tuple[dict, dict]:
    """Runs grade_one(dialogue) -> (preds, meta) over dialogues in a thread pool. Stops early on a
    usage limit and returns what it has (meta["stopped"] says why)."""
    preds, meta = {}, {"usd": 0.0, "calls": 0, "cached": 0, "errors": 0, "disputed_cells": 0, "cells": 0,
                       "dialogues": 0, "stopped": None, "readers": {"1": {}, "2": {}}}
    with cf.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(grade_one, d): d for d in dialogues}
        try:
            for i, fut in enumerate(cf.as_completed(futures), 1):
                p, m = fut.result()
                preds.update(p)
                meta["dialogues"] += 1
                for c in m["calls"]:
                    meta["calls"] += 1
                    meta["cached"] += bool(c.get("cached"))
                    meta["errors"] += bool(c.get("error"))
                    meta["usd"] += float(c.get("usd") or 0)
                meta["disputed_cells"] += m.get("disputed_cells", 0)
                meta["cells"] += m.get("cells", 0)
                for k in ("1", "2"):
                    meta["readers"][k].update((m.get("readers") or {}).get(k, {}))
                if i % 10 == 0 or i == len(futures):
                    log(f"{i}/{len(futures)} dialogues, {meta['calls']} calls ({meta['cached']} cached), "
                        f"errors {meta['errors']}, ${meta['usd']:.2f}")
        except llm.UsageStop as err:
            meta["stopped"] = f"usage limit: {str(err)[:200]}"
            log(f"stopping: {meta['stopped']}")
            for f in futures:
                f.cancel()
    meta["usd"] = round(meta["usd"], 4)
    return preds, meta


def scores(dialogues, preds: dict) -> dict:
    return {d: score.report(data.gold(dialogues, d), {k: v.get(d) for k, v in preds.items()})
            for d in DIMENSIONS}


def save_preds(name: str, split: str, preds: dict, meta: dict) -> pathlib.Path:
    PREDS.mkdir(parents=True, exist_ok=True)
    path = PREDS / f"{name}__{split}.json"
    path.write_text(json.dumps({"name": name, "split": split, "meta": meta, "preds": preds}, indent=1))
    return path


def load_preds(name: str, split: str) -> dict:
    return json.loads((PREDS / f"{name}__{split}.json").read_text())


def upsert_results(rows: list[dict], path: pathlib.Path = RESULTS) -> None:
    """Replace rows with the same (split, dimension, system), keep the rest."""
    old = []
    if path.is_file():
        with path.open() as f:
            old = list(csv.DictReader(f))
    new_keys = {(r["split"], r["dimension"], r["system"]) for r in rows}
    keep = [r for r in old if (r["split"], r["dimension"], r["system"]) not in new_keys]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in keep + rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def result_rows(split: str, system: str, rep: dict) -> list[dict]:
    return [{"split": split, "dimension": d, "system": system, "macro_f1": rep[d]["macro_f1"],
             "n": rep[d]["n"], "record": RECORDS[d]} for d in DIMENSIONS]


def print_report(split: str, system: str, rep: dict, meta: dict | None = None) -> None:
    print(f"{system} on {split}:")
    for d in DIMENSIONS:
        r = rep[d]
        print(f"  {d:24s} macro-F1 {r['macro_f1']:5.1f}  acc {r['accuracy']:5.1f}  lenient {r['lenient_f1']:5.1f}"
              f"  n {r['n']}  missing {r['missing']}  (record {RECORDS[d]}, test)")
    mean3 = sum(rep[d]["macro_f1"] for d in DIMENSIONS[:3]) / 3
    print(f"  mean of MI, ML, PG: {mean3:.1f}")
    if meta:
        extra = {k: meta[k] for k in ("dialogues", "calls", "cached", "errors", "usd", "stopped")}
        if meta.get("cells"):
            extra["disputed"] = f"{meta['disputed_cells']}/{meta['cells']}"
        print(f"  {extra}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bench.run")
    ap.add_argument("mode", choices=("single", "panel", "score"))
    ap.add_argument("--split", default="dev-A", choices=("dev-A", "dev-B", "dev", "test"))
    ap.add_argument("--n", type=int, default=None, help="first n dialogues of the split")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--models", default=None, help="panel: reader1,reader2,referee (default all --model)")
    ap.add_argument("--guide", default=str(judge.GUIDE))
    ap.add_argument("--referee", default=str(judge.REFEREE))
    ap.add_argument("--name", required=True, help="system name in results.csv")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--replicate", type=int, default=0)
    ap.add_argument("--no-results", action="store_true", help="do not write results.csv")
    a = ap.parse_args(argv)

    dialogues = data.select(a.split, a.n)
    split_label = a.split if not a.n else f"{a.split}"
    if a.mode == "score":
        doc = load_preds(a.name, a.split)
        preds, meta = doc["preds"], doc["meta"]
    else:
        guide = pathlib.Path(a.guide).read_text()
        if a.mode == "single":
            one = lambda d: judge.grade_single(d, guide, a.model, replicate=a.replicate)
        else:
            models = tuple((a.models or f"{a.model},{a.model},{a.model}").split(","))
            referee = pathlib.Path(a.referee).read_text()
            one = lambda d: judge.grade_panel(d, guide, referee, models, replicate=a.replicate)
        log(f"{a.mode} {a.name}: {len(dialogues)} dialogues of {a.split}, jobs {a.jobs}")
        preds, meta = grade_all(dialogues, one, a.jobs)
        meta.update({"n_dialogues_asked": len(dialogues), "model": a.model, "models": a.models,
                     "guide": a.guide, "replicate": a.replicate})
        save_preds(a.name, a.split, preds, meta)
    if a.split == "test":
        print(f"test predictions saved for {len(preds)} replies (no labels to score)")
        return 0
    done = [d for d in dialogues if all(r.key in preds for r in d.replies)]
    rep = scores(done, preds)
    print_report(split_label, a.name, rep, meta)
    if not a.no_results and not meta.get("stopped"):
        upsert_results(result_rows(split_label, a.name, rep))
    return 1 if meta.get("stopped") else 0


if __name__ == "__main__":
    sys.exit(main())

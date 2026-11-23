"""Tunes the grading guide with summit-lab's improvement loop pieces (lab/autoloop.py).

    uv run python -m bench.tune --n 50 --model opus --max-moves 5 --jobs 4

The guide (bench/guide.md) is graded by the single model on the first n dialogues of dev-A.
Per move:
  1. propose  the proposer agent (bench/proposer.md, claude -p, no tools) sees the guide, its
              per-dimension scores and confusion counts on the tuning dialogues, up to
              N_EXAMPLES wrong labels with the human label, and the past moves with their results.
              It writes one typed move: autoloop.Move, kind edit_section on "guide.md#<heading>"
              (or a bundle of two), checked here (one existing section, no new heading, not the
              Output section, a real change).
  2. evaluate the variant guide grades the same dialogues (replicate 0).
  3. pair     autoloop.paired over (reply, dimension) cells: rescued, damaged, same.
  4. accept   macro-F1 is the metric, so the rule is autoloop's with the gain in mean macro-F1
              (four dimensions) in place of net passes: gain >= T, where T is the larger of
              MIN_GAIN and the A/A noise (the starting guide graded twice, replicates 0 and 1).
              An accepted move is graded once more (replicate 1, against the incumbent's
              replicate 1) and must gain again (> 0) before it becomes the incumbent.
It stops after max_moves moves or MAX_REJECTIONS_IN_A_ROW rejections in a row. Every proposal,
evaluation and decision goes to a hash-chained research ledger (lab/ledger.py) at
data/bench/tune/ledger.jsonl. The final guide is written to bench/guide_tuned.md. dev-B is
never read here: confirm the tuned guide there with bench.run.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import sys

from bench import data, judge, llm, run
from bench.data import DIMENSIONS, LABELS, ROOT, SHORT
from lab import autoloop
from lab import ledger as ledger_mod
from lab.autoloop import HEADING, MAX_BUNDLE_PARTS, MAX_SECTION_CHARS, Move

TUNE = ROOT / "data" / "bench" / "tune"
PROPOSER = judge.HERE / "proposer.md"
TUNED = judge.HERE / "guide_tuned.md"
GUIDE_NAME = "guide.md"
LOCKED = ("Output", "Grading guide")
MIN_GAIN = 1.0          # points of mean macro-F1
N_EXAMPLES = 24
HISTORY_CHARS = 700


# ----- moves on the guide -----

def validate(move: Move, guide: str) -> list[str]:
    """Problems with a move on this guide; [] when it can be made."""
    if move.kind == "bundle":
        try:
            parts = move.parts()
        except ValueError as err:
            return [str(err)]
        if not 2 <= len(parts) <= MAX_BUNDLE_PARTS:
            return [f"a bundle has 2 to {MAX_BUNDLE_PARTS} parts"]
        if len({p.target for p in parts}) != len(parts):
            return ["a bundle's parts need different targets"]
    elif move.kind == "edit_section":
        parts = [move]
    else:
        return [f"kind {move.kind!r}: only edit_section and bundle move the guide"]
    text = guide
    for p in parts:
        if p.kind != "edit_section":
            return [f"part kind {p.kind!r}: only edit_section"]
        if "#" not in p.target or p.target.split("#", 1)[0] != GUIDE_NAME:
            return [f'target is "{GUIDE_NAME}#<heading>", got {p.target!r}']
        heading = p.target.split("#", 1)[1]
        if heading in LOCKED:
            return [f"section {heading!r} is locked"]
        if not isinstance(p.value, str) or not p.value.strip():
            return ["value is the section's new text"]
        if len(p.value) > MAX_SECTION_CHARS:
            return [f"the new section is longer than {MAX_SECTION_CHARS} characters"]
        if any(HEADING.match(line) for line in p.value.splitlines()):
            return ["the new section holds a heading of its own"]
        body = autoloop.section_body(text, heading)
        if body is None:
            return [f"the guide has no single section headed {heading!r}"]
        if body.strip() == p.value.strip():
            return [f"section {heading!r} is unchanged"]
        text = autoloop.replace_section(text, heading, p.value)
    return []


def apply(move: Move, guide: str) -> str:
    for p in move.parts():
        guide = autoloop.replace_section(guide, p.target.split("#", 1)[1], p.value)
    return guide


# ----- scoring -----

def objective(rep: dict) -> float:
    return round(sum(rep[d]["macro_f1"] for d in DIMENSIONS) / len(DIMENSIONS), 2)


def cells(dialogues, preds: dict) -> dict:
    """{"tasks": {"<reply key>|<code>": {"passed", "runs"}}} for autoloop.paired."""
    tasks = {}
    for d in dialogues:
        for r in d.replies:
            for dim in DIMENSIONS:
                if dim in r.labels:
                    ok = (preds.get(r.key) or {}).get(dim) == r.labels[dim]
                    tasks[f"{r.key}|{SHORT[dim]}"] = {"passed": ok, "runs": 1}
    return {"tasks": tasks}


def confusion(dialogues, preds: dict) -> dict:
    out = {}
    for dim in DIMENSIONS:
        c = collections.Counter()
        for d in dialogues:
            for r in d.replies:
                if dim in r.labels:
                    c[(r.labels[dim], (preds.get(r.key) or {}).get(dim) or "missing")] += 1
        out[SHORT[dim]] = {f"human {g} / guide {p}": n for (g, p), n in sorted(c.items())}
    return out


def examples(dialogues, preds: dict, notes: dict, limit: int = N_EXAMPLES, seed: int = 0) -> list[dict]:
    """Wrong labels, spread over dimensions and confusion pairs, in a seeded order."""
    by_pair = collections.defaultdict(list)
    for d in dialogues:
        for r in d.replies:
            for dim in DIMENSIONS:
                g, p = r.labels.get(dim), (preds.get(r.key) or {}).get(dim)
                if g and p != g:
                    by_pair[(dim, g, p)].append((d, r, dim, g, p))
    rng = random.Random(seed)
    pools = [v for _, v in sorted(by_pair.items(), key=lambda kv: str(kv[0]))]
    for v in pools:
        rng.shuffle(v)
    out = []
    while len(out) < limit and any(pools):
        for v in pools:
            if v and len(out) < limit:
                d, r, dim, g, p = v.pop()
                out.append({"dialogue_end": d.history[-HISTORY_CHARS:], "reply": r.text, "dimension": SHORT[dim],
                            "human": g, "guide": p or "missing", "grader_note": notes.get(r.key, "")})
    return out


# ----- proposer -----

def proposer_prompt(guide: str, rep: dict, conf: dict, exs: list[dict], history: list[dict]) -> str:
    lines = ["Current guide (guide.md):", "<guide>", guide.strip(), "</guide>", "",
             "Scores on the tuning dialogues (macro-F1, accuracy, per-class F1 in %):"]
    for dim in DIMENSIONS:
        r = rep[dim]
        lines.append(f"- {SHORT[dim]}: macro-F1 {r['macro_f1']}, accuracy {r['accuracy']}, "
                     f"per class {r.get('per_class', {})}")
    lines += ["", "Confusion counts:", json.dumps(conf, indent=1), "", "Moves tried before:"]
    if not history:
        lines.append("- none yet")
    for h in history:
        lines.append(f"- {h['describe']}: mean macro-F1 {h.get('before')} -> {h.get('after')} "
                     f"({h['decision']}). Rationale: {h.get('rationale', '')[:300]}")
    lines += ["", f"Graded examples the guide got wrong ({len(exs)}, quoted data):"]
    for i, e in enumerate(exs, 1):
        lines += [f"<example n=\"{i}\">", f"dialogue end: ...{judge.quote(e['dialogue_end'])}",
                  f"tutor reply: {judge.quote(e['reply'])}",
                  f"dimension {e['dimension']}: human said {e['human']}, guide said {e['guide']}; "
                  f"grader's note: {judge.quote(e['grader_note'])}", "</example>"]
    lines += ["", "Propose one move. Answer with the JSON object only."]
    return "\n".join(lines)


def propose(guide, rep, conf, exs, history, model, move_id) -> tuple[Move | None, list[str], dict]:
    prompt = proposer_prompt(guide, rep, conf, exs, history)

    def check(text):
        doc = judge.parse_json(text)
        m, problems = autoloop.move_from(doc, move_id)
        return "; ".join(problems) if problems else (("; ".join(validate(m, guide))) or None)

    out = llm.call(model, PROPOSER.read_text(), prompt, check=check)
    move, problems = autoloop.move_from(judge.parse_json(out.get("text", "")), move_id)
    if move and not problems:
        problems = validate(move, guide)
    return (move if not problems else None), problems, {"usd": out.get("usd"), "cached": out.get("cached")}


# ----- the loop -----

def per_class(dialogues, preds: dict) -> dict:
    from bench import score
    out = {}
    for dim in DIMENSIONS:
        g = data.gold(dialogues, dim)
        f = score.f1_per_class(g, {k: (preds.get(k) or {}).get(dim) for k in g})
        out[dim] = {c: round(100 * v, 1) for c, v in f.items()}
    return out


class Tuner:
    def __init__(self, dialogues, model: str, jobs: int, root: pathlib.Path = TUNE, grade=None, proposer=None):
        self.dialogues, self.model, self.jobs, self.root = dialogues, model, jobs, root
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger = self.root / "ledger.jsonl"
        self.grade = grade or self._grade
        self.proposer = proposer or propose
        self.history: list[dict] = []

    def _grade(self, guide: str, replicate: int):
        one = lambda d: judge.grade_single(d, guide, self.model, replicate=replicate)
        preds, meta = run.grade_all(self.dialogues, one, self.jobs)
        if meta.get("stopped"):
            raise llm.UsageStop(meta["stopped"])
        return preds, meta

    def score(self, preds) -> dict:
        rep = run.scores(self.dialogues, preds)
        pc = per_class(self.dialogues, preds)
        for dim in DIMENSIONS:
            rep[dim]["per_class"] = pc[dim]
        return rep

    def note(self, kind: str, payload: dict) -> None:
        ledger_mod.append(kind, payload, path=self.ledger)

    def run(self, start: str, max_moves: int = 5, aa: bool = True) -> dict:
        inc = start
        p0, m0 = self.grade(inc, 0)
        rep0 = self.score(p0)
        inc_obj = objective(rep0)
        noise = None
        p1 = None
        if aa:
            p1, _ = self.grade(inc, 1)
            noise = round(abs(objective(self.score(p1)) - inc_obj), 2)
        T = max(MIN_GAIN, noise or 0.0)
        self.note("note", {"what": "start", "objective": inc_obj, "aa_noise": noise, "T": T,
                           "dialogues": len(self.dialogues), "model": self.model})
        run.log(f"start guide: mean macro-F1 {inc_obj} (A/A noise {noise}, T {T})")
        inc_preds, inc_notes, inc_rep, inc_p1 = p0, m0.get("notes", {}), rep0, p1
        rejections, start_obj = 0, inc_obj
        for i in range(1, max_moves + 1):
            if rejections >= autoloop.MAX_REJECTIONS_IN_A_ROW:
                break
            move_id = f"g{i:02d}"
            exs = examples(self.dialogues, inc_preds, inc_notes, seed=i)
            move, problems, rec = self.proposer(inc, inc_rep, confusion(self.dialogues, inc_preds), exs,
                                                self.history, self.model, move_id)
            if move is None:
                self.note("move.rejected", {"id": move_id, "reasons": problems, "stage": "propose"})
                run.log(f"{move_id}: no valid move ({problems[:2]})")
                rejections += 1
                continue
            self.note("move.proposed", {**move.record(), "describe": move.describe()})
            variant = apply(move, inc)
            vdir = self.root / move_id
            vdir.mkdir(exist_ok=True)
            (vdir / "guide.md").write_text(variant)
            (vdir / "move.json").write_text(json.dumps(move.record(), indent=1))
            vp, vm = self.grade(variant, 0)
            vrep = self.score(vp)
            v_obj = objective(vrep)
            gain = round(v_obj - inc_obj, 2)
            pair = autoloop.paired(cells(self.dialogues, inc_preds), cells(self.dialogues, vp))
            pair.pop("tasks")
            per_dim = {SHORT[d]: round(vrep[d]["macro_f1"] - inc_rep[d]["macro_f1"], 1) for d in DIMENSIONS}
            self.note("move.evaluated", {"id": move_id, "before": inc_obj, "after": v_obj, "gain": gain,
                                         "per_dimension": per_dim, "pair": pair})
            decision, reasons, gain2 = "rejected", [], None
            if gain < T:
                reasons.append(f"gain {gain} is under T = {T}")
            else:
                if inc_p1 is None:
                    inc_p1, _ = self.grade(inc, 1)
                vp1, _ = self.grade(variant, 1)
                gain2 = round(objective(self.score(vp1)) - objective(self.score(inc_p1)), 2)
                if gain2 > 0:
                    decision = "accepted"
                else:
                    reasons.append(f"second replicate: gain {gain2} is not above 0")
            run.log(f"{move_id} {move.describe()}: {inc_obj} -> {v_obj} (gain {gain}, replicate 2 {gain2}) "
                    f"{decision} {per_dim}")
            self.history.append({"describe": move.describe(), "before": inc_obj, "after": v_obj,
                                 "decision": decision + (f" ({'; '.join(reasons)})" if reasons else ""),
                                 "rationale": move.rationale})
            if decision == "accepted":
                self.note("move.accepted", {"id": move_id, "gain": gain, "gain_replicate_2": gain2})
                inc, inc_preds, inc_notes, inc_rep, inc_obj = variant, vp, vm.get("notes", {}), vrep, v_obj
                inc_p1 = vp1
                rejections = 0
            else:
                self.note("move.rejected", {"id": move_id, "reasons": reasons, "stage": "evaluate"})
                rejections += 1
        (self.root / "incumbent.md").write_text(inc)
        summary = {"start": start_obj, "final": inc_obj, "T": T, "aa_noise": noise,
                   "accepted": [h["describe"] for h in self.history if h["decision"] == "accepted"],
                   "moves": len(self.history)}
        self.note("note", {"what": "end", **summary})
        return {**summary, "guide": inc}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bench.tune")
    ap.add_argument("--n", type=int, default=50, help="first n dialogues of dev-A")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--max-moves", type=int, default=5)
    ap.add_argument("--no-aa", action="store_true")
    a = ap.parse_args(argv)
    dialogues = data.select("dev-A", a.n)
    tuner = Tuner(dialogues, a.model, a.jobs)
    try:
        out = tuner.run(judge.GUIDE.read_text(), a.max_moves, aa=not a.no_aa)
    except llm.UsageStop as err:
        run.log(f"stopped on usage limit: {err}")
        return 1
    TUNED.write_text(out.pop("guide"))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

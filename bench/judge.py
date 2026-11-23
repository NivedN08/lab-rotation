"""Grades tutor replies: one model alone, or the panel (two blind readers and a referee).

One call grades every reply of one dialogue (about 8), so a dialogue costs one call for
the single model and two or three for the panel. Replies get neutral ids R1..Rn in a
seeded order (tutor names such as "Expert" would leak), and the dialogue and replies
are passed as quoted data.

Panel: reader 1 sees the replies in id order, reader 2 in reverse order; neither sees
the other. Labels they agree on stand. When they disagree on any label of a dialogue,
the referee sees both readers' labels and notes for the disputed replies and settles
each disputed label. A label the referee leaves unsettled falls back to reader 1.
"""

from __future__ import annotations

import json
import pathlib
import random
import re

from bench import llm
from bench.data import DIMENSIONS, LABELS, SHORT, Dialogue, Reply
from lab.autoloop import sections

HERE = pathlib.Path(__file__).resolve().parent
GUIDE = HERE / "guide.md"
REFEREE = HERE / "referee.md"
FULL = {v: k for k, v in SHORT.items()}
CODES = tuple(SHORT[d] for d in DIMENSIONS)
NOTE_CHARS = 200
SYNONYMS = {"yes": "Yes", "no": "No", "to some extent": "To some extent", "some extent": "To some extent",
            "partially": "To some extent", "partly": "To some extent", "partial": "To some extent",
            "somewhat": "To some extent"}


def normalise(label) -> str | None:
    if not isinstance(label, str):
        return None
    return SYNONYMS.get(label.strip().strip(".").lower())


def order(dialogue: Dialogue) -> list[tuple[str, Reply]]:
    """(id, reply) with ids R1..Rn over a shuffle seeded by the dialogue id."""
    replies = sorted(dialogue.replies, key=lambda r: r.tutor)
    random.Random(dialogue.id).shuffle(replies)
    return [(f"R{i}", r) for i, r in enumerate(replies, 1)]


def quote(text: str) -> str:
    return text.replace("<", "‹").replace(">", "›")


def item_prompt(dialogue: Dialogue, ids: list[tuple[str, Reply]]) -> str:
    lines = ["The tutoring dialogue so far (quoted data):", "<dialogue>", quote(dialogue.history.strip()),
             "</dialogue>", "", f"Candidate next tutor turns to grade ({len(ids)}):"]
    for rid, r in ids:
        lines += [f'<reply id="{rid}">', quote(r.text.strip()), "</reply>"]
    lines += ["", "Grade every reply on MI, ML, PG and AC. Answer with the JSON object only."]
    return "\n".join(lines)


def parse_json(text: str):
    """The first JSON object in a reply (code fences and surrounding prose allowed)."""
    start = text.find("{")
    while start != -1:
        try:
            return json.JSONDecoder().raw_decode(text[start:])[0]
        except ValueError:
            start = text.find("{", start + 1)
    return None


def parse_labels(text: str, rids: list[str], codes=CODES) -> tuple[dict, list[str]]:
    """{rid: {code: label, "note": str}} from a reader's answer, and what is missing."""
    doc = parse_json(text)
    if not isinstance(doc, dict):
        return {}, ["no JSON object"]
    out, missing = {}, []
    for rid in rids:
        row = doc.get(rid) if isinstance(doc.get(rid), dict) else {}
        got = {c: normalise(row.get(c)) for c in codes}
        missing += [f"{rid}.{c}" for c, v in got.items() if v is None]
        out[rid] = {c: v for c, v in got.items() if v is not None}
        if isinstance(row.get("note"), str):
            out[rid]["note"] = row["note"][:NOTE_CHARS]
    return out, missing


def checker(rids: list[str], codes=CODES):
    def check(text: str) -> str | None:
        _, missing = parse_labels(text, rids, codes)
        return None if not missing else "missing " + ", ".join(missing[:6])
    return check


def to_keys(labels: dict, ids: list[tuple[str, Reply]]) -> dict:
    """{reply key: {dimension: label}} from {rid: {code: label}}."""
    return {r.key: {FULL[c]: v for c, v in labels.get(rid, {}).items() if c in FULL and v in LABELS}
            for rid, r in ids}


def read(dialogue: Dialogue, guide: str, model: str, *, reverse: bool = False, replicate: int = 0,
         runner=llm.run_cli, cache=llm.CACHE) -> tuple[dict, dict]:
    """One reader's labels {rid: {...}} and the call's record."""
    ids = order(dialogue)
    shown = list(reversed(ids)) if reverse else ids
    rids = [rid for rid, _ in ids]
    out = llm.call(model, guide, item_prompt(dialogue, shown), replicate=replicate, runner=runner,
                   cache=cache, check=checker(rids))
    labels, _ = parse_labels(out.get("text", ""), rids)
    return labels, {"usd": out.get("usd"), "cached": out.get("cached"), "error": out.get("error")}


def grade_single(dialogue: Dialogue, guide: str, model: str, *, replicate: int = 0, runner=llm.run_cli,
                 cache=llm.CACHE) -> tuple[dict, dict]:
    labels, rec = read(dialogue, guide, model, replicate=replicate, runner=runner, cache=cache)
    return to_keys(labels, order(dialogue)), {"calls": [rec]}


def referee_system(referee: str, guide: str) -> str:
    """The referee's prompt plus the readers' guide, without the guide's role and output sections."""
    keep = [(t, s, e) for t, s, e in sections(guide) if t not in ("Role", "Output", "Grading guide")]
    lines = guide.splitlines(keepends=True)
    parts = [referee.rstrip("\n"), "", "## The examiners' grading guide", ""]
    for title, start, end in keep:
        parts += [f"### {title}", "".join(lines[start:end]).strip("\n"), ""]
    return "\n".join(parts)


def disputes(a: dict, b: dict, rids: list[str]) -> dict[str, list[str]]:
    out = {}
    for rid in rids:
        codes = [c for c in CODES if (a.get(rid) or {}).get(c) != (b.get(rid) or {}).get(c)]
        if codes:
            out[rid] = codes
    return out


def referee_prompt(dialogue: Dialogue, ids: list[tuple[str, Reply]], a: dict, b: dict,
                   disputed: dict[str, list[str]]) -> str:
    lines = ["The tutoring dialogue so far (quoted data):", "<dialogue>", quote(dialogue.history.strip()),
             "</dialogue>", "", "Replies with disputed labels:"]
    for rid, r in ids:
        if rid not in disputed:
            continue
        lines += [f'<reply id="{rid}">', quote(r.text.strip()), "</reply>"]
        for name, x in (("Examiner 1", a), ("Examiner 2", b)):
            row = x.get(rid) or {}
            labels = ", ".join(f"{c} {row.get(c, '?')}" for c in CODES)
            lines.append(f"{name}: {labels}. Note: {quote(str(row.get('note', '')))}")
        lines += [f"Disputed: {', '.join(disputed[rid])}", ""]
    lines.append("Settle every disputed label. Answer with the JSON object only.")
    return "\n".join(lines)


def grade_panel(dialogue: Dialogue, guide: str, referee: str, models: tuple[str, str, str], *,
                replicate: int = 0, runner=llm.run_cli, cache=llm.CACHE) -> tuple[dict, dict]:
    """models: (reader 1, reader 2, referee)."""
    ids = order(dialogue)
    rids = [rid for rid, _ in ids]
    a, rec_a = read(dialogue, guide, models[0], replicate=replicate, runner=runner, cache=cache)
    b, rec_b = read(dialogue, guide, models[1], reverse=True, replicate=replicate, runner=runner, cache=cache)
    disputed = disputes(a, b, rids)
    calls = [rec_a, rec_b]
    settled = {}
    if disputed:
        system = referee_system(referee, guide)
        prompt = referee_prompt(dialogue, ids, a, b, disputed)

        def check(text: str) -> str | None:
            doc = parse_json(text)
            if not isinstance(doc, dict):
                return "no JSON object"
            miss = [f"{rid}.{c}" for rid, cs in disputed.items() for c in cs
                    if normalise((doc.get(rid) or {}).get(c) if isinstance(doc.get(rid), dict) else None) is None]
            return "missing " + ", ".join(miss[:6]) if miss else None

        out = llm.call(models[2], system, prompt, replicate=replicate, runner=runner, cache=cache, check=check)
        calls.append({"usd": out.get("usd"), "cached": out.get("cached"), "error": out.get("error")})
        doc = parse_json(out.get("text", "")) or {}
        settled = {rid: {c: normalise((doc.get(rid) or {}).get(c)) for c in cs}
                   for rid, cs in disputed.items() if isinstance(doc.get(rid), dict)}
    final = {}
    for rid in rids:
        row = {}
        for c in CODES:
            va, vb = (a.get(rid) or {}).get(c), (b.get(rid) or {}).get(c)
            if va == vb and va is not None:
                row[c] = va
            else:
                row[c] = (settled.get(rid) or {}).get(c) or va or vb
        final[rid] = {c: v for c, v in row.items() if v is not None}
    n_cells = sum(len(cs) for cs in disputed.values())
    return to_keys(final, ids), {"calls": calls, "disputed_cells": n_cells, "cells": len(rids) * len(CODES),
                                 "readers": {"1": to_keys(a, ids), "2": to_keys(b, ids)}}

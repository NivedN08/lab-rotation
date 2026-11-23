"""Quote check: every quote in feedback must appear word for word in its source.

Sources are the learner's answer note (`"note"`) and the SQL of the learner's queries
(the source is the SQL text itself). A quote is text between double quotes (straight or
curly). A quote found in no source is dropped together with the sentence that holds it.
"""

from __future__ import annotations

import re

QUOTE = re.compile(r"[\"“”]([^\"“”]{3,300})[\"“”]")
SENTENCE = re.compile(r"[^.!?]*[.!?]+[\"”]?\s*|[^.!?]+$")


def _norm(s: str) -> str:
    return " ".join(s.split())


def find_source(quote: str, note: str, sqls: list[str]) -> str | None:
    q = _norm(quote)
    if q and q in _norm(note or ""):
        return "note"
    for sql in sqls:
        if q and q in _norm(sql or ""):
            return sql
    return None


def check(text: str, note: str, sqls: list[str]) -> tuple[str, list[dict], list[str]]:
    """(text with bad quotes removed, [{text, source}] kept, [dropped quotes])."""
    kept, dropped = [], []
    out_sentences = []
    for sentence in SENTENCE.findall(text or ""):
        bad = False
        found = []
        for m in QUOTE.finditer(sentence):
            src = find_source(m.group(1), note, sqls)
            if src is None:
                bad = True
                dropped.append(m.group(1))
            else:
                found.append({"text": _norm(m.group(1)), "source": src})
        if not bad:
            out_sentences.append(sentence)
            kept.extend(found)
    cleaned = "".join(out_sentences).strip()
    return cleaned, kept, dropped


def safe_fragment(note: str, limit: int = 70) -> str | None:
    """A short verbatim piece of the note to quote (the first clause), or None."""
    note = _norm(note or "")
    if len(note) < 8:
        return None
    piece = re.split(r"[.;:!?]", note)[0].strip()
    if len(piece) > limit:
        piece = piece[:limit].rsplit(" ", 1)[0]
    return piece if len(piece) >= 8 else None

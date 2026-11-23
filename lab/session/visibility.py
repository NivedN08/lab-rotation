"""What each agent may read, enforced in code (summit-lab's `visible_docs` idea).

`view(agent, s)` returns `[(source name in plain words, text)]` built only from the parts
of the session that agent's role may see. Everyone sees the public task (title, claim,
brief: it is on the learner's screen). Beyond that:

- vale: the learner profile, the panel's whispers, the check results (after the answer)
- ines: the answer key, the check output (after the answer), the learner's answer
- sam: the learner's queries and actions, the answer, the struggle meter, the whispers
- telem: only its own search results
- riley: only the public tables

No other agent's input ever contains the key, and no text built here reaches the browser
before the verdict except through the agent's own (checked) words.
"""

from __future__ import annotations

import json

READS = {
    "vale": ("learner profile", "panel whispers", "check results"),
    "ines": ("answer key", "check output", "learner's answer"),
    "sam": ("your queries", "your actions", "your answer", "struggle meter", "panel whispers"),
    "telem": ("Telem's search results",),
    "riley": ("public tables",),
}


def _task_events(s, kinds: tuple[str, ...]) -> list[dict]:
    slot = s.slot
    return [e for e in s.log.events if e["k"] in kinds and (slot is None or e.get("task") == slot.id)]


def public_task(s) -> tuple[str, str]:
    p = s.slot.task.public if s.slot else {}
    return ("the task", f"Title: {p.get('title', '')}\nClaim: {p.get('claim', '')}\nBrief: {p.get('brief', '')}")


def learner_profile(s) -> tuple[str, str]:
    rows = s.mastery_now()["traps"]
    past = [f"{x.id}: score {x.grade['score']}" for x in s.slots if x.grade]
    return ("learner profile", "Mastery (0 to 1): " + ", ".join(f"{r['trap']} {r['score']:.2f}" for r in rows)
            + (f"\nThis session so far: {'; '.join(past)}" if past else "\nThis session so far: no graded tasks")
            + f"\nWrong answers this session: {s.wrong_guesses}")


def whispers(s) -> tuple[str, str]:
    ws = _task_events(s, ("panel.whisper",))
    text = "\n".join(f"[{e['t']:.0f}s] {e['agent']} to {e.get('to')}: {e['data'].get('text', '')}" for e in ws)
    return ("panel whispers", text or "none yet")


def checks(s) -> tuple[str, str]:
    cs = s.slot.checks if s.slot else []
    text = "\n".join(f"{c['check']}: {'passed' if c['passed'] else 'FAILED'} ({c['detail']})" for c in cs)
    return ("check results", text or "not run yet")


def key(s) -> tuple[str, str]:
    k = s.slot.task.key
    return ("answer key", f"Trap: {k['trap']}\nCorrect verdict: {k['verdict']}\n"
                          f"Careful analysis: {k.get('careful', {}).get('note', '')}\n"
                          f"Columns that matter: {', '.join(k.get('columns') or [])}")


def answer(s) -> tuple[str, str]:
    a = s.slot.answer if s.slot else None
    if not a:
        return ("learner's answer", "not answered yet")
    ev = "; ".join(i.get("label") or i.get("column") or "" for i in a.get("evidence") or [])
    return ("learner's answer", f"Verdict: {a['verdict']}\nTrap: {a['trap']}\nNote (their own words): "
                                f"{json.dumps(a.get('note', ''))}\nEvidence: {ev or 'none'}")


def queries(s) -> tuple[str, str]:
    qs = _task_events(s, ("learner.query",))
    lines = [f"[{e['t']:.0f}s] {e['data']['queryId']} {'ok' if e['data']['ok'] else 'error'}"
             f"{' useful' if e['data'].get('useful') else ''}: {e['data']['sql']}" for e in qs]
    return ("your queries", "\n".join(lines[-15:]) or "no queries yet")


def actions(s) -> tuple[str, str]:
    acts = _task_events(s, ("learner.evidence", "ask", "agent.say"))
    lines = []
    for e in acts:
        if e["k"] == "ask":
            lines.append(f"[{e['t']:.0f}s] asked {e.get('to')}: {e.get('text', '')}")
        elif e["k"] == "agent.say" and (e.get("data") or {}).get("hintLevel"):
            lines.append(f"[{e['t']:.0f}s] Sam gave a level {e['data']['hintLevel']} hint: {e.get('text', '')}")
        elif e["k"] == "learner.evidence":
            lines.append(f"[{e['t']:.0f}s] cited {len(e['data'].get('items') or [])} items")
    return ("your actions", "\n".join(lines) or "none yet")


def meter(s) -> tuple[str, str]:
    m = s.meter_now()
    return ("struggle meter", f"value {m['value']}, idle {m['idleSeconds']} s, dead ends {m['deadEnds']}, "
                              f"wrong answers {m['wrongGuesses']}, suggested hint level {m['hintLevel']}, "
                              f"hints given {s.slot.hints if s.slot else 0}")


def search_results(s) -> tuple[str, str]:
    found = s.slot.search if s.slot else None
    if not found:
        return ("Telem's search results", "none")
    lines = [f"- {r.get('title', '')}: {r.get('snippet', '')} ({r.get('url', '')})" for r in found.get("results", [])]
    return ("Telem's search results", "\n".join(lines) or "no results")


def public_tables(s) -> tuple[str, str]:
    from lab.session import sources
    if not s.slot:
        return ("public tables", "none")
    out = []
    for t in sources.ws_tables(s.slot.task.dir):
        cols = ", ".join(f"{c['name']} ({c['type']})" for c in t["columns"])
        out.append(f"{t['name']} ({t['rowCount']} rows): {cols}")
    return ("public tables", "\n".join(out) + "\nData dictionary:\n" + s.slot.task.public.get("dictionary", ""))


def view(agent: str, s) -> list[tuple[str, str]]:
    after = bool(s.slot and s.slot.answer)
    parts = [public_task(s)]
    if agent == "vale":
        parts += [learner_profile(s), whispers(s)] + ([checks(s)] if after else [])
    elif agent == "ines":
        parts += [key(s)] + ([checks(s), answer(s)] if after else [])
    elif agent == "sam":
        parts += [queries(s), actions(s), meter(s), whispers(s)] + ([answer(s)] if after else [])
    elif agent == "telem":
        parts += [search_results(s)]
    elif agent == "riley":
        parts += [public_tables(s)]
    else:
        raise KeyError(agent)
    return parts


def sources_used(agent: str, parts: list[tuple[str, str]]) -> list[str]:
    """Plain-words names of what an answer drew on (for `ask.answer`)."""
    names = [name for name, text in parts if text and text not in ("none", "none yet", "not run yet",
                                                                     "no queries yet", "not answered yet")]
    return names

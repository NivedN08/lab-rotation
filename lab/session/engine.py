"""The session engine: runs a Lab Rotation session and records every step.

One `Session` per learner sitting. Its events go to `data/sessions/<id>.jsonl` as they
happen (`lab.session.log`), and its private state (bank ids, never sent to the browser) to
`data/sessions/<id>.state.json`, so a restarted server serves and resumes it.

Flow per task slot (`t1`, `t2`, `t3`): Vale picks it with the learner model and briefs the
learner; Telem brings a real case; the learner explores (every query is logged and moves
the struggle meter; Sam hints when it climbs, after checking with the panel); the learner
answers; Riley answers too; the panel confers in its BAND room; Ines runs the checks,
the grade is computed from the key and sealed in the hash-chained ledger; Ines delivers
the verdict quoting the learner's own words (quote-checked); mastery updates; the next
task is picked. Rotation mode has 3 slots with rising tiers; judge mode has one, 240 s.

HTTP threads call the `on_*` methods, which log the learner's action at once and queue
the panel's work for the session's worker thread, so replies never wait on an agent
(except `ask`, which is a question and waits for its answer).
"""

from __future__ import annotations

import json
import os
import pathlib
import queue
import random
import secrets
import threading
import time
import traceback
from dataclasses import dataclass, field

from lab import ledger
from lab.session import fallback, grade as grading, meter, quotes, sources, speaker, summary
from lab.session.log import SessionLog, read_events, session_path, sessions_dir
from lab.session.visibility import sources_used, view

TICK_S = 2.0
HINT_GAP_S = 20.0
JUDGE_SECONDS = 240
DEFAULT_SECONDS = 600
TRAP_LABEL = {"duplicate_rows": "duplicated rows", "unit_mismatch": "unit mix-up",
              "dictionary_flip": "dictionary flip", "confounder": "confounder",
              "hidden_variable": "hidden variable", "none": "clean result"}
LEAK = {"duplicate_rows": ("duplicate_rows", "duplicate", "double-count", "counted twice"),
        "unit_mismatch": ("unit_mismatch", "unit mix", "cents"),
        "dictionary_flip": ("dictionary_flip", "dictionary flip", "coded backwards", "flipped"),
        "confounder": ("confounder", "confound"),
        "hidden_variable": ("hidden_variable", "hidden variable"),
        "none": ()}
SPONSOR_WHY = {"band": "the panel talks in its BAND room",
               "telem": "the librarian finds real cases with Telem AI",
               "runware": "every spoken line is a Runware voice",
               "bruin": "Bruin's checks prove the planted trap",
               "glasser": "real retail numbers come from Glasser",
               "teamily": "the practice summary goes to Teamily"}


HOME = {"vale": "vale_office", "ines": "terminal", "sam": "whiteboard", "telem": "door", "riley": "door"}

# The `why` of a panel.whisper is shown before the verdict while its text is sealed, so it
# comes only from this fixed table (by speaker and purpose), never from agent output.
WHISPER_WHY = {
    ("sam", "hint_ask"): "Sam asks the panel before a hint",
    ("ines", "hint_steer"): "Ines gives Sam a direction",
    ("vale", "hint_ok"): "Vale approves the hint level",
    ("ines", "grade_basis"): "Ines shares the basis for the grade",
    ("sam", "coaching"): "Sam reports the coaching history",
    ("vale", "decide"): "Vale decides the verdict",
}


def _label(b: dict) -> str:
    lab_ = str(b.get("label") or f"a typical {b.get('kind', 'basket')}").strip()
    return lab_[0].lower() + lab_[1:] if lab_[:1].isupper() and lab_[1:2].islower() else lab_


def telem_reply(found: dict) -> str:
    """Telem's answer to a question, built from the search results (quoted web text)."""
    rs = found.get("results") or []
    first = rs[0]
    text = f"I looked that up. \"{first.get('title', '')}\": {first.get('snippet', '')}".strip()
    if len(rs) > 1:
        text += f" Also: \"{rs[1].get('title', '')}\"."
    return text[:600] + " The sources are on the card."


class EngineError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def ledger_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("LAB_GRADE_LEDGER") or sessions_dir().parent / "ledger" / "grades.jsonl")


def leaks(text: str, trap: str) -> bool:
    low = (text or "").lower()
    return any(w in low for w in LEAK.get(trap, ()))


def leaks_any(text: str) -> bool:
    """True if the text names any trap. Pre-answer lines use this, not `leaks(text, trap)`:
    replacing a line only when it names *this* task's trap would itself tell the trap apart
    from a clean twin."""
    return any(leaks(text, t) for t in LEAK)


def trap_words(text: str) -> set[str]:
    low = (text or "").lower()
    return {w for ws in LEAK.values() for w in ws if w in low}


def leaks_beyond(reply: str, question: str) -> bool:
    """Telem's ask rule: a reply may use a trap word only if the learner's question did.
    Telem never sees the task's data, so its reply is the same for a clean twin."""
    return bool(trap_words(reply) - trap_words(question))


# Vale says this in every first brief when the news was read, steered or not, trap or clean:
# a line said only when the news steered the pick would tell the learner the task has a trap.
NEWS_BRIEF = "Telem's monitor read the news this morning; I'll tell you after the verdict whether it shaped this pick."
NEWS_WAIT_S = 3.0


def topic_query(claim: str) -> str:
    """Telem's pre-answer search: built from the public claim only, so a clean twin with the
    same claim gets the same search."""
    return f"retail data: {claim}"[:160]


@dataclass
class Slot:
    id: str
    tier: int
    task: sources.BankTask | None = None
    pick: dict | None = None
    phase: str = "waiting"           # waiting, brief, analysis, grading, done
    opened_t: float | None = None
    seconds: int = DEFAULT_SECONDS
    answer: dict | None = None
    grade: dict | None = None
    rival: dict | None = None
    hints: int = 0
    last_hint_t: float = -1e9
    checks: list = field(default_factory=list)
    search: dict | None = None       # Telem's topic search (before the answer)
    case: dict | None = None         # Telem's real case of this trap (after the verdict)
    seen_cols: set = field(default_factory=set)
    last_meter: dict | None = None
    last_meter_t: float = -1e9
    ledger: dict | None = None

    def public(self) -> dict | None:
        if not self.task:
            return None
        p = dict(self.task.public)
        p["id"], p["tier"], p["seconds"] = self.id, self.tier, self.seconds
        return {k: p.get(k) for k in ("id", "title", "brief", "seconds", "claim", "tier", "dictionary")}


class Session:
    def __init__(self, engine: "Engine", sid: str, mode: str, learner: str, log: SessionLog):
        self.engine, self.id, self.mode, self.learner, self.log = engine, sid, mode, learner, log
        n = 1 if mode == "judge" else 3
        self.slots = [Slot(f"t{i + 1}", tier=1 if mode == "judge" else i + 1) for i in range(n)]
        self.idx = 0
        self.wrong_guesses = 0
        self.qn = 0
        self.appeals: dict[str, dict] = {}
        self.finished = False
        self.rng = random.Random(sid)
        self.q: queue.Queue = queue.Queue()
        self.lock = threading.RLock()
        self.room = None
        self.retail: dict | None = None
        self.news: dict | None = None    # Telem's case of the day, read before the first pick
        self.where = dict(HOME)
        self._sponsors = None
        self.thread: threading.Thread | None = None

    @property
    def sponsors(self) -> sources.Sponsors:
        if self._sponsors is None:
            self._sponsors = sources.Sponsors(self.on_call)
        return self._sponsors

    # ------------------------------------------------------------------ views for agents
    @property
    def slot(self) -> Slot | None:
        return self.slots[min(self.idx, len(self.slots) - 1)] if self.slots else None

    def slot_by_id(self, task_id: str | None) -> Slot | None:
        if task_id is None:
            return self.slot
        return next((s for s in self.slots if s.id == task_id), None)

    def mastery_now(self) -> dict:
        return sources.mastery(self.learner)

    def meter_now(self) -> dict:
        s = self.slot
        return meter.reading(self.log.events, s.id if s else "", self.log.now(), self.wrong_guesses)

    # ----------------------------------------------------------------------- logging
    def emit(self, k, agent, why, **kw) -> dict:
        return self.log.append(k, agent, why, **kw)

    def on_call(self, call) -> None:
        """A sponsor client reports a call: log it as `sponsor.call`."""
        try:
            data = call.event_data() if hasattr(call, "event_data") else dict(call)
        except Exception:
            return
        if not data.get("sponsor") or not data.get("label"):
            return
        data.setdefault("count", 1)
        self.emit("sponsor.call", "system", SPONSOR_WHY.get(data["sponsor"], "a sponsor service was called"),
                  data=data)

    def say(self, agent: str, text: str, why: str, to: str | None = "learner", task: str | None = None,
            data: dict | None = None) -> dict:
        e = self.emit("agent.say", agent, why, to=to, text=text, task=task, data=data)
        speaker.POOL.submit(self._voice, agent, text, e["seq"], task)
        return e

    def _voice(self, agent: str, text: str, line_of: int, task: str | None) -> None:
        try:
            v = sources.tts(self.sponsors, agent, text, line_of=line_of)
            data = {"file": v["file"], "lineOf": line_of, "seconds": v["seconds"], "provider": v["provider"]}
            if v.get("cost") is not None and v["provider"] == "runware":
                data["cost"] = v["cost"]
            self.emit("voice.line", agent, "speak the line in the agent's own voice"
                      if v["provider"] == "runware" else "no voice file, so the browser speaks the line",
                      task=task, data=data)
        except Exception as e:
            self.engine.log_error(self, "voice", e)

    def move(self, agent: str, place: str, why: str, to: str | None = None) -> None:
        """Walk an agent to a place; `from` is where it really is. A walk to where it stands is skipped."""
        frm = self.where.get(agent, "door")
        if frm == place:
            return
        self.where[agent] = place
        self.emit("agent.move", agent, why, to=to, task=self.slot.id if self.slot else None,
                  data={"from": frm, "place": place})

    def whisper(self, agent: str, to: str, text: str, purpose: str, cc: list[str] = ()) -> dict:
        why = WHISPER_WHY[(agent, purpose)]   # a fixed template: never built from the text
        posted = sources.band_post(self.room, agent, text, [to, *cc])
        data = {"text": text, "cc": list(cc), "local": posted["local"]}
        if posted.get("id") and not posted["local"]:
            data["bandMessageId"] = str(posted["id"])
        return self.emit("panel.whisper", agent, why, to=to, task=self.slot.id, data=data)

    # ----------------------------------------------------------------- private state
    def save(self) -> None:
        state = {"mode": self.mode, "learner": self.learner, "idx": self.idx, "qn": self.qn,
                 "wrong": self.wrong_guesses, "finished": self.finished, "appeals": self.appeals,
                 "where": self.where, "news": self.news,
                 "slots": [{"id": s.id, "tier": s.tier, "bankId": s.task.bank_id if s.task else None,
                            "pick": s.pick, "phase": s.phase, "hints": s.hints, "seconds": s.seconds,
                            "openedT": s.opened_t, "answer": s.answer, "grade": s.grade,
                            "checks": s.checks, "search": s.search, "case": s.case, "seenCols": sorted(s.seen_cols),
                            "ledger": s.ledger, "rival": s.rival} for s in self.slots]}
        path = self.log.path.with_suffix(".state.json")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, default=str))
        tmp.replace(path)

    # ----------------------------------------------------------------------- worker
    def start_worker(self) -> None:
        self.thread = threading.Thread(target=self._run, name=f"session-{self.id}", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self.finished or not self.q.empty():
            try:
                action = self.q.get(timeout=TICK_S)
            except queue.Empty:
                action = ("tick",)
            try:   # no session lock here: agent turns are slow and SQL must not wait on them
                getattr(self, "do_" + action[0])(*action[1:])
            except Exception as e:
                self.engine.log_error(self, action[0], e)
            if self.finished and self.q.empty() and not self._open_appeals():
                break

    def _open_appeals(self) -> bool:
        return any(not a.get("ruled") for a in self.appeals.values())

    # ------------------------------------------------------------------- task flow
    def pick_task(self) -> None:
        s = self.slot
        seen_traps = [x.task.key["trap"] for x in self.slots if x.task]
        seen_ids = [x.task.bank_id for x in self.slots if x.task]
        pick = sources.pick_next(self.learner, seen_traps, seen_ids, s.tier, self.rng, nudge=self.nudge_for(s))
        bank_id = pick.get("bankId") or sources.bank_pick(pick["skill"], s.tier, seen_ids)
        s.task = sources.bank_load(bank_id)
        s.pick = pick
        public_text = " ".join(str(s.task.public.get(f) or "") for f in ("title", "brief", "claim"))
        if leaks(public_text, s.task.key["trap"]):   # the bank's text is shown before the answer
            self.engine.note(self, f"task {bank_id}: its title, brief or claim names its trap")
        s.seconds = JUDGE_SECONDS if self.mode == "judge" else int(s.task.public.get("seconds") or DEFAULT_SECONDS)
        s.phase = "brief"
        first = s.id == "t1"
        reason = ("new learner with no history: start at tier 1" if first and not any(
            r["attempts"] for r in self.mastery_now()["traps"]) else
                  f"tier {s.tier} next; the learner model favours the skills you have shown least")
        p = s.public()
        self.emit("task.picked", "vale", reason, task=s.id, text=f"Vale picked task {s.id[1:]}.",
                  data={"taskId": s.id, "title": p["title"], "brief": p["brief"], "seconds": p["seconds"],
                        "dictionary": p["dictionary"], "tier": s.tier, "claim": p["claim"], "reason": reason,
                        "fallback": bool(pick.get("fallback") or s.task.stub)})
        self.save()
        self.q.put(("brief",))

    def nudge_for(self, s: Slot) -> dict | None:
        """The news nudges the first pick only, so its reveal after t1's verdict covers it."""
        n = self.news or {}
        if s.id != "t1" or n.get("trap") not in TRAP_LABEL or n.get("trap") == "none":
            return None
        return {"trap": n["trap"], "headline": n.get("title", ""), "url": n.get("url", ""),
                "trace": n.get("trace", "")}

    def do_tick(self) -> None:
        s = self.slot
        if self.finished or not s or s.phase != "analysis":
            return
        now = self.log.now()
        if s.opened_t is not None and now - s.opened_t >= s.seconds:
            with self.lock:
                if s.phase == "analysis":
                    self.engine.submit_answer(self, {"taskId": s.id, "verdict": "cant_tell", "trap": "none",
                                                     "evidence": [], "note": ""}, timed_out=True)
            return
        m = self.meter_now()
        last = s.last_meter
        changed = last is None or m["hintLevel"] != last["hintLevel"] or abs(m["value"] - last["value"]) >= 0.2
        if changed and now - s.last_meter_t >= 8:
            self.emit_meter(m)
        if m["hintLevel"] > s.hints and s.hints < 3 and now - s.last_hint_t >= HINT_GAP_S:
            self.give_hint(s.hints + 1, m)

    def emit_meter(self, m: dict, cause: str = "moved") -> None:
        s = self.slot
        s.last_meter, s.last_meter_t = m, self.log.now()
        self.emit("meter.update", "system", meter.why(cause), task=s.id, data=m)

    def do_brief(self) -> None:
        s = self.slot
        p = s.public()
        self.move("vale", "learner_desk", "brief the learner in person", to="learner")
        brief_fallback = f"{p['brief']} The claim: {p['claim']} Check it before it goes any further."
        vale_job = ("Brief the learner on this task in two or three short sentences: the claim, who wants it, "
                    "and why it must be checked. Do not hint at what might be wrong.")
        vale_f = speaker.submit("vale", vale_job, view("vale", self), brief_fallback, 55)
        query = topic_query(p["claim"])
        search_f = speaker.POOL.submit(sources.telem_topic, self.sponsors, query)
        line, used_fb = vale_f.result()
        if leaks_any(line):
            line = brief_fallback
        if s.id == "t1" and self.news:
            line = f"{line} {NEWS_BRIEF}"
        self.say("vale", line, "deliver the brief and the claim", task=s.id)
        self.move("telem", "shelves", "look up background on the claim")
        found = search_f.result()
        s.search = found
        self.emit("search", "telem", "background on the claim's topic; the search uses only the public claim",
                  task=s.id, text="Telem looked up background on the claim.",
                  data={"phase": "topic", "query": found.get("query", query), "results": found.get("results", []),
                        "trace": found.get("trace", ""), "cached": bool(found.get("cached"))})
        self.move("telem", "learner_desk", "bring background on the claim", to="learner")
        telem_fb = "Some background on claims like this one: the sources are on the card."
        tline, _ = speaker.call("telem", "Before the learner starts, give one or two sentences of background on "
                                         "the claim's topic from your search results. Say nothing about what "
                                         "could be wrong with any dataset.", view("telem", self), telem_fb, 45)
        if leaks_any(tline):
            tline = telem_fb
        self.say("telem", tline, "background on the claim's topic, with its sources", task=s.id)
        self.move("vale", "vale_office", "brief done; let the learner work")
        self.move("telem", "shelves", "back to the shelves")
        self.move("riley", "riley_desk", "the intern races the learner on the same task")
        s.phase = "analysis"
        s.opened_t = self.log.now()
        self.save()

    def give_hint(self, level: int, m: dict) -> None:
        s, key = self.slot, self.slot.task.key
        ladder = key.get("hints") or fallback.HINTS.get(key["trap"], [])
        hint = ladder[min(level, len(ladder)) - 1] if ladder else "What would you check first if this were your data?"
        sam_fb = (f"The learner has {m['deadEnds']} dead ends and {m['idleSeconds']} s without a useful query. "
                  f"I'd like to give a level {level} hint.")
        sam_line, _ = speaker.call("sam", f"Tell Vale and Ines privately, in one sentence, what the learner has "
                                          f"tried and that you want to give a level {level} hint.",
                                   view("sam", self), sam_fb, 40)
        self.whisper("sam", "vale", sam_line, "hint_ask", cc=["ines"])
        self.whisper("ines", "sam", f"Steer them here, as a question: {hint}", "hint_steer")
        self.whisper("vale", "sam", "Go ahead, keep it a question.", "hint_ok")
        self.move("sam", "learner_desk", f"the struggle meter reached {m['value']}", to="learner")
        bought = sources.glasser_benchmark(self.on_call, key.get("benchmark") or "basket", "sam") \
            if level == 2 else None
        if bought:   # built in code so the numbers are exactly Glasser's
            paid = (f"I spent ${float(bought['cost']):.3f} to check" if bought.get("cost") and
                    sources.from_glasser(bought) else "I checked")
            line = f"{paid}: {_label(bought)} is typically {sources.benchmark_range(bought)}. {hint}"
        else:
            line, _ = speaker.call("sam", "Ask the learner one short question that points where Ines suggested. "
                                          "Do not give the answer.", view("sam", self), hint, 30)
        if leaks(line, key["trap"]):
            line = hint
        s.hints, s.last_hint_t = level, self.log.now()
        data = {"hintLevel": level}
        if bought:
            data["bought"] = {"sponsor": "glasser", **{k: bought.get(k) for k in ("kind", "label", "cost", "source",
                                                                                  "trace")}}
        self.say("sam", line, f"struggle meter {m['value']}; hint level {level}, as a question"
                 + ("; Sam bought a fact from Glasser" if bought else ""), task=s.id, data=data)
        self.move("sam", "whiteboard", "back to the whiteboard to watch")
        self.save()

    # ------------------------------------------------------------------------- grading
    def do_grade(self) -> None:
        s = self.slot
        key, ans = s.task.key, s.answer
        bench_f = speaker.POOL.submit(sources.glasser_benchmark, self.on_call, key.get("benchmark") or "basket",
                                      "ines")   # after the answer, so the lookup tells nothing
        self.rival_answer()
        for agent in ("vale", "ines", "sam"):
            self.move(agent, "panel_table", "the panel confers before the verdict")
        s.checks, bruin_call = sources.run_checks(s.task)
        g = grading.grade(ans, key, s.hints)
        facts = (f"Score {g['score']} ({g['result']}); verdict part {g['parts']['verdict']}, trap part "
                 f"{g['parts']['trap']}, evidence part {g['parts']['evidence']}, hints {g['parts']['hints']}.")
        ines_fb = (f"The key says {key['trap']}, verdict {key['verdict']}. The learner said {ans['trap']}, "
                   f"{ans['verdict']}. {facts}")
        sam_fb = (f"They needed {s.hints} hint{'s' if s.hints != 1 else ''}." if s.hints else
                  "They needed no hints.")
        ines_f = speaker.submit("ines", "Tell Vale and Sam privately what the key says and how the learner's "
                                        "answer compares, in one or two sentences. " + facts,
                                view("ines", self), ines_fb, 45)
        sam_f = speaker.submit("sam", "Tell Ines and Vale privately, in one sentence, how the learner worked: "
                                      "hints needed, dead ends, recoveries.", view("sam", self), sam_fb, 35)
        self.whisper("ines", "vale", ines_f.result()[0], "grade_basis", cc=["sam"])
        self.whisper("sam", "ines", sam_f.result()[0], "coaching", cc=["vale"])
        vale_line, _ = speaker.call("vale", "Decide with the panel in one or two sentences and ask Ines to deliver "
                                            "the verdict with the failing check. " + facts, view("vale", self),
                                    f"{'Passed' if g['result'] == 'passed' else 'Not this time'}: {g['score']}. "
                                    "Ines, deliver it with the failing check.", 35)
        self.whisper("vale", "ines", vale_line, "decide", cc=["sam"])
        self.move("ines", "terminal", "run the Bruin checks at the terminal")
        self.on_call(bruin_call)
        for c in s.checks:
            self.emit("check.result", "ines", ("the planted trap shows here" if not c["passed"]
                                               else "this check passes on this data"), task=s.id,
                      text=f"Check {'passed' if c['passed'] else 'failed'}: {c['detail']}"[:200], data=c)
        failing = next((c["check"] for c in s.checks if not c["passed"]), None)
        record = {"session": self.id, "taskId": s.id, "score": g["score"], "verdict": ans["verdict"],
                  "trap": ans["trap"]}
        entry = ledger.append("grade.sealed", record, path=ledger_path())
        s.ledger = {"index": entry["seq"], "hash": entry["sha"][:12], "prev": entry["prev_sha"][:12]}
        self.emit("ledger.seal", "system", "seal the grade in the hash chain", task=s.id,
                  data={**s.ledger, "record": {k: record[k] for k in ("taskId", "score", "verdict", "trap")}})
        text, qs = self.feedback(g, failing)
        bench = None
        try:
            bench = bench_f.result(timeout=20)
        except Exception as e:
            self.engine.log_error(self, "benchmark", e)
        if bench:
            text = f"{text} {self.reality_line(bench)}"
        s.grade = g
        self.emit("verdict", "ines", "graded against the answer key, with the failing Bruin check as evidence",
                  task=s.id, text=f"{'Passed' if g['result'] == 'passed' else 'Failed'}: {g['score']}.",
                  data={"taskId": s.id, **{k: g[k] for k in ("result", "score", "parts", "correctVerdict",
                                                             "correctTrap")},
                        "text": text, "quotes": qs, "failingCheck": failing, "ledger": s.ledger,
                        **({"benchmark": bench} if bench else {})})
        opened = [{"seq": e["seq"], "agent": e["agent"], "to": e.get("to"), "text": (e.get("data") or {}).get("text", "")}
                  for e in self.log.of_kind("panel.whisper") if e.get("task") == s.id]
        self.emit("panel.transcript", "ines", "the verdict is in, so the panel's whispers are open", task=s.id,
                  data={"taskId": s.id, "whispers": opened})
        self.say("ines", text, "deliver the verdict out loud", task=s.id, data={"quotes": qs} if qs else None)
        self.bring_case()
        if s.id == "t1" and self.news:
            self.reveal_news()
        correct = grading.correct_for_mastery(ans, key)
        if not correct:
            self.wrong_guesses += 1
        rival_g = grading.grade({**s.rival, "evidence": []}, key, 0) if s.rival else {"score": 0}
        pick = s.pick or {}
        news = {}
        if s.id == "t1" and self.news:
            news = {"news": {**{k: self.news.get(k, "") for k in ("title", "url", "trace")},
                             "trap": self.news.get("trap"), "steered": bool(pick.get("nudged"))}}
        full = pick.get("pickReason") or pick.get("reason") or "picked by the rules"
        self.emit("task.end", "system", "the verdict is in", task=s.id,
                  data={"taskId": s.id, "score": g["score"], "beatRival": g["score"] > rival_g["score"],
                        "trap": key["trap"], "pickReason": f"{full}; it was a {TRAP_LABEL[key['trap']]} task "
                                                          f"at tier {s.tier}",
                        **({"bandit": pick["bandit"]} if pick.get("bandit") else {}), **news})
        self.move("vale", "vale_office", "the verdict is delivered; back to the office")
        self.move("sam", "whiteboard", "back to the whiteboard")
        self.move("riley", "learner_desk", "Riley comes over to see who won", to="learner")
        for upd in sources.learner_update(self.learner, key["trap"], correct, score=g["score"], tier=s.tier,
                                          session=self.id, task=s.task.bank_id):
            if upd.get("from") == upd.get("to") or upd.get("trap") not in TRAP_LABEL:
                continue
            lab_ = TRAP_LABEL[upd["trap"]]
            self.emit("mastery.update", "system", f"knowledge tracing after a{' correct' if correct else 'n incorrect'}"
                                                  f" answer on a {TRAP_LABEL[key['trap']]} task", task=s.id,
                      text=f"{lab_.capitalize()} mastery: {upd['from']} to {upd['to']}.",
                      data={k: upd[k] for k in ("trap", "from", "to", "correct", "attempts", "bruinRun")
                            if k in upd})
        s.phase = "done"
        self.next_task()

    def bring_case(self) -> None:
        """After the verdict: Telem brings a real case of this task's trap (or, on a clean task,
        of trusting a clean result). The search starts only now: its sponsor.call names the trap."""
        s, trap = self.slot, self.slot.task.key["trap"]
        found = sources.telem_case(self.sponsors, trap)
        s.case = found
        top = (found.get("results") or [{}])[0]
        clean = trap == "none"
        self.move("telem", "learner_desk", "the verdict is in, so Telem brings a real case of "
                  + ("trusting a clean result" if clean else "the same trap"), to="learner")
        self.emit("search", "telem", "this happens in real life: a real case of "
                  + ("trusting a clean result" if clean else f"a {TRAP_LABEL[trap]}"), task=s.id,
                  text=f"Telem found a real case: {top.get('title', 'a related case')}"[:200],
                  data={"phase": "case", "trap": trap, "query": found.get("query", ""),
                        "results": found.get("results", []), "trace": found.get("trace", ""),
                        "cached": bool(found.get("cached"))})
        fb = (f"This happens in real life: {top.get('title', 'a related case')}. "
              "The source and the trace are on the card.")
        line, _ = speaker.call("telem", "The verdict is in. In one or two sentences, tell the learner that this "
                                        "happens in real life: share the real case from your search results and "
                                        "say the source and trace are on the card.", view("telem", self), fb, 45)
        self.say("telem", line, "this happens in real life: a real case with its source", task=s.id)
        self.move("telem", "shelves", "back to the shelves")
        self.save()

    def reality_line(self, b: dict) -> str:
        """One sentence from Glasser's numbers, built in code (an agent could misstate them)."""
        key = self.slot.task.key
        line = f"Reality check: {_label(b)} is typically {sources.benchmark_range(b)} ({sources.benchmark_source(b)})."
        naive = key.get("naive")
        unit = str(b.get("unit") or "")
        if isinstance(naive, (int, float)) and key["trap"] != "none" and naive > 3 * float(b["high"]):
            money = unit.upper().startswith("USD") or unit.startswith("$")
            line += f" The quick answer's {sources._amount(float(naive), money)} should have looked wrong."
        return line

    def reveal_news(self) -> None:
        """After t1's verdict: the case of the day, and whether it steered the pick."""
        s, n = self.slot, self.news
        steered = bool((s.pick or {}).get("nudged"))
        title = n.get("title", "") or "a data error in the news"
        self.emit("monitor.hit", "telem", "Telem's monitor found today's case; held until the first verdict "
                                          "because it can steer the pick", task=s.id,
                  text=f"Case of the day: {title}"[:200],
                  data={**{k: n.get(k, "") for k in ("title", "url", "trace", "summary")},
                        "trap": n.get("trap"), "steered": steered})
        self.move("vale", "learner_desk", "explain what shaped the pick", to="learner")
        line = (f"I picked this task because Telem's monitor caught a story this morning: {title}. "
                "The source and the trace are on the card." if steered else
                f"Telem's monitor caught a story this morning: {title}. It didn't decide this pick; "
                "your learner profile did.")
        self.say("vale", line, "the news behind the pick, now that the verdict is in" if steered
                 else "the morning's news, which did not decide this pick", task=s.id)

    def rival_answer(self) -> None:
        s, key = self.slot, self.slot.task.key
        careless = key.get("careless") or {}
        verdict, trap = careless.get("verdict", "holds"), careless.get("trap", "none")
        note = careless.get("note", "")
        tables = dict(view("riley", self))["public tables"]
        got = None if speaker.canned() else sources.riley_model(self.sponsors, speaker.system_prompt("riley"),
                                  f"Claim: {s.public()['claim']}\nPublic tables:\n{tables}\n"
                                  f"Your quick analysis: {note}\nSay your answer and your number in one or two "
                                  "breezy sentences.")
        if got:
            text, model, provider = got["text"], got["model"], got["provider"]
        else:
            parts = view("riley", self) + [("your quick analysis", note)]
            text, fb = speaker.call("riley", "Give your quick answer to the claim: your number and your verdict.",
                                    parts, note, 40)
            model, provider = ("claude -p (careless prompt)" if not fb else "careless analysis"), "claude_fallback"
        s.rival = {"verdict": verdict, "trap": trap, "note": text}
        self.emit("rival.answer", "riley", "the intern took the first number that answered the question",
                  task=s.id, text=f"Riley answered: {verdict}.",
                  data={"verdict": verdict, "trap": trap, "note": text, "model": model, "provider": provider})

    def feedback(self, g: dict, failing: str | None) -> tuple[str, list[dict]]:
        s, key, ans = self.slot, self.slot.task.key, self.slot.answer
        sqls = [e["data"]["sql"] for e in self.log.of_kind("learner.query") if e.get("task") == s.id]
        frag = quotes.safe_fragment(ans.get("note", ""))
        right_v, right_t = g["parts"]["verdict"] == 1, g["parts"]["trap"] == 1
        opening = ("Right verdict, right trap." if right_v and right_t else
                   "Right verdict, wrong trap." if right_v else
                   "Right trap, wrong verdict." if right_t else "Not this time.")
        fb = opening
        if frag:
            fb += f" You wrote \"{frag}\"."
        if failing:
            fb += f" The failing check, {failing}, shows the {TRAP_LABEL[key['trap']]}."
        elif key["trap"] == "none":
            fb += " Every check passed: the data was clean and the claim was the thing to judge."
        if g["parts"]["hints"]:
            fb += " You lose a little for needing a hint."
        job = (f"Give the learner the verdict in two to four sentences. {opening} Score {g['score']}. "
               f"The correct answer: verdict {key['verdict']}, trap {key['trap']}. "
               f"Failing check: {failing or 'none'}. Hint deduction: {g['parts']['hints']}. "
               "Quote the learner's own words exactly, in double quotes, at most twice.")
        text, used_fb = speaker.call("ines", job, view("ines", self), fb, 80)
        cleaned, qs, dropped = quotes.check(text, ans.get("note", ""), sqls)
        if dropped:
            self.engine.note(self, f"dropped {len(dropped)} quote(s) not found word for word")
        if not cleaned:
            cleaned, qs, _ = quotes.check(fb, ans.get("note", ""), sqls)
        return cleaned, qs

    def next_task(self) -> None:
        self.save()
        if self.idx + 1 < len(self.slots):
            self.idx += 1
            self.pick_task()
            return
        total = round(sum(x.grade["score"] for x in self.slots if x.grade) / len(self.slots), 2)
        if self.mode == "rotation":
            done = [{"taskId": x.id, "title": x.public()["title"], "trap": x.task.key["trap"],
                     "score": x.grade["score"], "result": x.grade["result"]} for x in self.slots if x.grade]
            sources.teamily_post(self.id, done, self.mastery_now(), self.learner, self.on_call)
        refresh = speaker.POOL.submit(sources.learner_refresh, self.on_call)   # N3's Bruin learner tables
        try:   # wait a little so session.end stays last; a slow refresh reports when it is done
            refresh.result(timeout=20)
        except Exception:
            pass
        self.finished = True
        self.emit("session.end", "system", "judge mode is one task" if self.mode == "judge"
                  else "all three rotation tasks are graded", data={"tasks": len(self.slots), "totalScore": total})
        self.save()

    def retail_numbers(self) -> None:
        self.retail = sources.glasser_params(self.on_call)

    def read_news(self) -> None:
        """Telem's case of the day, before the first pick (it may nudge it). Its monitor.hit
        waits for t1's verdict: the headline names a trap."""
        f = speaker.POOL.submit(sources.case_of_day, self.sponsors)
        try:
            self.news = f.result(timeout=NEWS_WAIT_S)
        except Exception:
            self.news = None

    # -------------------------------------------------------------------------- appeal
    def do_appeal(self, aid: str) -> None:
        a = self.appeals[aid]
        s = self.slot_by_id(a["taskId"])
        g = s.grade
        hint_ts = [e["t"] for e in self.log.of_kind("agent.say")
                   if e.get("task") == s.id and (e.get("data") or {}).get("hintLevel")]
        qs = [e for e in self.log.of_kind("learner.query") if e.get("task") == s.id]
        first_hint = min(hint_ts) if hint_ts else None
        useful_before = [e for e in qs if e["data"].get("useful") and first_hint is not None and e["t"] < first_hint]
        facts = (f"Grade {g['score']} with parts {g['parts']}. Hints given: {s.hints}"
                 + (f", the first at {first_hint:.0f} s." if first_hint is not None else ".")
                 + f" Useful queries before the first hint: {len(useful_before)} of {len(qs)} queries.")
        parts = view("sam", self) + [("the appeal", a["reason"])]
        sam_fb = (f"The log shows {len(useful_before)} useful queries before my first hint."
                  if first_hint is not None else "The log shows no hint was given on this task.")
        line, _ = speaker.call("sam", "Tell the learner, in one or two sentences, what the log shows about the "
                                      "appeal. " + facts, parts, sam_fb, 40)
        posted = sources.band_post(self.room, "sam", line, ["ines", "vale"])
        self.emit("appeal.message", "sam", "Sam reports what the log shows", to="learner", task=s.id, text=line,
                  data={"appealId": aid, "text": line, **({"bandMessageId": str(posted["id"])}
                                                          if posted.get("id") and not posted["local"] else {})})
        refund = -g["parts"]["hints"]
        refundable = refund > 0 and len(useful_before) > 0
        if refundable:
            upheld, reason = False, (f"{len(useful_before)} useful quer{'y' if len(useful_before) == 1 else 'ies'} "
                                     f"ran before the first hint, so the hint deduction is refunded.")
        elif refund > 0:
            upheld, reason = True, ("no useful query ran before the first hint at "
                                    f"{first_hint:.0f} s, so the deduction stands.")
        else:
            upheld, reason = True, "the verdict and trap parts come from the sealed key; there is no hint deduction to refund."
        worded, _ = speaker.call("ines", f"Rule on the appeal in one or two sentences. The ruling is decided: "
                                         f"{'the grade stands' if upheld else 'the hint deduction is refunded'}, "
                                         f"because {reason} State it plainly.",
                                 view("ines", self) + [("the appeal", a["reason"]), ("the log facts", facts)],
                                 reason[0].upper() + reason[1:], 45)
        old = g["score"]
        new = old if upheld else round(min(1.0, old + refund), 2)
        a["ruled"] = True
        self.emit("appeal.ruling", "ines", reason, task=s.id,
                  text=f"Appeal ruled: {'the grade stands' if upheld else f'the grade changes from {old} to {new}'}.",
                  data={"appealId": aid, "upheld": upheld, "oldScore": old, "newScore": new, "reason": worded})
        if not upheld:
            g["score"] = new
            g["result"] = "passed" if new >= grading.PASS else "failed"
            entry = ledger.append("grade.changed", {"session": self.id, "taskId": s.id, "score": new,
                                                    "oldScore": old, "reason": reason}, path=ledger_path())
            s.ledger = {"index": entry["seq"], "hash": entry["sha"][:12], "prev": entry["prev_sha"][:12]}
            self.emit("ledger.seal", "system", f"the appeal changed the grade: {reason}", task=s.id,
                      data={**s.ledger, "record": {"taskId": s.id, "score": new, "verdict": s.answer["verdict"],
                                                   "trap": s.answer["trap"]}})
        self.save()

    def do_appeal_reply(self, aid: str, text: str) -> None:
        a = self.appeals[aid]
        s = self.slot_by_id(a["taskId"])
        parts = view("ines", self) + [("the appeal", a["reason"]), ("the learner's message", text)]
        line, _ = speaker.call("ines", "Answer the learner's message about their appeal in one or two sentences.",
                               parts, "Noted. The ruling follows the log.", 40)
        posted = sources.band_post(self.room, "ines", line, ["vale", "sam"])
        self.emit("appeal.message", "ines", "Ines answers the learner's appeal message", to="learner", task=s.id,
                  text=line, data={"appealId": aid, "text": line,
                                   **({"bandMessageId": str(posted["id"])} if posted.get("id") and not posted["local"]
                                      else {})})


class Engine:
    """All sessions of this server. Thread-safe."""

    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------------- plumbing
    def log_error(self, s: Session, where: str, e: Exception) -> None:
        import sys
        print(f"[engine] {s.id} {where} failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(limit=4, file=sys.stderr)

    def note(self, s: Session, msg: str) -> None:
        import sys
        print(f"[engine] {s.id} {msg}", file=sys.stderr, flush=True)

    def has(self, sid: str) -> bool:
        with self._lock:
            if sid in self.sessions:
                return True
        try:
            return session_path(sid).is_file()
        except ValueError:
            return False

    def get(self, sid: str) -> Session:
        with self._lock:
            if sid in self.sessions:
                return self.sessions[sid]
        s = self._load(sid)
        if s is None:
            raise EngineError(404, f"no session {sid}")
        return s

    def _load(self, sid: str) -> Session | None:
        """A session from disk: its log, and its private state when there is one."""
        path = session_path(sid)
        if not path.is_file():
            return None
        events = read_events(path)
        if not events:
            return None
        start = events[0].get("data") or {}
        log = SessionLog(sid, path)
        s = Session(self, sid, start.get("mode", "rotation"), start.get("learner", "guest"), log)
        state_path = path.with_suffix(".state.json")
        state = {}
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text())
            except ValueError:
                state = {}
        s.idx, s.qn, s.wrong_guesses = state.get("idx", 0), state.get("qn", 0), state.get("wrong", 0)
        s.appeals = state.get("appeals", {})
        s.where = {**HOME, **(state.get("where") or {})}
        s.news = state.get("news")
        for slot, st in zip(s.slots, state.get("slots", [])):
            if st.get("bankId"):
                slot.task = sources.bank_load(st["bankId"])
            slot.pick, slot.phase, slot.hints = st.get("pick"), st.get("phase", "waiting"), st.get("hints", 0)
            slot.seconds, slot.opened_t = st.get("seconds", DEFAULT_SECONDS), st.get("openedT")
            slot.answer, slot.grade, slot.checks = st.get("answer"), st.get("grade"), st.get("checks") or []
            slot.search, slot.seen_cols = st.get("search"), set(st.get("seenCols") or [])
            slot.case = st.get("case")
            slot.ledger, slot.rival = st.get("ledger"), st.get("rival")
        s.finished = any(e["k"] == "session.end" for e in events)
        with self._lock:
            if sid in self.sessions:
                return self.sessions[sid]
            self.sessions[sid] = s
        if not s.finished and s.slot and s.slot.task:
            s.room = sources.band_room(s.on_call)
            if s.slot.phase == "grading":
                s.q.put(("grade",))
            elif s.slot.phase == "brief":
                s.q.put(("brief",))
            s.start_worker()
        return s

    # ------------------------------------------------------------------------ routes
    def start_session(self, mode: str = "rotation", learner: str | None = None) -> dict:
        sid = "s" + time.strftime("%H%M%S") + "-" + secrets.token_hex(3)
        learner = learner or "guest"
        log = SessionLog(sid)
        s = Session(self, sid, mode, learner, log)
        with self._lock:
            self.sessions[sid] = s
        why = ("a judge sat down at the desk and chose judge mode" if mode == "judge"
               else "a learner started a rotation: three tasks with rising tiers")
        s.emit("session.start", "system", why, data={"mode": mode, "learner": learner, "tasks": len(s.slots),
                                                     "startedAt": log.started})
        s.room = sources.band_room(s.on_call)
        s.read_news()
        with s.lock:
            s.pick_task()
        speaker.POOL.submit(s.retail_numbers)
        s.start_worker()
        tasks = [{"id": x.id, "title": x.public()["title"] if x.task else f"Task {x.id[1:]}"} for x in s.slots]
        return {"sessionId": sid, "tasks": tasks, "task": s.slot.public()}

    def current_task(self, sid: str) -> dict | None:
        s = self.get(sid)
        if s.finished:
            return None
        return s.slot.public() if s.slot else None

    def _folder(self, sid: str, task: str | None) -> str:
        s = self.get(sid)
        slot = s.slot_by_id(task)
        if slot is None or slot.task is None:
            raise EngineError(404, "no such task in this session")
        return slot.task.dir

    def tables(self, sid: str, task: str | None = None) -> list[dict]:
        return sources.ws_tables(self._folder(sid, task))

    def rows(self, sid: str, table: str, offset: int, limit: int, task: str | None = None) -> dict:
        return sources.ws_rows(self._folder(sid, task), table, offset, limit)

    def profile(self, sid: str, table: str, task: str | None = None) -> dict:
        return sources.ws_profile(self._folder(sid, task), table)

    def events_since(self, sid: str, since: int) -> dict:
        s = self.get(sid)
        out = [e for e in summary.seal(s.log.since(0)) if e["seq"] > since]
        return {"events": out, "next": out[-1]["seq"] if out else min(since, s.log.last_seq)}

    def sql(self, sid: str, sql: str) -> dict:
        s = self.get(sid)
        if s.finished:
            raise EngineError(409, "this session is over")
        with s.lock:
            slot = s.slot
            res = sources.ws_query(slot.task.dir, sql)
            s.qn += 1
            ok = "error" not in res
            rel = set(slot.task.key.get("columns") or [])
            useful = meter.is_useful(sql, ok, rel, slot.seen_cols)
            if ok:
                slot.seen_cols |= meter.columns_in(sql, rel)
            data = {"queryId": f"q{s.qn}", "sql": sql, "ok": ok, "rowCount": len(res.get("rows") or []),
                    "ms": res.get("ms", 0), "useful": useful}
            if not ok:
                data["error"] = res["error"]
            # `useful` names columns that matter, so the why stays generic and the server holds
            # `data.useful` back until the task's verdict (summary.seal).
            why = "the learner ran a query in the SQL box" if ok else "the query failed"
            s.emit("learner.query", "learner", why, task=slot.id, text=sql[:300], data=data)
            if slot.phase == "analysis":   # after every query, so the timing says nothing either
                s.emit_meter(s.meter_now(), cause="query" if ok else "failed")
            s.save()
        return {"error": res["error"]} if not ok else {k: res[k] for k in ("columns", "rows", "ms", "truncated")}

    def submit_answer(self, s: Session, answer: dict, timed_out: bool = False) -> None:
        slot = s.slot
        if s.finished or answer["taskId"] != slot.id or slot.phase not in ("brief", "analysis"):
            raise EngineError(409, "that task is not open for an answer")
        slot.answer = answer
        slot.phase = "grading"
        if answer.get("evidence"):
            s.emit("learner.evidence", "learner", "the learner cited this evidence with the answer", task=slot.id,
                   data={"action": "add", "items": answer["evidence"]})
        s.emit("learner.answer", "learner", "the clock ran out, so the answer is can't tell" if timed_out
               else "the learner submitted an answer", task=slot.id,
               text=f"The learner answered: {answer['verdict']}, {TRAP_LABEL[answer['trap']]}.",
               data={k: answer[k] for k in ("verdict", "trap", "note", "evidence")})
        s.save()
        s.q.put(("grade",))

    def on_answer(self, sid: str, answer: dict) -> dict:
        s = self.get(sid)
        with s.lock:
            self.submit_answer(s, answer)
        return {"accepted": True}

    def on_appeal(self, sid: str, body: dict) -> dict:
        s = self.get(sid)
        with s.lock:
            slot = s.slot_by_id(body["taskId"])
            if slot is None or not slot.grade:
                raise EngineError(409, "only a graded task can be appealed")
            if any(a["taskId"] == slot.id for a in s.appeals.values()):
                raise EngineError(409, "this task was already appealed")
            aid = f"a{len(s.appeals) + 1}"
            s.appeals[aid] = {"taskId": slot.id, "reason": body["reason"], "ruled": False}
            room = sources.band_relay(s.room, f"Appeal on {slot.id} from the learner: {body['reason']}")
            s.emit("appeal.open", "learner", "the learner thinks the grade is unfair", task=slot.id,
                   text="The learner appealed.", data={"appealId": aid, "taskId": slot.id, "reason": body["reason"],
                                                       "room": "local" if room["local"] else "band"})
            s.save()
        s.q.put(("appeal", aid))
        if s.thread is None or not s.thread.is_alive():
            s.start_worker()
        return {"appealId": aid}

    def on_appeal_message(self, sid: str, aid: str, body: dict) -> dict:
        s = self.get(sid)
        with s.lock:
            if aid not in s.appeals:
                raise EngineError(404, f"no appeal {aid}")
            a = s.appeals[aid]
            sources.band_relay(s.room, f"Learner on appeal {aid}: {body['text']}")
            s.emit("appeal.message", "learner", "the learner added to the appeal", to="ines", task=a["taskId"],
                   text=body["text"], data={"appealId": aid, "text": body["text"]})
        s.q.put(("appeal_reply", aid, body["text"]))
        if s.thread is None or not s.thread.is_alive():
            s.start_worker()
        return {"ok": True}

    def mastery(self, sid: str) -> dict:
        return sources.mastery(self.get(sid).learner)

    def ask(self, sid: str, agent: str, text: str) -> dict:
        s = self.get(sid)
        with s.lock:
            slot = s.slot
            graded = bool(slot and slot.grade)
            s.emit("ask", "learner", "the learner asked an agent", to=agent, task=slot.id if slot else None, text=text)
            parts = view(agent, s)
            if agent == "ines" and not graded:   # the key stays sealed until the verdict
                parts = [p for p in parts if p[0] != "answer key"]
        extra, found = {}, None
        if agent == "telem":   # a live look-up with the question only; Telem never sees the data
            found = sources.telem_answer(s.sponsors, text)
        if found and found.get("results"):
            reply = telem_reply(found)
            used = ["Telem's web search"]
            extra = {"links": [{"title": r.get("title", ""), "url": r.get("url", "")} for r in found["results"]],
                     "trace": found.get("trace", "")}
        else:
            reply, _ = speaker.call(agent, "Answer the learner's question from your records only, in one to three "
                                           "sentences. If your records do not say, say so.",
                                    parts + [("the learner's question", text)],
                                    "I can't answer that from what I can see.", 60)
            used = sources_used(agent, parts)
        if not graded and (leaks_beyond(reply, text) if agent == "telem" else leaks_any(reply)):
            reply, extra = "I can't say that before the verdict.", {}
        with s.lock:
            s.emit("ask.answer", agent, f"answered only from what {agent} can see", to="learner",
                   task=slot.id if slot else None, text=reply, data={"sources": used, **extra})
        return {"agent": agent, "text": reply, "sources": used, **extra}

    def sponsor_totals(self, sid: str) -> dict:
        return summary.sponsor_totals(self.get(sid).log.events)

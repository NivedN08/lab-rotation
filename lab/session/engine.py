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
    search: dict | None = None
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
        self.thread: threading.Thread | None = None

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
            v = sources.tts(agent, text, self.on_call)
            data = {"file": v["file"], "lineOf": line_of, "seconds": v["seconds"], "provider": v["provider"]}
            if v.get("cost") is not None and v["provider"] == "runware":
                data["cost"] = v["cost"]
            self.emit("voice.line", agent, "speak the line in the agent's own voice"
                      if v["provider"] == "runware" else "no voice file, so the browser speaks the line",
                      task=task, data=data)
        except Exception as e:
            self.engine.log_error(self, "voice", e)

    def move(self, agent: str, frm: str, place: str, why: str, to: str | None = None) -> None:
        self.emit("agent.move", agent, why, to=to, task=self.slot.id if self.slot else None,
                  data={"from": frm, "place": place})

    def whisper(self, agent: str, to: str, text: str, why: str, cc: list[str] = ()) -> dict:
        posted = sources.band_post(self.room, agent, text, [to, *cc])
        data = {"text": text, "cc": list(cc), "local": posted["local"]}
        if posted.get("id") and not posted["local"]:
            data["bandMessageId"] = str(posted["id"])
        return self.emit("panel.whisper", agent, why, to=to, task=self.slot.id, data=data)

    # ----------------------------------------------------------------- private state
    def save(self) -> None:
        state = {"mode": self.mode, "learner": self.learner, "idx": self.idx, "qn": self.qn,
                 "wrong": self.wrong_guesses, "finished": self.finished, "appeals": self.appeals,
                 "slots": [{"id": s.id, "tier": s.tier, "bankId": s.task.bank_id if s.task else None,
                            "pick": s.pick, "phase": s.phase, "hints": s.hints, "seconds": s.seconds,
                            "openedT": s.opened_t, "answer": s.answer, "grade": s.grade,
                            "checks": s.checks, "search": s.search, "seenCols": sorted(s.seen_cols),
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
        pick = sources.pick_next(self.learner, seen_traps, s.tier, self.rng)
        bank_id = sources.bank_pick(pick["skill"], s.tier, seen_ids)
        s.task = sources.bank_load(bank_id)
        s.pick = pick
        s.seconds = JUDGE_SECONDS if self.mode == "judge" else int(s.task.public.get("seconds") or DEFAULT_SECONDS)
        s.phase = "brief"
        first = s.id == "t1"
        reason = ("new learner with no history: start at tier 1" if first and not any(
            r["attempts"] for r in self.mastery_now()["traps"]) else
                  f"tier {s.tier} next; the learner model favours the skills you have shown least")
        p = s.public()
        self.emit("task.picked", "vale", reason, task=s.id, text=f"Vale picked task {s.id[1:]}.",
                  data={"taskId": s.id, "title": p["title"], "tier": s.tier, "claim": p["claim"],
                        "reason": reason, "fallback": bool(pick.get("fallback") or s.task.stub)})
        self.save()
        self.q.put(("brief",))

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

    def emit_meter(self, m: dict, useful_now: bool = False) -> None:
        s = self.slot
        s.last_meter, s.last_meter_t = m, self.log.now()
        self.emit("meter.update", "system", meter.why(m, useful_now), task=s.id, data=m)

    def do_brief(self) -> None:
        s = self.slot
        p, key = s.public(), s.task.key
        self.move("vale", "vale_office", "learner_desk", "brief the learner in person", to="learner")
        brief_fallback = f"{p['brief']} The claim: {p['claim']} Check it before it goes any further."
        vale_job = ("Brief the learner on this task in two or three short sentences: the claim, who wants it, "
                    "and why it must be checked. Do not hint at what might be wrong.")
        vale_f = speaker.submit("vale", vale_job, view("vale", self), brief_fallback, 55)
        case_trap = key["trap"] if (s.tier == 1 and key["trap"] != "none") else self.rng.choice(
            [t for t in summary.TRAPS if t != "none"])
        case_query = fallback.CASES[case_trap]["query"]
        search_f = speaker.POOL.submit(sources.telem_search, case_query, case_trap, self.on_call)
        line, used_fb = vale_f.result()
        if leaks(line, key["trap"]):
            line = brief_fallback
        self.say("vale", line, "deliver the brief and the claim", task=s.id)
        self.move("telem", "door", "shelves", "look for real cases of claims like this going wrong")
        found = search_f.result()
        s.search = found
        top = (found.get("results") or [{}])[0]
        self.emit("search", "telem", "real cases help the learner know what to look for", task=s.id,
                  text=f"Telem found a real case: {top.get('title', 'a related case')}"[:200],
                  data={"query": found.get("query", case_query), "results": found.get("results", []),
                        "trace": found.get("trace", ""), "cached": bool(found.get("cached"))})
        self.move("telem", "shelves", "learner_desk", "bring the case to the learner", to="learner")
        telem_fb = f"A real case for you: {top.get('title', 'a related case')}. The source is on the card."
        tline, _ = speaker.call("telem", "Share the one real case from your search results with the learner, "
                                         "in one or two sentences.", view("telem", self), telem_fb, 45)
        self.say("telem", tline, "share one real case with its source", task=s.id)
        self.move("vale", "learner_desk", "vale_office", "brief done; let the learner work")
        self.move("telem", "learner_desk", "shelves", "back to the shelves")
        self.move("riley", "door", "riley_desk", "the intern races the learner on the same task")
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
        self.whisper("sam", "vale", sam_line, "Sam checks with the panel before giving a hint", cc=["ines"])
        self.whisper("ines", "sam", f"Point them here, as a question: {hint}",
                     "Ines knows the key, so she says where to point without naming the trap")
        self.whisper("vale", "sam", "Go ahead, keep it a question.", "Vale approves the hint level")
        self.move("sam", "whiteboard", "learner_desk", f"the struggle meter reached {m['value']}", to="learner")
        line, _ = speaker.call("sam", "Ask the learner one short question that points where Ines suggested. "
                                      "Do not give the answer.", view("sam", self), hint, 30)
        if leaks(line, key["trap"]):
            line = hint
        s.hints, s.last_hint_t = level, self.log.now()
        self.say("sam", line, f"struggle meter {m['value']}; hint level {level}, as a question", task=s.id,
                 data={"hintLevel": level})
        self.move("sam", "learner_desk", "whiteboard", "back to the whiteboard to watch")
        self.save()

    # ------------------------------------------------------------------------- grading
    def do_grade(self) -> None:
        s = self.slot
        key, ans = s.task.key, s.answer
        self.rival_answer()
        for agent, frm in (("vale", "vale_office"), ("ines", "terminal"), ("sam", "whiteboard")):
            self.move(agent, frm, "panel_table", "the panel confers before the verdict")
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
        self.whisper("ines", "vale", ines_f.result()[0], "Ines shares the basis for the grade with the panel",
                     cc=["sam"])
        self.whisper("sam", "ines", sam_f.result()[0], "Sam reports the coaching history", cc=["vale"])
        vale_line, _ = speaker.call("vale", "Decide with the panel in one or two sentences and ask Ines to deliver "
                                            "the verdict with the failing check. " + facts, view("vale", self),
                                    f"{'Passed' if g['result'] == 'passed' else 'Not this time'}: {g['score']}. "
                                    "Ines, deliver it with the failing check.", 35)
        self.whisper("vale", "ines", vale_line, "Vale decides the verdict", cc=["sam"])
        self.move("ines", "panel_table", "terminal", "run the Bruin checks at the terminal")
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
        s.grade = g
        self.emit("verdict", "ines", "graded against the answer key, with the failing Bruin check as evidence",
                  task=s.id, text=f"{'Passed' if g['result'] == 'passed' else 'Failed'}: {g['score']}.",
                  data={"taskId": s.id, **{k: g[k] for k in ("result", "score", "parts", "correctVerdict",
                                                             "correctTrap")},
                        "text": text, "quotes": qs, "failingCheck": failing, "ledger": s.ledger})
        self.say("ines", text, "deliver the verdict out loud", task=s.id, data={"quotes": qs} if qs else None)
        correct = grading.correct_for_mastery(ans, key)
        if not correct:
            self.wrong_guesses += 1
        rival_g = grading.grade({**s.rival, "evidence": []}, key, 0) if s.rival else {"score": 0}
        pick = s.pick or {}
        self.emit("task.end", "system", "the verdict is in", task=s.id,
                  data={"taskId": s.id, "score": g["score"], "beatRival": g["score"] > rival_g["score"],
                        "trap": key["trap"], "pickReason": f"{pick.get('reason', 'picked by the rules')}; "
                                                          f"it was a {TRAP_LABEL[key['trap']]} task at tier {s.tier}",
                        **({"bandit": pick["bandit"]} if pick.get("bandit") else {})})
        upd = sources.learner_update(self.learner, key["trap"], correct)
        if upd.get("from") != upd.get("to"):
            self.emit("mastery.update", "system", f"knowledge tracing after a{' correct' if correct else 'n incorrect'}"
                                                  f" answer on a {TRAP_LABEL[key['trap']]} task", task=s.id,
                      text=f"{TRAP_LABEL[key['trap']].capitalize()} mastery: {upd['from']} to {upd['to']}.",
                      data={k: upd[k] for k in ("trap", "from", "to", "correct", "attempts", "bruinRun")
                            if k in upd})
        if not upd.get("fallback"):
            self.on_call({"sponsor": "bruin", "label": "updated the learner model (bkt_mastery)", "count": 1,
                          "op": "run", "by": "system", "ms": int(upd.get("ms") or 0), "fallback": False})
        s.phase = "done"
        self.next_task()

    def rival_answer(self) -> None:
        s, key = self.slot, self.slot.task.key
        careless = key.get("careless") or {}
        verdict, trap = careless.get("verdict", "holds"), careless.get("trap", "none")
        note = careless.get("note", "")
        got = sources.riley_model(f"Claim: {s.public()['claim']}\nYour quick analysis: {note}\n"
                                  "Say your answer in one or two breezy sentences.", self.on_call)
        if got:
            text, model, provider = got["text"], got["model"], "runware"
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
        self.finished = True
        self.emit("session.end", "system", "judge mode is one task" if self.mode == "judge"
                  else "all three rotation tasks are graded", data={"tasks": len(self.slots), "totalScore": total})
        self.save()

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
        for slot, st in zip(s.slots, state.get("slots", [])):
            if st.get("bankId"):
                slot.task = sources.bank_load(st["bankId"])
            slot.pick, slot.phase, slot.hints = st.get("pick"), st.get("phase", "waiting"), st.get("hints", 0)
            slot.seconds, slot.opened_t = st.get("seconds", DEFAULT_SECONDS), st.get("openedT")
            slot.answer, slot.grade, slot.checks = st.get("answer"), st.get("grade"), st.get("checks") or []
            slot.search, slot.seen_cols = st.get("search"), set(st.get("seenCols") or [])
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
        with s.lock:
            s.pick_task()
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
        out = s.log.since(since)
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
            why = ("the query touched a column that matters for the first time" if useful else
                   "the query failed" if not ok else "the query touched no new column that matters")
            s.emit("learner.query", "learner", why, task=slot.id, text=sql[:300], data=data)
            if slot.phase == "analysis" and (useful or not ok or s.meter_now()["hintLevel"] != (
                    slot.last_meter or {}).get("hintLevel")):
                s.emit_meter(s.meter_now(), useful_now=useful)
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
        reply, _ = speaker.call(agent, "Answer the learner's question from your records only, in one to three "
                                       "sentences. If your records do not say, say so.",
                                parts + [("the learner's question", text)],
                                "I can't answer that from what I can see.", 60)
        trap = slot.task.key["trap"] if slot and slot.task else "none"
        if not graded and leaks(reply, trap):
            reply = "I can't say that before the verdict."
        used = sources_used(agent, parts)
        with s.lock:
            s.emit("ask.answer", agent, f"answered only from what {agent} can see", to="learner",
                   task=slot.id if slot else None, text=reply, data={"sources": used})
        return {"agent": agent, "text": reply, "sources": used}

    def sponsor_totals(self, sid: str) -> dict:
        return summary.sponsor_totals(self.get(sid).log.events)

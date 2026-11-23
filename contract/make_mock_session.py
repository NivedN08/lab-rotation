"""Write contract/mock_task/{task,tables}.json and contract/mock_session.jsonl.

Run from the repo root: python3 contract/make_mock_session.py contract
The CSVs in contract/mock_task/ are fixed; this script only writes the JSON files."""
import json, sys
from pathlib import Path

root = Path(sys.argv[1])
T = "t1"
claim = "Loyalty members spend more than twice as much per visit as other customers."
dictionary = ("# Data dictionary\n\n- **visits.spend**: basket total in US dollars, tax included.\n"
              "- **customers.loyalty_member**: 1 if the customer is in the loyalty program.\n"
              "- **stores.pos_version**: point-of-sale software that exported the visit.\n")
task = {"id": T, "title": "Loyalty spend check", "seconds": 240, "tier": 1, "claim": claim,
        "brief": "Marketing wants this on a board slide on Friday: members spend 2.4x per visit. Check it first.",
        "dictionary": dictionary}
tables = [
    {"name": "visits", "about": "One row per store visit", "rowCount": 300, "key": "visit_id", "columns": [
        {"name": "visit_id", "type": "text", "about": "One store visit"},
        {"name": "customer_id", "type": "text", "about": "Who visited (customers.customer_id)"},
        {"name": "store_id", "type": "text", "about": "Where (stores.store_id)"},
        {"name": "visit_date", "type": "date", "about": "Day of the visit"},
        {"name": "items", "type": "int", "about": "Items in the basket"},
        {"name": "spend", "type": "real", "about": "Basket total in dollars"}]},
    {"name": "customers", "about": "One row per customer", "rowCount": 60, "key": "customer_id", "columns": [
        {"name": "customer_id", "type": "text", "about": "Customer"},
        {"name": "loyalty_member", "type": "int", "about": "1 = loyalty member, 0 = not"},
        {"name": "joined", "type": "date", "about": "First purchase"},
        {"name": "home_store", "type": "text", "about": "Store they visit most"}]},
    {"name": "stores", "about": "One row per store", "rowCount": 12, "key": "store_id", "columns": [
        {"name": "store_id", "type": "text", "about": "Store"},
        {"name": "region", "type": "text", "about": "Sales region"},
        {"name": "pos_version", "type": "text", "about": "Point-of-sale software version"},
        {"name": "opened", "type": "int", "about": "Year the store opened"}]},
]
(root / "mock_task" / "task.json").write_text(json.dumps(task, indent=2) + "\n")
(root / "mock_task" / "tables.json").write_text(json.dumps(tables, indent=2) + "\n")

events, seq = [], 0
def ev(t, k, agent, why, **kw):
    global seq
    seq += 1
    e = {"seq": seq, "t": round(t, 3), "k": k, "agent": agent, "why": why}
    e.update({key: v for key, v in kw.items() if v is not None})
    events.append(e)
    return seq
def call(t, by, sponsor, op, label, ms, why, **extra):
    ev(t, "sponsor.call", "system", why, data={"sponsor": sponsor, "label": label, "count": 1, "op": op,
                                               "by": by, "ms": ms, "fallback": False, **extra})
def move(t, agent, frm, place, why, to=None):
    ev(t, "agent.move", agent, why, to=to, task=T, data={"from": frm, "place": place})
def say(t, agent, to, text, why, **data):
    n = ev(t, "agent.say", agent, why, to=to, text=text, task=T, data=data or None)
    f = f"mock-{n}.mp3"
    ev(t + 0.4, "voice.line", agent, "speak the line in the agent's own voice", task=T,
       data={"file": f, "lineOf": n, "seconds": round(len(text) / 14, 1), "cost": 0.0012, "provider": "runware"})
    call(t + 0.4, agent, "runware", "tts", f"voice line for {agent}", 820, "every spoken line is a Runware voice",
         cost=0.0012)
    return n
def query(t, qid, sql, rows, ms, useful, why, ok=True, error=None):
    d = {"queryId": qid, "sql": sql, "ok": ok, "rowCount": rows, "ms": ms, "useful": useful}
    if error:
        d["error"] = error
    ev(t, "learner.query", "learner", why, task=T, text=sql, data=d)
def meter(t, value, idle, dead, wrong, level, why):
    ev(t, "meter.update", "system", why, task=T,
       data={"value": value, "idleSeconds": idle, "deadEnds": dead, "wrongGuesses": wrong, "hintLevel": level})
whispers = []  # (seq, agent, to, text) for the panel.transcript after the verdict
def whisper(t, frm, to, text, why):
    # Before the verdict a whisper goes out sealed: no text. panel.transcript carries it later.
    n = ev(t, "panel.whisper", frm, why, to=to[0], task=T,
           data={"sealed": True, "cc": to[1:], "bandMessageId": f"band-mock-{seq + 1}", "local": False})
    whispers.append({"seq": n, "agent": frm, "to": to[0], "text": text})
    call(t + 0.2, frm, "band", "send_message", f"{frm} posted in the panel room", 140,
         "the panel talks in its BAND room")

ev(0, "session.start", "system", "a judge sat down at the desk and chose judge mode",
   data={"mode": "judge", "learner": "guest", "tasks": 1})
call(0.5, "system", "bruin", "run", "loaded the task tables with ingestr", 1900, "every task's tables go through Bruin")
call(0.6, "system", "glasser", "run", "looked up a typical basket size", 640, "real retail numbers come from Glasser",
     cost=0.002)
call(0.7, "system", "glasser", "run", "looked up store counts for the chain", 710, "real retail numbers come from Glasser",
     cost=0.002)
ev(1, "task.picked", "vale", "new learner with no history: start with the most common kind of trap, at tier 1",
   task=T, text="Vale picked the first task.",
   data={"taskId": T, "title": task["title"], "brief": task["brief"], "seconds": task["seconds"],
         "dictionary": task["dictionary"], "tier": 1, "claim": claim, "fallback": False,
         "reason": "new learner with no history: start with the most common kind of trap, at tier 1"})
move(1.5, "vale", "vale_office", "learner_desk", "brief the learner in person", to="learner")
say(5, "vale", "learner", "Marketing says loyalty members spend 2.4 times as much per visit. It goes to the board on Friday. Check it before it does.",
    "deliver the brief and the claim")
move(6, "telem", "door", "shelves", "look for real cases of this kind of claim going wrong")
call(7, "telem", "telem", "search", "searched for real cases", 1430, "the librarian finds real cases with Telem AI",
     trace="https://app.telem.ai/traces/mock-1")
ev(8.5, "search", "telem", "real cases help the learner know what to look for", task=T,
   text="Telem found a real case of a unit mix-up in sales data.",
   data={"query": "retail sales data reported in cents instead of dollars restated", "cached": False,
         "trace": "https://app.telem.ai/traces/mock-1",
         "results": [{"title": "Mock case: a chain restated regional sales after an export unit bug",
                      "url": "https://example.com/mock-case-units", "snippet": "One region's export switched to minor units..."}]})
move(9, "telem", "shelves", "learner_desk", "bring the case to the learner", to="learner")
say(12, "telem", "learner", "A real case for you: a chain once restated a region's sales because its export used cents. Source and trace are on the card.",
    "share one real case with its source")
move(13, "vale", "learner_desk", "vale_office", "brief done; let the learner work")
move(13, "telem", "learner_desk", "shelves", "back to the shelves")
move(14, "riley", "door", "riley_desk", "the intern races the learner on the same task")
query(30, "q1", "select * from visits limit 20", 20, 4, False, "first look at the visits table")
query(55, "q2", "select loyalty_member, avg(spend) from visits join customers using (customer_id) group by 1", 2, 6, True,
      "compare spend per visit by loyalty status")
meter(56, 0.1, 1, 0, 0, 0, "a useful query just ran")
query(80, "q3", "select loyalty_member, median(spend) from visits group by 1", 0, 2, False, "try a median instead",
      ok=False, error='Binder Error: Referenced column "loyalty_member" not found in FROM clause')
query(98, "q4", "select loyalty_member, avg(spend) as avg_spend from visits join customers using (customer_id) group by 1 order by 1", 2, 5, False,
      "the same comparison again, touching no new column: a dead end")
meter(130, 0.62, 32, 2, 0, 1, "two dead ends and 30 s without a useful query")
whisper(131, "sam", ["vale"], "The learner has repeated the member comparison twice and not looked at units or regions. I'll ask about units.",
        "Sam checks with the lab head before giving a hint")
whisper(133, "vale", ["sam"], "Go ahead, keep it a question.", "Vale approves the hint level")
move(134, "sam", "whiteboard", "learner_desk", "the struggle meter crossed 0.6", to="learner")
say(137, "sam", "learner", "Is every row of spend in the same unit? What does spend look like store by store?",
    "struggle meter 0.62; first hint, as a question", hintLevel=1)
query(150, "q5", "select region, min(spend), max(spend) from visits join stores using (store_id) group by 1 order by 1", 4, 7, True,
      "check spend ranges by region")
meter(151, 0.18, 0, 2, 0, 0, "a useful query just ran")
move(152, "sam", "learner_desk", "whiteboard", "the learner is moving again")
q6 = ("select loyalty_member, avg(case when region = 'West' then spend / 100 else spend end) from visits "
      "join customers using (customer_id) join stores using (store_id) group by 1 order by 1")
query(175, "q6", q6, 2, 9, True, "recompute with West converted from cents")
ev_q5 = {"kind": "column", "source": "query", "sql": "select region, min(spend), max(spend) from visits join stores using (store_id) group by 1 order by 1",
         "column": "max(spend)", "label": "max spend per region (q5)"}
ev_cell = {"kind": "cell", "source": "query", "sql": ev_q5["sql"], "row": 4, "column": "max(spend)", "value": 5600.0,
           "label": "West's max spend: 5600"}
ev_col = {"kind": "column", "source": "visits", "column": "spend", "label": "visits.spend"}
ev_q6 = {"kind": "column", "source": "query", "sql": q6, "column": "avg(CASE  WHEN ((region = 'West')) THEN ((spend / 100)) ELSE spend END)",
         "label": "average spend with West fixed (q6)"}
ev(199.9, "learner.evidence", "learner", "cite the region ranges, the spend column and the fixed comparison", task=T,
   data={"action": "add", "items": [ev_cell, ev_col, ev_q6]})
note = ("West spend is in cents: its max is 5600 while other regions top out near 74. After dividing West by 100, "
        "members average 37.05 and others 35.00, so not 2.4x.")
ev(200, "learner.answer", "learner", "the learner submitted an answer", task=T, text="The learner answered: fails, unit mix-up.",
   data={"verdict": "fails", "trap": "unit_mismatch", "note": note, "evidence": [ev_cell, ev_col, ev_q6]})
call(201, "riley", "runware", "chat", "Riley's analysis on an open model", 2300, "the intern runs on an open model served by Runware",
     cost=0.0004)
ev(203, "rival.answer", "riley", "the intern took the overall average and stopped there", task=T,
   text="Riley answered: holds.",
   data={"verdict": "holds", "trap": "none", "note": "Members average 1067 vs 441 for others. That's 2.4x. Claim holds.",
         "model": "open model via Runware", "provider": "runware"})
for a, frm in [("vale", "vale_office"), ("ines", "terminal"), ("sam", "whiteboard")]:
    move(204, a, frm, "panel_table", "the panel confers before the verdict")
whisper(206, "ines", ["vale", "sam"], "The key says unit_mismatch, verdict fails. The learner got both and cited the West max and the fixed means.",
        "Ines shares the basis for the grade with the panel")
whisper(208, "sam", ["ines", "vale"], "They needed one hint (level 1). Credit the recovery.", "Sam reports the coaching history")
whisper(210, "vale", ["ines", "sam"], "Full marks on verdict and trap. Ines, deliver it with the failing check.", "Vale decides the verdict")
move(212, "ines", "panel_table", "terminal", "run the Bruin checks at the terminal")
call(213, "ines", "bruin", "check", "ran 5 quality checks", 2600, "Bruin's checks prove the planted trap")
ev(215.5, "check.result", "ines", "no duplicate visits, so this check passes", task=T, text="Check passed: visit ids are unique.",
   data={"check": "duplicate_rows.unique_visit", "trap": "duplicate_rows", "passed": True,
         "detail": "visit_id is unique (300 of 300)", "bruinRun": "run-mock-2"})
ev(215.7, "check.result", "ines", "the loyalty flag holds only the values the dictionary describes", task=T,
   text="Check passed: the loyalty flag matches the dictionary.",
   data={"check": "dictionary_flip.loyalty_flag_values", "trap": "dictionary_flip", "passed": True,
         "detail": "loyalty_member holds only 0 and 1 (20 members of 60 customers)", "bruinRun": "run-mock-2"})
ev(215.9, "check.result", "ines", "members and others use both point-of-sale versions in similar shares", task=T,
   text="Check passed: no point-of-sale imbalance between the groups.",
   data={"check": "confounder.pos_version_balance", "trap": "confounder", "passed": True,
         "detail": "members are 35% of visits on POS 4.2 and 30% on POS 5.0", "bruinRun": "run-mock-2"})
ev(216.1, "check.result", "ines", "every visit joins to its customer and store", task=T,
   text="Check passed: nothing is missing across the tables.",
   data={"check": "hidden_variable.joins_complete", "trap": "hidden_variable", "passed": True,
         "detail": "300 of 300 visits join to a customer and a store", "bruinRun": "run-mock-2"})
ev(216.5, "check.result", "ines", "the planted trap: West's spend is out of range for dollars", task=T,
   text="Check failed: West's spend is out of range.",
   data={"check": "unit_mismatch.spend_range_by_region", "trap": "unit_mismatch", "passed": False,
         "detail": "West spend runs 792 to 5600; every other region runs 4 to 74", "bruinRun": "run-mock-2",
         "rows": [["v0083", "st04", 5600.0], ["v0165", "st04", 5272.0], ["v0150", "st04", 5108.0]]})
ev(218, "ledger.seal", "system", "seal the grade in the hash chain", task=T,
   data={"index": 1, "hash": "5b0e2c4f9a7d", "prev": "000000000000",
         "record": {"taskId": T, "score": 0.9, "verdict": "fails", "trap": "unit_mismatch"}})
quotes = [{"text": "its max is 5600 while other regions top out near 74", "source": "note"},
          {"text": "spend / 100", "source": q6}]
verdict_text = ("Right verdict, right trap. You wrote \"its max is 5600 while other regions top out near 74\", which is exactly "
                "what the failing check shows. Your fix, spend / 100, is the right one. You lose a little for needing a hint.")
ev(220, "verdict", "ines", "graded against the answer key, with the failing Bruin check as evidence", task=T,
   text="Passed: 0.9.",
   data={"taskId": T, "result": "passed", "score": 0.9, "parts": {"verdict": 1, "trap": 1, "evidence": 1, "hints": -0.1},
         "correctVerdict": "fails", "correctTrap": "unit_mismatch", "text": verdict_text, "quotes": quotes,
         "failingCheck": "unit_mismatch.spend_range_by_region",
         "ledger": {"index": 1, "hash": "5b0e2c4f9a7d", "prev": "000000000000"}})
ev(220.2, "panel.transcript", "ines", "the verdict is in, so the panel's whispers are open", task=T,
   data={"taskId": T, "whispers": whispers})
say(221, "ines", "learner", verdict_text, "deliver the verdict out loud", quotes=quotes)
ev(226, "task.end", "system", "the verdict is in", task=T,
   data={"taskId": T, "score": 0.9, "beatRival": True, "trap": "unit_mismatch",
         "pickReason": "no history, so every trap sat at 0.15; the bandit's draw was highest for unit mix-ups",
         "bandit": {"unit_mismatch": {"mean": 0.15, "sample": 0.71}, "duplicate_rows": {"mean": 0.15, "sample": 0.52},
                    "dictionary_flip": {"mean": 0.15, "sample": 0.33}, "confounder": {"mean": 0.15, "sample": 0.48},
                    "hidden_variable": {"mean": 0.15, "sample": 0.29}, "none": {"mean": 0.15, "sample": 0.44}}})
ev(227, "mastery.update", "system", "knowledge tracing after a correct answer on a unit mix-up", task=T,
   text="Unit mix-up mastery: 0.15 to 0.61.",
   data={"trap": "unit_mismatch", "from": 0.15, "to": 0.61, "correct": True, "attempts": 1, "bruinRun": "run-mock-3"})
call(227, "system", "bruin", "run", "updated the learner model (bkt_mastery)", 2100, "the learner model runs as a Bruin asset")
ev(235, "appeal.open", "learner", "the learner thinks the hint deduction is unfair", task=T,
   text="The learner appealed.",
   data={"appealId": "a1", "taskId": T, "reason": "I'd have found it without the hint, I was about to group by region.",
         "room": "band"})
call(235.5, "system", "band", "send_message", "relayed the appeal into the panel room", 150, "appeals are argued in the BAND room")
ev(240, "appeal.message", "sam", "Sam reports what the log shows", to="learner", task=T,
   text="The log shows two repeats of the same comparison before my question. The hint came first.",
   data={"appealId": "a1", "text": "The log shows two repeats of the same comparison before my question. The hint came first.",
         "bandMessageId": "band-mock-40"})
ev(244, "appeal.ruling", "ines", "the event log shows the hint came before the region query", task=T,
   text="Appeal ruled: the grade stands.",
   data={"appealId": "a1", "upheld": True, "oldScore": 0.9, "newScore": 0.9,
         "reason": "q5, the first region query, ran 13 s after Sam's hint, so the deduction stands."})
ev(250, "ask", "learner", "the learner asked an agent why", to="vale", text="Why did I get this task first?")
ev(253, "ask.answer", "vale", "answered only from what Vale saw: the learner profile and the bandit draw", to="learner",
   text="You were new, so every skill sat at 0.15. The bandit's draw was highest for unit mix-ups, a very common trap in real exports.",
   data={"sources": ["your learner profile", "the bandit's draw for this task"]})
ev(258, "session.end", "system", "judge mode is one task", data={"tasks": 1, "totalScore": 0.9})
with open(root / "mock_session.jsonl", "w") as f:
    for e in events:
        f.write(json.dumps(e) + "\n")
print(len(events), "events")

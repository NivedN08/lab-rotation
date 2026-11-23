# Events

Each session is a list of events. The server writes them to
`data/sessions/<sessionId>.jsonl`, one per line. The browser reads them with
`GET /api/session/:id/events?since=N`, polled every second, which returns
`{events, next}`. The floor, the workspace, the lab log, the transcript and the
sponsor strip are all drawn from these events. Types live in
`web/src/api/types.ts` (`LabEvent`).

The contract only grows from here: new kinds and new optional fields, added by N1 and
announced to both of us. Ask for changes in `requests/<your stream>.md`.

## Fields

| field | type | required | meaning |
|---|---|---|---|
| `seq` | int | yes | 1, 2, 3 ... within a session. `next` in a reply is the last `seq` it returned. |
| `t` | number | yes | Seconds since the session started (millisecond precision). |
| `k` | string | yes | The kind, from the list below. |
| `agent` | string | yes | Who did it, or who it is about: an agent id. `system` when no agent did. |
| `why` | string | yes | The reason, in plain words. Never empty. This is the decision log the judges read. Before a task's verdict no `why` names its trap or the columns that matter (see "Before the verdict" below). |
| `to` | string | no | The second agent, for events between two (whispers, moves toward someone, appeal messages). |
| `task` | string | no | The task slot id (`t1`, `t2`, `t3`). |
| `text` | string | no | A plain-words line for the lab log, or the words spoken. |
| `data` | object | no | Details for that kind, listed below. Field names are camelCase. |

Agent ids: `vale`, `ines`, `sam`, `telem`, `riley`, `learner`, `system`.

Readers ignore fields they don't know. An event of an unknown kind is shown in the
lab log as its `text` (or `why`) and otherwise ignored.

## Shared values

- **trap**: `duplicate_rows`, `unit_mismatch`, `dictionary_flip`, `confounder`,
  `hidden_variable`, `none`. Mastery uses the same ids, with `none` standing for
  "trusting a clean result".
- **verdict**: `holds`, `fails`, `cant_tell`.
- **mode**: `rotation` (3 tasks with rising tiers) or `judge` (one task, 240 s).
- **tier**: `1` one trap in one table; `2` a trap plus a decoy; `3` a trap that
  spans two tables.
- **place** (for `agent.move`): `door`, `vale_office`, `learner_desk`, `riley_desk`,
  `shelves`, `terminal`, `panel_table`, `whiteboard`.
- **Evidence** is in the same shape as in `api.md`: `{kind, source, sql?, row?, column?, value?, label}`.

## Kinds and their `data`

Fields marked `?` are optional. The front end reads the fields in **bold**; the rest
are there for the lab log, the verdict card and the people reading them.

### Session and task
- `session.start` (system): `mode`, `learner`, `tasks` (the number of slots).
- `task.picked` (vale): **`taskId`**, **`title`**, **`brief`** (the same text as
  `GET /task`), **`seconds`** (the time allowed: 240 in judge mode), `tier`, `claim`,
  `dictionary` (the data dictionary in Markdown, as in `GET /task`), `reason` (why this
  task, also in `why`), `fallback` (true when the rules fallback
  chose instead of the bandit). None of these name the trap; the trap is never sent
  before the verdict. In a replay `GET /task` is null, so the screen reads the task
  from this event.
- `task.end` (system): `taskId`, `score` (0 to 1), `beatRival`, `trap`, `pickReason`
  (the full reason for the pick, now that it can name the trap), `bandit?`
  (`{trap: {mean, sample}}`).
- `session.end` (system): `tasks`, `totalScore`.

### Floor
- `agent.move`: `from`, `place`. The floor animates the walk.
- `agent.say`: `text` is the line and `to` the listener. `data`: `hintLevel?` (0 to 3,
  Sam only), `quotes?` (`[{text, source}]`, where `source` is `"note"` or a query's
  SQL. Code has checked every quote word for word against its source.)
- `voice.line`: **`file`** (played from `/api/audio/:file`), `lineOf` (the `seq` of the
  `agent.say` it voices), `seconds`, `cost?`, `provider` (`runware`, or `browser`,
  in which case `file` is empty and the browser speaks the `agent.say` text).

### Librarian (telem)
- `search`: `query`, `results` (`[{title, url, snippet}]`), **`trace`** (a Telem AI
  trace link), `cached` (true when a recorded result answered), `phase?` (`topic` or
  `case`), `trap?` (only with `case`). Each task has two:
  - `topic`, during the brief: background on the claim. The query is built from the
    public claim alone, so a clean twin with the same claim gets the same search, and
    Telem's line says nothing about what could be wrong.
  - `case`, after the task's `panel.transcript`: a real case of this task's trap ("this
    happens in real life"), or on a clean task (`trap: none`) a case of trusting a clean
    result. The search runs only after the verdict, since its query names the trap.
- `monitor.hit`: `title`, `url`, **`trace`**, `summary` (the case of the day).

### Learner
- `learner.query`: `queryId` (`q1`, `q2` ...), `sql`, `ok`, `rowCount`, `ms`, `error?`,
  `useful?` (set by the struggle meter: did the query touch a column that matters?).
  `useful` names the columns that matter, so the server holds it back until the task's
  `panel.transcript`, as it does whisper text. `why` is the same for every query
  ("the learner ran a query in the SQL box", or "the query failed").
- `learner.evidence`: `action` (`add` or `remove`), `items` (`[Evidence]`). The server
  sends it when the answer arrives, listing the cited items (there is no separate
  evidence route).
- `learner.answer`: **`verdict`**, **`trap`**, `note` (the learner's own words),
  `evidence` (`[Evidence]`).
- `meter.update` (system): `value` (0 to 1), `idleSeconds`, `deadEnds`,
  `wrongGuesses`, `hintLevel` (0 to 3). Sent after every query (and when the reading
  changes), so its timing says nothing about the query. Its `why` is one of three fixed
  lines: "the learner ran a query", "a query failed", "the meter moved"; it never says
  whether a query was useful. The reading itself is in `data`.

### Rival (riley)
- `rival.answer`: **`verdict`**, **`trap`**, `note`, `model`, `provider` (`runware` or
  `claude_fallback`). Sent after `learner.answer`.

### Panel
- `panel.whisper`: a private message between panel agents in the BAND room. `agent`
  sends it, `to` is the first recipient, and `data.cc` lists any others; the floor
  flies an envelope to each. `data`: `text?`, `sealed?`, `bandMessageId?`, `local`
  (true when BAND was down and the local room carried it). The server holds the text
  back: until the task's `panel.transcript`, a whisper has no `text` and has
  `sealed: true`. Its `why` is shown all along, so it comes from a fixed set of
  templates by speaker and purpose, never from agent output: "Sam asks the panel before
  a hint", "Ines gives Sam a direction", "Vale approves the hint level", "Ines shares the
  basis for the grade", "Sam reports the coaching history", "Vale decides the verdict". Once the transcript is out (and in any replay of a finished task, read
  from `since=0`), whispers arrive with `text` filled in; the front end hides it in a
  replay until the `verdict` event has played.
- `panel.transcript` (ines): sent right after the `verdict`. `taskId`, `whispers`
  (`[{seq, agent, to, text}]`): the text of every whisper of that task.
- `check.result` (ines): `check` (an id such as `unit_mismatch.spend_range_by_region`),
  `trap`, `passed`, `detail` (one line), `rows?` (up to 5 failing rows, public columns
  only), `bruinRun?`. Sent only after the answer, one per check that ran (one per trap
  id). The Bruin run that ran them is one `sponsor.call` with `count: 1`; the sponsor
  totals count checks from these events.
- `verdict` (ines): **`taskId`**, **`result`** (`passed` or `failed`), `score` (0 to 1),
  `parts` (`{verdict, trap, evidence, hints}`), `correctVerdict`, `correctTrap`, `text`
  (the feedback), `quotes`, `failingCheck`, `ledger` (`{index, hash, prev}`).
- `ledger.seal` (system): `index`, `hash`, `prev`, `record` (`{taskId, score, verdict, trap}`).

### Appeal
- `appeal.open` (learner): `appealId`, `taskId`, `reason`, `room` (`band` or `local`).
- `appeal.message`: `appealId`, `text`, `bandMessageId?`. `agent` is the speaker.
- `appeal.ruling` (ines): `appealId`, `upheld` (true means the grade stands), `oldScore`,
  `newScore`, `reason`.

### Learning
- `mastery.update` (system): **`trap`**, **`from`**, **`to`** (scores 0 to 1),
  `correct`, `attempts`, `bruinRun?`. One event per trap whose score changed.

### Sponsors
- `sponsor.call` (agent `system`): **`sponsor`** (`band`, `telem`, `bruin`, `runware`,
  `glasser`, `teamily`), **`label`** (what was done, in plain words), **`count`**
  (calls in this event, usually 1), **`failed?`**, **`cost?`** (dollars), **`trace?`**
  (link). It also has `op` (`search`, `fetch`, `tts`, `image`, `chat`, `send_message`,
  `run`, `check`, ...), `by` (the agent that made the call), `ms` and `fallback` (true
  when a recorded fallback answered).

### Ask any agent
- `ask` (learner): `to` is the agent asked, `text` the question.
- `ask.answer`: `agent` is the one asked, `text` the answer, `data.sources` (in plain
  words) what it used.

## Before the verdict

Until a task's `verdict`, nothing the browser receives may tell its trap apart from a
clean twin (the same task with no trap). The engine enforces it:

- No `why`, `text` or `data` names the trap. The trap and the full pick reason arrive
  with `task.end`; the check ids arrive with `check.result`, after the answer.
- Pre-answer lines from agents (Vale's brief, Telem's background, answers to `ask`) are
  replaced by a fixed line if they name *any* trap, so a replacement says nothing either.
- Telem's pre-answer search uses only the claim; the real case of the trap comes after the
  verdict (see `search`).
- Whisper text and `learner.query.useful` wait for `panel.transcript` (the session's
  jsonl on disk keeps both); whisper and meter `why`s are fixed templates.
- Sam's hints are the exception: they point the way on purpose, as questions.

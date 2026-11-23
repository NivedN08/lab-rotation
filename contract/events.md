# Events

Every session is a stream of events, one JSON object per line. The server writes
them to `data/sessions/<session>.jsonl` and streams them to the browser
(`GET /api/sessions/{id}/events`, see `api.md`). The web app draws the floor, the
lab log, the transcript and the sponsor strip from these events only.

The contract is frozen at 12:00. After that it only grows (new kinds, new optional
fields), and only N1 edits it. Ask for changes in `requests/<your stream>.md`.

## Envelope (every event)

| field | type | required | meaning |
|---|---|---|---|
| `seq` | int | yes | 1, 2, 3 ... within a session, no gaps |
| `ts` | string | yes | ISO 8601 UTC, e.g. `2026-11-23T20:15:03.120Z` |
| `session` | string | yes | session id, e.g. `s-7f3a` |
| `kind` | string | yes | one of the kinds below |
| `agent` | string | yes | who acted: an agent id, `learner` or `system` |
| `why` | string | yes | the reason, in plain words. Shown in the lab log. Never empty. |
| `to` | string | no | who it is for: an agent id, `learner`, `panel` or `all` |
| `text` | string | no | words to show (or speak) |
| `task` | string | no | task id the event belongs to |
| `evidence` | list | no | refs that back the event, see Evidence refs |
| `data` | object | no | kind-specific fields, listed below |

Agent ids: `vale`, `ines`, `sam`, `telem`, `riley`. Plus `learner` and `system`.

Unknown fields must be ignored by readers. Unknown kinds must be shown in the lab
log as plain text and otherwise ignored.

## Shared values

- **trap**: `duplicate_rows`, `unit_mismatch`, `dictionary_flip`, `confounder`,
  `hidden_variable`, `none` (a clean twin: no trap, the claim holds as stated).
- **skill** (learner model): the five traps plus `trust_clean`.
- **tier**: `1` one trap in one table; `2` a trap plus a decoy; `3` a trap that
  spans two tables.
- **verdict**: `holds`, `fails`, `cannot_judge`.
- **mode**: `rotation` (3 tasks, rising tiers) or `judge` (one task, 4-minute clock).
- **place** (floor spots for `agent.move`): `door`, `vale_office`, `learner_desk`,
  `riley_desk`, `shelves`, `terminal`, `panel_table`, `whiteboard`.

## Evidence refs

```json
{"type": "query", "id": "q3"}
{"type": "row", "table": "visits", "key": "v0412"}
{"type": "column", "table": "visits", "column": "spend"}
{"type": "cell", "table": "visits", "key": "v0412", "column": "spend"}
{"type": "check", "id": "unit_mismatch.spend_range_by_region"}
{"type": "source", "url": "https://...", "trace": "https://..."}
{"type": "message", "id": "band:..."}
```

`key` is the value of the table's key column (named in the task's table list).

## Kinds

Each entry lists its `data` fields. Fields marked `?` are optional.

### Session and task

- **`session.start`**: `mode`, `learner` (learner id), `clock_s?` (judge mode: 240).
- **`task.picked`** (agent `vale`): `task` (id), `skill`, `tier`, `claim`,
  `tables` (list of table names), `reason` (why this task, also in `why`),
  `bandit?` (`{"skill": {"mean": 0.41, "sample": 0.37}, ...}`), `fallback?` (bool:
  the rules fallback chose).
- **`task.end`**: `task`, `score` (0..1), `beat_rival` (bool).
- **`session.end`**: `tasks` (count), `total_score`.

### Floor

- **`agent.move`**: `from`, `place` (destination). The floor animates the walk.
- **`agent.say`**: `text` set; `to` set. `data`: `hint_level?` (0..3, Sam only),
  `quotes?` (list of `{"text": "...", "source": {"type": "query", "id": "q3"}}`,
  every quote was checked by code against its source), `audio?` (see voice.line).
- **`voice.line`**: `line_of` (seq of the `agent.say` it voices), `url`
  (`/api/audio/<file>.mp3`), `duration_s`, `cost_usd?`, `provider` (`runware` or
  `browser` when we fall back to browser speech; then `url` is empty).

### Librarian

- **`search`** (agent `telem`): `query`, `results` (list of `{"title", "url",
  "snippet"}`), `trace` (Telem AI trace link), `cached` (bool).
- **`monitor.hit`** (agent `telem`): `title`, `url`, `trace`, `summary` (the case
  of the day).

### Learner

- **`learner.query`**: `id` (`q1`, `q2` ...), `sql`, `ok` (bool), `row_count`,
  `ms`, `error?`, `useful` (bool, set by the struggle meter: did it touch a
  column that matters?).
- **`learner.evidence`**: `items` (list of evidence refs), `action` (`add` or
  `remove`).
- **`learner.answer`**: `verdict`, `trap`, `text` (the learner's own words),
  `evidence` (refs), `via` (`text` or `voice`).
- **`meter.update`** (agent `system`): `value` (0..1), `parts` (`{"idle_s": 95,
  "dead_ends": 2, "wrong_guesses": 0}`), `hint_level` (0..3).

### Rival

- **`rival.answer`** (agent `riley`): `verdict`, `trap`, `text`, `model` (the
  open model's name), `provider` (`runware` or `claude_fallback`). Shown to the
  learner only after `learner.answer`.

### Panel

- **`panel.whisper`**: private message between panel agents in the BAND room.
  `from`, `to` (list of agent ids), `text`, `band_message_id?`, `local` (bool:
  true when BAND is down and the local room carried it). The floor flies an
  envelope from `from` to each `to`. The browser hides `text` until the
  verdict.
- **`check.result`** (agent `ines`): `check` (id, e.g.
  `duplicate_rows.unique_visit`), `trap`, `passed` (bool), `detail` (one line),
  `rows?` (up to 5 failing rows, public columns only), `bruin_run?` (run id).
- **`verdict`** (agent `ines` or `vale`): `score` (0..1), `parts`
  (`{"verdict": 1, "trap": 1, "evidence": 0.5}`), `correct_verdict`,
  `correct_trap`, `text` (the feedback), `quotes` (as in agent.say),
  `failing_check` (check id), `ledger` (`{"index": 3, "hash": "ab12..",
  "prev": "9f0c.."}`).
- **`ledger.seal`** (agent `system`): `index`, `hash`, `prev`, `record` (what was
  sealed: `{"task", "score", "verdict", "trap"}`).

### Appeal

- **`appeal.open`** (agent `learner`): `text`, `room` (BAND chat id or `local`).
- **`appeal.message`**: `from`, `text`, `band_message_id?`.
- **`appeal.ruling`** (agent `ines`): `upheld` (bool: the original grade stands),
  `old_score`, `new_score`, `reason`.

### Learning

- **`mastery.update`** (agent `system`): `learner`, `skill`, `before`, `after`
  (0..1, BKT probability), `correct` (bool), `bruin_run?`. One event per skill
  that changed.

### Sponsors

- **`sponsor.call`** (agent: whoever made the call, or `system`): `sponsor`
  (`bruin`, `band`, `telem`, `runware`, `glasser`, `teamily`), `op` (e.g.
  `search`, `fetch`, `tts`, `image`, `chat`, `send_message`, `run`, `check`),
  `ok` (bool), `ms`, `cost_usd?`, `trace?` (link), `fallback` (bool: a recorded
  fallback answered). The sponsor strip counts these.

### Ask any agent

- **`ask`**: (agent `learner`, `to` the agent asked) `text` the question.
- **`ask.answer`**: (agent: the agent asked) `text`, `seen` (list of evidence
  refs the answer used; the agent only sees what its role allows).

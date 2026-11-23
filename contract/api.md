# API

The Python server (`web/server.py`, summit-lab's server, extended by N1) serves the
browser. The front end calls these routes from one file (`web/src/api/client.ts`),
with types in `web/src/api/types.ts`. N1 can add fields to a reply but never renames
or removes one. If the backend needs a change, N1 makes it here and the front end
adapts.

Dev: `uv run python web/server.py` answers `/api` on port 8790, and `npm run dev`
proxies to it. The front end's own mock is on by default; `?mock=0` calls the server.

- All bodies and replies are JSON unless noted. Fields are camelCase.
- `:id` is the `sessionId`.
- Errors: a non-2xx status with `{"error": "plain words"}`. The browser shows the
  message as is, except 404 and 503, which show "not ready yet".
- Every timestamp `t` is seconds since the session started.

**Server mock.** With `LAB_MOCK=1`, the server replays `contract/mock_session.jsonl`
at real speed (`LAB_MOCK_SPEED` multiplies the speed) and serves the tables in
`contract/mock_task/`. Every route works in mock mode.
A start with `{"mock": true}` gets a mock session from a live server too, and any
session id that starts with `mock-` is a mock replay. In mock mode answer, appeal and
ask take canned replies and add no events.

**Visibility.** No reply contains the answer key, the trap or the bank id of a task
that has not been graded yet, panel whisper text before the verdict, or any key.
The server enforces the whisper rule itself: before a task's `panel.transcript` (sent
right after its verdict), `panel.whisper` events have no `text` and carry `sealed: true`.

## Routes

| Job | Route | Sends | Gets back | Calls |
|---|---|---|---|---|
| Start a session | `POST /api/session/start` | optional `{mode?: "rotation" \| "judge", learner?}`. No body means rotation. | `{sessionId, tasks: [{id, title}], task}` | `lab.session.engine.start_session` |
| Current task | `GET /api/session/:id/task` | | `{task}`, or `{task: null}` when all are done | `engine.current_task` |
| List tables | `GET /api/session/:id/tables?task=` | `task` (optional, a slot id) | `[{name, about, columns: [{name, type, about?}], rowCount}]` | `lab.workspace_sql.tables` |
| Read rows | `GET /api/session/:id/tables/:table/rows?offset=&limit=&task=` | | `{rows: [[cell]]}` | `lab.workspace_sql.table_rows` |
| Column profiles | `GET /api/session/:id/tables/:table/profile?task=` | | `{table, columns: [ColumnProfile]}` | `lab.workspace_sql.profile` |
| New events | `GET /api/session/:id/events?since=N` | `since` is the last reply's `next` (0 the first time) | `{events: [LabEvent], next}` | `engine.events_since` |
| Run SQL | `POST /api/session/:id/sql` | `{sql}` | `{columns, rows, ms, truncated}` or `{error}` | `lab.workspace_sql.run_query`, then `engine.on_query` |
| Submit answer | `POST /api/session/:id/answer` | `{taskId, verdict, trap, evidence: [Evidence], note}` | `{accepted: true}` | `engine.on_answer` |
| Open appeal | `POST /api/session/:id/appeal` | `{taskId, reason}` | `{appealId}` | `engine.on_appeal` |
| Appeal message | `POST /api/session/:id/appeal/:appealId/message` | `{text}` | `{ok: true}` | `engine.on_appeal_message` |
| Mastery | `GET /api/session/:id/mastery` | | `{traps: [{trap, score, attempts}]}` | `lab.learner.mastery` |
| Ask an agent | `POST /api/session/:id/ask` | `{agent, text}` | `{agent, text, sources: [string], links?, trace?}` | `engine.ask` |
| Agents | `GET /api/agents` | | `[{id, name, role, reads, portrait}]` | `lab.session.cast.agents` |
| Portraits | `GET /api/portraits/:file` | | the image (not JSON) | static, from `data/portraits/` |
| Voice audio | `GET /api/audio/:file` | | the audio file (not JSON) | static, from `data/audio/` |
| Sponsor totals | `GET /api/session/:id/sponsors` | | `SponsorTotals` (below) | `engine.sponsor_totals` |
| Demo replay | `GET /api/demo` | | `{session, start, end, speed}`, or `{session: null}` | `engine.demo` |
| Health | `GET /api/health` | | `{ok, mock, band: "live" \| "local"}` | |

## Shapes

**Task** (in `start` and `task`):
`{id, title, brief, seconds, claim, tier, dictionary}`.

- `id` is a slot id for this session (`t1`, `t2`, `t3`), so the start reply can list
  every slot before the learner model fills it. The task bank's own id stays on the
  server, because it would give the trap away.
- `seconds` is the time allowed: 240 in judge mode.
- `claim` is the sentence the learner checks. `tier` is 1, 2 or 3.
- `dictionary` is the data dictionary in Markdown. It is the only place the
  `dictionary_flip` trap shows up.

The task changes one at a time. The front end polls `GET /task` after an answer
until `id` changes, so there is no "next task" route.

**Column type**: `text`, `int`, `real` or `date`. Mapping from DuckDB: VARCHAR → text;
the integer types → int; DOUBLE, FLOAT and DECIMAL → real; DATE and TIMESTAMP → date.

**Rows** come in a fixed order: by the table's key column, ascending. Row `n`
(1-based) is the same row on every call. A cell is a string, number, boolean or
`null`. `limit` is at most 500.

**ColumnProfile**:
`{column, type, count, nulls, distinct, min?, max?, mean?, top: [{value, count}]}`.
`min` and `max` are sent for numeric and date columns, `mean` for numeric ones.
`top` holds up to 5 values, most common first.

**SQL**: read-only. It runs on an in-memory DuckDB that holds only this task's public
tables, one statement at a time, with no file, network or extension access. Results
stop at 500 rows (`truncated: true` when the cap cut the result) and queries time out
after 3 s. A bad or blocked query returns `200 {error}`. Every query, good or bad,
becomes a `learner.query` event.

**Verdict** (in an answer): `holds`, `fails` or `cant_tell`.

**Trap ids**: `duplicate_rows`, `unit_mismatch`, `dictionary_flip`, `confounder`,
`hidden_variable`, `none`. The browser sends the id; the labels are for display only.
Mastery has one entry per trap id, and `none` stands for the skill "trusting a clean
result". `score` runs from 0 to 1.

**Evidence**: `{kind: "row" | "column" | "cell", source, sql?, row?, column?, value?, label}`.

- `source` is a table name, or `"query"` for a SQL result.
- For a table, `row` is the absolute 1-based row number, counting the offset
  (the fixed order above).
- For a SQL result, `row` is the 1-based position within that result, and `sql` holds
  the query so the server can rebuild the result.
- `value` is the cell's value, for `cell` evidence. `label` is a description in plain
  words.

**Agents**: `role` is the floor role (`director`, `referee`, `library`, `head`,
`team-a`, `team-b`). `reads` says in plain words what the agent can see. `portrait`
is a URL or `null`.

**Ask**: the agent answers only from what its role could see. `sources` lists what it
used, in plain words.

**Appeal**: the server relays the appeal into the panel's BAND room (or a local room
when BAND is down). Replies and the ruling arrive as `appeal.message` and
`appeal.ruling` events.

**SponsorTotals**:
```json
{"band": {"messages": 0},
 "telem": {"searches": 0, "monitorHits": 0, "traces": []},
 "bruin": {"checksRun": 0, "checksFailed": 0},
 "runware": {"lines": 0, "cost": 0.0},
 "glasser": {"calls": 0},
 "teamily": {"posts": 0}}
```
`cost` is in dollars. `teamily` is an addition the front end may ignore.
`bruin.checksRun` and `checksFailed` count `check.result` events (one per check), not
`sponsor.call` counts: one Bruin run that runs five checks is one call.

**Demo**: `GET /api/demo` names a recorded session to replay on stage and on the
live link. `session` is its sessionId; `start` and `end` are `t` values in seconds
(the part worth showing); `speed` is the playback multiplier. Nived picks it with
`LAB_DEMO_SESSION`, `LAB_DEMO_START`, `LAB_DEMO_END` and `LAB_DEMO_SPEED` in `.env`.
Unset, the reply is `{session: null}` and the front end plays its own mock session.

**Recorded sessions**: every session is saved as it runs to
`data/sessions/<sessionId>.jsonl` and survives a server restart. For a finished
session, `GET /api/session/:id/events?since=0` returns every event, and `next` stays
at the last `seq`. The other read routes (`task`, `tables`, `rows`, `mastery`,
`sponsors`) keep working for a finished session, so a replay can show the workspace.

**Events**: see `events.md`.

## Additions (N1, after the freeze; all optional)

- `task` query on `tables`, `rows` and `profile` (`?task=t2`): the slot id (`t1`, `t2`,
  `t3`) whose tables to read, so the front end can re-read the tables when the task
  changes. Without it the routes use the current task (the last one when the session is
  over). Only the current task or one already finished in this session is served; a
  future or unknown task returns `409 {error}`, so task 3's tables wait their turn. In a
  finished session (a replay) every task works. A malformed id is `400`. `POST /sql`
  always runs on the current task.
- `GET /api/agents` items also carry `title` ("Lab head", "Examiner", ...).
  `portrait` is `/api/portraits/<agent>.png` when that file exists.
- Roles in `GET /api/agents`: `vale` director, `ines` referee, `sam` head, `telem`
  library, `riley` team-b. The learner is the agent id `learner`.
- Answering a task that is not open, or appealing a task twice or before its verdict,
  returns `409 {error}`. In judge mode (and when a rotation task's `seconds` run out) the
  server answers for the learner with `cant_tell`, and `learner.answer`'s `why` says so.
- Before a task's verdict, `GET /events` holds back whisper text and
  `learner.query.useful` (they arrive with the task's `panel.transcript`), and nothing in
  the stream tells the trap apart from a clean twin. See "Before the verdict" in
  `events.md`.
- `ask` to `telem` runs a live Telem search with the learner's question; the reply adds
  `links` (`[{title, url}]`) and `trace`.

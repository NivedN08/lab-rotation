# Front end <-> backend contract

This file is the contract. The backend is built to match it exactly. Do not rename anything here without telling the front end.
All calls live in `client.ts`; nothing else in the front end touches `/api`. Shapes are in `types.ts`, ids in `traps.ts`.
`mock.ts` answers the same calls with fake data. It is on by default. Add `?mock=0` to the URL to call the real server.

Errors: any non-2xx reply, or a JSON body `{"error": "plain words"}`, is shown to the learner as is (except 404 and 503, which show a generic "not ready yet").
All timestamps `t` are seconds since the session started. `:id` is the `sessionId`. All bodies and replies are JSON unless noted.

## Routes

| Job | Route | Sends | Gets back |
|---|---|---|---|
| Start a session | `POST /api/session/start` | optional `{mode?: "rotation" \| "judge", learner?: string}`. Sending nothing means `{mode: "rotation"}`. | `{sessionId, tasks: [{id, title}], task}`. `tasks` is the whole rotation in order. `task` is the current one, `{id, title, brief, seconds}`, or `null`. |
| Current task | `GET /api/session/:id/task` | nothing | `{task}`, same shape, `null` when all are done. Tasks come one at a time; polled after an answer is sent until the id changes. |
| List tables | `GET /api/session/:id/tables` | nothing | `[{name, about, columns: [{name, type}], rowCount}]`. `type` is `text`, `int`, `real` or `date`. |
| Read rows | `GET /api/session/:id/tables/:table/rows?offset=&limit=` | query string | `{rows: [[cell, ...], ...]}`. A cell is a string, number, boolean or `null`. |
| Column profiles | `GET /api/session/:id/tables/:table/profile` | nothing | `{table, columns: [{column, type, count, nulls, distinct, min?, max?, mean?, top: [{value, count}]}]}`. `min` and `max` for numeric and date columns, `mean` for numeric, `top` up to 5, most common first. |
| New events | `GET /api/session/:id/events?since=N` | `since` = the last reply's `next` (0 first) | `{events: [LabEvent], next}`. Polled every second. |
| Run SQL | `POST /api/session/:id/sql` | `{sql}` | `{columns: [name], rows: [[cell]], ms}` or `{error}` |
| Submit answer | `POST /api/session/:id/answer` | `{taskId, verdict, trap, evidence: [Evidence], note}` | `{accepted}`. The verdict arrives later as an event. |
| Open appeal | `POST /api/session/:id/appeal` | `{taskId, reason}` | `{appealId}` |
| Appeal message | `POST /api/session/:id/appeal/:appealId/message` | `{text}` | `{ok}`. Replies and the ruling arrive as events. |
| Mastery | `GET /api/session/:id/mastery` | nothing | `{traps: [{trap, score, attempts}]}`. One entry per trap id below, including `none`. `score` is 0 to 1. |
| Ask an agent | `POST /api/session/:id/ask` | `{agent, text}` (`agent` is an agent id) | `{agent, text, sources: [string]}`. The agent answers only from what it could see; `sources` says what it used. |
| Agents | `GET /api/agents` | nothing | `[{id, name, role, reads, portrait}]`. `role` is the floor role (`director`, `referee`, `library`, `head`, `team-a`, `team-b`). `reads` is what the agent can read, in plain words. `portrait` is an image URL or `null`. |
| Voice audio | `GET /api/audio/:file` | nothing | The audio file itself (not JSON). `:file` is the `data.file` of a `voice.line` event. |
| Demo session | `GET /api/demo` | nothing | `{session, start, end, speed}`: the id of the recorded session the backend picked for the demo, the seconds (since that session began) to play from and to, and the playback speed (1 is normal). Only `start` to `end` is played, at `speed`, on a loop. `{session: null}` means there is no demo: the front end falls back to the fake session and shows "Sample data". The front end then reads that session's tables, task and events with the routes above, using `session` as `:id`. |
| Sponsor totals | `GET /api/session/:id/sponsors` | nothing | `{band: {messages}, telem: {searches, monitorHits, traces: [string]}, bruin: {checksRun, checksFailed}, runware: {lines, cost}, glasser: {calls}}`. `cost` is in dollars. |

## Ids and values

**Verdict** (`verdict` in an answer): `holds`, `fails` or `cant_tell`.

**Trap ids.** The answer form sends the id, never the label; labels are display only. Mastery's `trap` field uses the same ids.

| id | label |
|---|---|
| `duplicate_rows` | Duplicated rows |
| `unit_mismatch` | Unit mix-up |
| `dictionary_flip` | Misleading data dictionary |
| `confounder` | Batch confounder |
| `hidden_variable` | Hidden column in a second table |
| `none` | No trap (the data is clean) |

**Agent ids** (`agent` and `to` on events, `agent` in an ask): `vale`, `ines`, `sam`, `telem`, `riley`, `learner`, and `system` (events only, for things no agent does, such as sponsor counters).

## Evidence

`{kind: "row" | "column" | "cell", source, sql?, row?, column?, value?, label}`

- `source` is the table name, or `"query"` for a SQL result.
- Table evidence: `row` is the **absolute** 1-based row number in the table, counting from its first row, regardless of which page the learner was on.
- SQL evidence: `row` is the 1-based position **within that result**, and `sql` is also sent so the result can be rebuilt.
- `column` is a column name (for a SQL result, the result's column name). `value` is the cell's value for `cell` evidence.
- `label` is a plain-words description for display.

## Events

`GET /api/session/:id/events` returns `LabEvent`:

| Field | Type | Notes |
|---|---|---|
| `seq` | number | Increasing, unique. `next` in the reply is the last `seq` returned. |
| `t` | number | Seconds since the session started. |
| `k` | string | Event kind, below. |
| `agent` | agent id | **Always set.** Who did it or who it is about. `system` when no agent did. |
| `why` | string | **Always set, never empty.** Why this happened, in plain words. This is the decision log the judges read. |
| `to` | agent id | Optional. Second agent, for events that move between two. |
| `task` | string | Optional. Id of the task the event belongs to. |
| `text` | string | Optional. Plain-words line for the lab log. |
| `data` | object | Optional. Details, per kind. |

Kinds: `session.start`, `task.picked`, `search`, `monitor.hit`, `learner.query`, `learner.evidence`, `agent.say`, `panel.whisper`, `learner.answer`, `rival.answer`, `check.result`, `verdict`, `mastery.update`, `appeal.open`, `appeal.message`, `appeal.ruling`, `voice.line`, `sponsor.call`.

Data that the front end reads:

- `verdict`: `{taskId, result: "passed" | "failed", ...}`. The top bar's marks come from `taskId` and `result`.
- `learner.answer`, `rival.answer`: `{verdict, trap}` (trap id).
- `mastery.update`: `{trap, from, to}` (trap id, scores 0 to 1).
- `voice.line`: `{file}`, played from `/api/audio/:file`.
- `sponsor.call`: `{sponsor: "band" | "telem" | "bruin" | "runware" | "glasser", label, count, failed?, cost?, trace?}`. `agent` is `system`.
- `search`, `monitor.hit`: `{trace}` is a link to the Telem trace.

`mockSession.ts` plays one full task of all of these in about two minutes, each with a `why`. Add `?mockspeed=10` to the URL to play it ten times faster.

## One shared state (`session.ts`)

`useRotation()` and `subscribeEvents(cb)` are the only way the rest of the app reads the session. The first reader starts the session and the single one-second poll; nobody else starts a session, polls or keeps time. `RotationState` holds `sessionId`, `tasks`, `current`, `startedAt` (the clock the Timer counts from), `results` (from verdict events), `events` (all so far), plus `error` and `awaitingNext`. `rotation.configure({mode, learner})` sets the start body before the session starts.

## Demo (`demo.ts`)

The demo replays a **real recorded session** from the backend, never fake data. It is front end only apart from `GET /api/demo`.

1. `getDemo()` calls `GET /api/demo` and gets `{session, start, end, speed}`. With `session: null` it uses the fake session instead (see below).
2. It loads that session's whole event list from the beginning with the normal events route (`GET /api/session/:session/events?since=...`, repeated until it returns no events), so the recording must be readable from `since=0` after it has finished.
3. A player moves a clock through `start` to `end`, looping at the end, and feeds the same rotation state and events a live session produces. `useRotation()` and `subscribeEvents()` work unchanged. Nothing starts a live session while the demo runs.

Controls: `startDemo()` (or `?demo=1`), `stopDemo()`, `demo.play()`, `demo.pause()`, `demo.toggle()`, `demo.setSpeed(n)`, `demo.seek(t)`. `useDemo()` gives `{status, error, playing, speed, position, start, end, sample, timeline}`. `timeline` lists every recorded event's `seq`, `t`, `k` and `agent`, so the bottom timeline can draw marks and rewind. `subscribeJump(cb)` fires on every seek and every loop with the new time and all events up to it, so the floor can reset and redraw; `subscribeEvents` still gets only new events during normal playback.

For the demo to show the task and the top bar, the `task.picked` event's `data` carries `{taskId, title, tier, claim, reason, brief, seconds}`. In a replay the task is shown from `task.picked` only; nothing else is asked for it. Without `title`, tasks are called "Task 1", "Task 2", and so on.

**Mock mode only:** `getDemo()` returns the fake session (`mockSession.ts`), `sample` is `true`, and the page shows a "Sample data" chip (`SampleBadge`, mounted once in the app) for as long as it plays. Against a real backend `sample` is `false` and nothing says "sample".

The workspace Timer follows the recording's clock while the demo runs (time since `task.picked`), so speed, pause, seek and loop all show correctly. `startedAt` in the rotation state is still wall-clock; a reader that draws its own countdown during the demo should use `useDemo().position` and the `task.picked` time in `timeline` the same way.

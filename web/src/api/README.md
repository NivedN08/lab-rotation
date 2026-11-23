# Front end <-> backend routes

All calls live in `client.ts`; nothing else in the front end touches `/api`. Shapes are in `types.ts`.
`mock.ts` answers the same calls with fake data. It is on by default. Add `?mock=0` to the URL to call the real server.
These names are the front end's proposal. Nived: match them, or send your real ones and `client.ts` will change to fit.
Errors: any non-2xx reply, or a JSON body with `{"error": "plain words"}`, is shown to the learner as is.

| Job | Route | Sends | Gets back |
|---|---|---|---|
| Start a session | `POST /api/session/start` | nothing | `{sessionId, tasks: [{id, title}], task}` where `tasks` is the whole rotation in order and `task` is the current one `{id, title, brief, seconds}` or null |
| Current task | `GET /api/session/:id/task` | nothing | `{task}` (same shape, null when all are done). Tasks come one at a time; polled after an answer is sent until the id changes. |
| List tables | `GET /api/session/:id/tables` | nothing | `[{name, about, columns: [{name, type}], rowCount}]` (type: text, int, real or date) |
| Read rows | `GET /api/session/:id/tables/:table/rows?offset=&limit=` | query string | `{rows: [[cell, ...], ...]}` (cell: string, number, boolean or null) |
| New events | `GET /api/session/:id/events?since=N` | `since` = last `next` (0 first) | `{events: [{seq, t, k, text?, data?}], next}`. Polled every second. |
| Run SQL | `POST /api/session/:id/sql` | `{sql}` | `{columns: [name], rows: [[cell]], ms}` or `{error}` |
| Submit answer | `POST /api/session/:id/answer` | `{taskId, verdict: holds\|fails\|cant_tell, trap, evidence: [{kind: row\|column\|cell, source, sql?, row?, column?, value?, label}], note}` | `{accepted}`. The verdict arrives later as an event. |
| Open appeal | `POST /api/session/:id/appeal` | `{taskId, reason}` | `{appealId}` |
| Appeal message | `POST /api/session/:id/appeal/:appealId/message` | `{text}` | `{ok}`. Replies and the ruling arrive as events. |
| Mastery | `GET /api/session/:id/mastery` | nothing | `{traps: [{trap, score 0..1, attempts}]}` |

Trap names come from `traps.ts`: the `trap` field in the answer is one of those exact strings. If Nived's names differ, change that one list.

## Events the floor plays

`GET /api/session/:id/events` returns these kinds in `k`. `a` is the agent (provisional ids: `learner`, `vale`, `ines`, `sam`, `telem`, `riley`); `to` is the second agent for `panel.whisper` and appeal messages; `text` is a plain-words line for the lab log; `data` holds the details.

`session.start`, `task.picked`, `search`, `monitor.hit`, `learner.query`, `learner.evidence`, `agent.say`, `panel.whisper`, `learner.answer`, `rival.answer`, `check.result`, `verdict`, `mastery.update`, `appeal.open`, `appeal.message`, `appeal.ruling`, `voice.line`, `sponsor.call` (`data.sponsor` is `band`, `telem`, `bruin`, `runware` or `glasser`).

The `verdict` event's `data` must carry `{taskId, result: "passed" | "failed"}`; the top bar's marks come from it.

`mockSession.ts` plays all of them in about two minutes. Add `?mockspeed=10` to the URL to play it ten times faster.

`row` is 1-based within what the learner saw. For a SQL result, `source` is `"query"` and `sql` holds the query.

## One shared state (`session.ts`)

`useRotation()` and `subscribeEvents(cb)` are the only way the rest of the app reads the session. The first reader starts the session and the single one-second poll; nobody else starts a session, polls or keeps time. `RotationState` holds `sessionId`, `tasks`, `current`, `startedAt` (the clock the Timer counts from), `results` (from verdict events), `events` (all so far), plus `error` and `awaitingNext`.

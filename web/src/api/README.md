# Front end API layer

**The contract is `contract/api.md` (routes and shapes) and `contract/events.md` (events).** Nived owns it. This folder implements it; where the two differ, the contract wins and we change this folder. Things we need from it that it doesn't say yet are listed at the end.

All backend calls live in `client.ts`. Nothing else in the front end touches `/api`. Shapes are in `types.ts`, trap ids and labels in `traps.ts`.

## Functions and routes

| Function | Route |
|---|---|
| `startSession(options?)` | `POST /api/session/start` |
| `getCurrentTask(id)` | `GET /api/session/:id/task` |
| `getTables(id)` | `GET /api/session/:id/tables` |
| `getRows(id, table, offset, limit)` | `GET /api/session/:id/tables/:table/rows` |
| `getProfile(id, table)` | `GET /api/session/:id/tables/:table/profile` |
| `getEvents(id, since)` | `GET /api/session/:id/events` |
| `runSql(id, sql)` | `POST /api/session/:id/sql` |
| `submitAnswer(id, answer)` | `POST /api/session/:id/answer` |
| `openAppeal(id, taskId, reason)` | `POST /api/session/:id/appeal` |
| `sendAppealMessage(id, appealId, text)` | `POST /api/session/:id/appeal/:appealId/message` |
| `getMastery(id)` | `GET /api/session/:id/mastery` |
| `askAgent(id, {agent, text})` | `POST /api/session/:id/ask` |
| `getAgents()` | `GET /api/agents` |
| `audioUrl(file)` | `GET /api/audio/:file` (a URL for an audio element) |
| `getSponsors(id)` | `GET /api/session/:id/sponsors` |
| `getDemo()` | `GET /api/demo` |
| `getHealth()` | `GET /api/health` |

Errors: a non-2xx reply or `{"error": "plain words"}` is shown as is, except 404 and 503, which show "not ready yet".

## Mock mode (sample data)

On by default. `?mock=0` calls the real server. `mock.ts` answers every function with the contract's own sample task and session: `./mock/` holds copies of `contract/mock_session.jsonl` and `contract/mock_task/`, so sample data has exactly the real format. Re-copy with `sh web/src/api/mock/sync.sh` from the repo root when the contract changes. Tasks `t2` and `t3` in the mock reuse the sample task so the one-task-at-a-time flow can be tried. The mock's SQL is a stand-in that understands only simple `SELECT ... FROM table [WHERE col = value] [LIMIT n]`. `?mockspeed=10` plays the sample session ten times faster.

## One shared state (`session.ts`)

`useRotation()` and `subscribeEvents(cb)` are the only way the rest of the app reads the session. The first reader starts the session and the single one-second poll; nobody else starts a session, polls or keeps time. `RotationState` holds `sessionId`, `tasks`, `current`, `startedAt`, `results` (from `verdict` events), `events` (all so far), `error` and `awaitingNext`. `getRotation()` reads it outside React. `rotation.configure({mode, learner})` sets the start body before the session starts.

## Demo (`demo.ts`)

Replays a **real recorded session** through the same state and events as a live one, never fake data, except in mock mode or when `GET /api/demo` returns `{session: null}`: then the fake session plays and the page shows "Sample data" (`SampleBadge`).

1. `getDemo()` gets `{session, start, end, speed}`. Only `start` to `end` plays, at `speed`, on a loop.
2. The whole event list is read from `since=0`, repeating until a page is empty.
3. A player feeds the shared state. Controls: `startDemo()` (or `?demo=1`), `stopDemo()`, `demo.play()`, `demo.pause()`, `demo.toggle()`, `demo.setSpeed(n)`, `demo.seek(t)`. `useDemo()` gives `{status, error, playing, speed, position, start, end, sample, timeline}`; `timeline` has every recorded event's `seq`, `t`, `k` and `agent`.
4. `subscribeJump(cb)` fires on every seek and loop with the new time and all events up to it. `subscribeEvents` gets only new events during normal playback.
5. In a replay the task comes from `task.picked` only. The workspace Timer follows the recording's clock (time since `task.picked`), so speed, pause, seek and loop show correctly.

## Events we read

We read the fields in bold in `contract/events.md`, and ignore kinds and fields we don't know. The ones the front end acts on: `task.picked`, `verdict` (`taskId`, `result`), `mastery.update`, `panel.whisper` (text in `data.text`), `appeal.*`, `voice.line` (`file`, or `provider: "browser"` with `lineOf`), `sponsor.call`, `check.result`, `monitor.hit`.

Sponsor totals: live, from `GET /sponsors`. In a replay they are added up from events (`sponsors.ts`) so they follow seek and rewind: BAND messages are `band` calls, Telem searches are `telem` calls with `op: "search"`, monitor hits are `monitor.hit` events, Bruin checks are `check.result` events (each has `passed`), Runware lines are `runware` calls with `op: "tts"`.

## Not yet in the contract (asked of Nived)

- `task.picked` has no `dictionary`, so a replay cannot show the data dictionary (only `GET /task` has it, and that is null in a replay).
- `sponsor.call` for Bruin checks says "ran 5 quality checks" with `count: 1`, so the number of checks cannot be added up from `sponsor.call`; we count `check.result` events instead.
- `events.md` says `panel.whisper`'s `data.text` is "hidden by the browser until the verdict", but `api.md` says the server never sends it before the verdict. Only one can be true.
- The sample session has no `glasser` `sponsor.call`, so Glasser shows 0 in sample data.

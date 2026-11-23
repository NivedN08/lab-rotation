# Front end API layer

**The contract is `contract/api.md` (routes and shapes) and `contract/events.md` (events).** Nived owns it. This folder implements it; where the two differ, the contract wins and we change this folder. Things we need from it that it doesn't say yet are listed at the end.

All backend calls live in `client.ts`. Nothing else in the front end touches `/api`. Shapes are in `types.ts`, trap ids and labels in `traps.ts`.

## Functions and routes

| Function | Route |
|---|---|
| `startSession(options?)` | `POST /api/session/start` |
| `getCurrentTask(id)` | `GET /api/session/:id/task` |
| `getTables(id, taskId?)` | `GET /api/session/:id/tables?task=` |
| `getRows(id, table, offset, limit, taskId?)` | `GET /api/session/:id/tables/:table/rows?task=` |
| `getProfile(id, table, taskId?)` | `GET /api/session/:id/tables/:table/profile?task=` |
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

On by default. `?mock=0` calls the real server. `mock.ts` answers every function with the contract's own sample task and tables: `./mock/` holds copies of `contract/mock_session.jsonl` and `contract/mock_task/`, so sample data has the real shape. Re-copy with `sh web/src/api/mock/sync.sh` from the repo root when the contract changes. The copy in `./mock/` is currently Nived's latest 86-event session from his `n1-session` branch (Telem's `topic` and `case` searches, sealed whispers, `panel.transcript`, the dictionary on `task.picked`); the `contract/` folder on `main` still has the older 68-event one until his branch is merged. The mock's SQL (`mockSql.ts`) is a small stand-in, not a real runner: it reads `SELECT` columns or `COUNT/AVG/SUM/MIN/MAX(col) [AS name]` `FROM` one table with an optional `JOIN other USING (col)`, `WHERE col op value [AND ...]`, `GROUP BY`, `ORDER BY` and `LIMIT`. `?mockspeed=10` runs the sample ten times faster.

**The live sample never acts for the learner.** In Your rotation and Judge mode the fake server (`mockLive.ts`) emits `learner.query`, `learner.evidence`, `learner.answer`, `appeal.*` and `ask` events only when the real person does those things (a SQL query, Submit, opening an appeal, asking an agent). Everything else is the lab's own work: Vale's task and brief, Telem's topic-only background, Riley's answer, the panel's whispers, the checks, the verdict, Telem's real case after the verdict, the mastery update. When the person submits, the fake compares their answer with its key and sends a matching verdict: right (verdict and trap both right, `passed`), partly right (one of them right, `failed`, with a score between) or wrong (`failed`, score 0). Whisper words arrive in `panel.transcript` after the verdict. An appeal gets an `appeal.message` from Sam and a ruling that the grade stands. Each agent answers an ask only from what it could see.

- **Judge mode** (`startSession({mode: "judge"})`): one task, `t1`, tier 1, 240 seconds. The start reply lists only that task, and the session ends after its verdict (`session.end`, then `GET /task` returns `{task: null}`).
- **Your rotation** (no body, or `mode: "rotation"`): three tasks at tiers 1, 2 and 3. Task 1 is the contract's sample task. Tasks 2 and 3 are made up for the sample and reuse the same tables, so their answer keys are arbitrary.
- **Time runs out:** if the learner has not answered when the task's seconds are up, the fake answers `cant_tell` for them, and that `learner.answer`'s `why` says so.
- Only the **demo** (`mock-demo`, `mockSession.ts`) plays the contract's recorded session with its scripted learner.

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

We read the fields in bold in `contract/events.md`, and ignore kinds and fields we don't know. The ones the front end acts on: `task.picked` (including `dictionary`, shown in the workspace live and in replays), `verdict` (`taskId`, `result`), `mastery.update`, `panel.whisper`, `panel.transcript`, `appeal.*`, `voice.line` (`file`, or `provider: "browser"` with `lineOf`), `sponsor.call`, `check.result`, `monitor.hit`, `agent.move` (`from`, `place`; places are `door`, `vale_office`, `learner_desk`, `riley_desk`, `shelves`, `terminal`, `panel_table`, `whiteboard`, typed as `Place`).

**Whisper words.** Before the verdict, `panel.whisper` has no `data.text` and `data.sealed` is `true`. Right after the verdict a `panel.transcript` event (from Ines) carries `{taskId, whispers: [{seq, agent, to, text}]}`, and the Panel room shows the transcript from that event. A finished session read from `since=0` has the words filled in, so `visibility.ts` strips them (`withholdWhispers`) from anything that plays a recording, until the verdict event has played; the same step hides `learner.query`'s `data.useful` (it names the columns that matter, so the server holds it back too). The demo player, the sample session and the demo's recorded-event reader all use it, so no screen shows either early.

**Trap labels.** Every screen shows trap labels, never ids. `trapLabel(id)` gives the label for an id, and `labelTraps(text)` replaces ids inside a sentence the backend wrote ("The key says unit_mismatch" becomes "The key says Unit mix-up"). The Panel room uses it for transcript and appeal text.

**Telem's two searches.** Each task has two `search` events, told apart by `data.phase` (`SearchData`): `topic` during the brief (background on the claim only) and `case` right after `panel.transcript`, with Telem walking to the learner's desk (`agent.move` to `learner_desk`). The `case` search holds the real case: `results` (title, `url` as the source, snippet), `trace` and `trap`. `CaseCard` in `web/src/panels/` shows it.

**Sponsor totals.** Live, from `GET /sponsors`. In a replay they are added up from events (`sponsors.ts`) so they follow seek and rewind: BAND messages are `band` calls, Telem searches are `telem` calls with `op: "search"`, monitor hits are `monitor.hit` events, Bruin checks are `check.result` events (each has `passed`; the front end keeps counting these), Runware lines are `runware` calls with `op: "tts"`.

## Still open with the contract

- The sample session has no `glasser` `sponsor.call`, so Glasser shows 0 in sample data.

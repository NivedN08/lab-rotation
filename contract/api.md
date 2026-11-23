# API

The Python server (`lab/server.py`, FastAPI, owned by N1) serves the browser.
Dev: `uv run uvicorn lab.server:app --port 8000`; Vite proxies `/api` to it.
All bodies are JSON. Errors are `{"error": "plain words"}` with a 4xx/5xx code.

Same freeze rule as `events.md`: frozen at 12:00, then only grows, through N1.

**Mock mode.** `LAB_MOCK=1` (or `POST /api/sessions` with `"mock": true`) replays
`contract/mock_session.jsonl` over the event stream at real speed (`LAB_MOCK_SPEED`
multiplies it) and serves the tables in `contract/mock_task/`. Every route below
works in mock mode, so the web streams never wait on the real engine.

**Visibility.** The browser never receives the answer key, the trap of an
unfinished task, panel whisper text before the verdict, or any sponsor key.

## Sessions

### `POST /api/sessions`
Start a session. Calls `lab.session.engine.start_session(mode, learner, mock)`.
```json
{"mode": "judge", "learner": "guest", "mock": false}
```
→ `201`
```json
{"session": "s-7f3a", "mode": "judge", "learner": "guest", "clock_s": 240}
```

### `GET /api/sessions/{id}`
Snapshot for a page reload. Calls `lab.session.engine.snapshot(id)`.
```json
{"session": "s-7f3a", "mode": "judge", "learner": "guest", "task": "t-unit-1-s3",
 "phase": "analysis", "clock_left_s": 171, "last_seq": 41,
 "agents": {"vale": {"place": "vale_office"}, "sam": {"place": "learner_desk"}}}
```
`phase`: `brief`, `context`, `analysis`, `answered`, `conferring`, `verdict`,
`appeal`, `next`, `done`.

### `GET /api/sessions/{id}/events?since=<seq>`
Server-sent events. Each SSE message is `event: lab` and `data: <one event JSON>`
(shape in `events.md`). Starts after `since` (default 0, the whole log), then stays
open. Calls `lab.session.engine.events(id, since)` (a generator).

## The task (public part only)

### `GET /api/sessions/{id}/task`
Calls `lab.session.engine.public_task(id)`.
```json
{"task": "t-unit-1-s3", "claim": "Loyalty members spend more per visit than other customers.",
 "brief": "Marketing wants this on a board slide on Friday. Check it first.",
 "tier": 1,
 "tables": [{"name": "visits", "key": "visit_id", "rows": 300,
             "columns": [{"name": "spend", "type": "DOUBLE", "doc": "Basket total in dollars"}]}],
 "dictionary": "markdown text of the data dictionary"}
```

### `GET /api/sessions/{id}/tables/{table}?limit=50&offset=0`
Rows of one public table. Calls `lab.workspace_sql.table_rows(task, table, limit, offset)`.
```json
{"table": "visits", "columns": ["visit_id", "customer_id", "store_id", "spend"],
 "rows": [["v0001", "c017", "st03", 42.5]], "total": 300}
```

### `GET /api/sessions/{id}/tables/{table}/profile`
Calls `lab.workspace_sql.profile(task, table)`.
```json
{"table": "visits", "columns": [
  {"name": "spend", "type": "DOUBLE", "nulls": 0, "distinct": 287,
   "min": 3.1, "max": 9120.0, "mean": 310.4, "top": [["42.5", 3]],
   "histogram": [{"lo": 0, "hi": 100, "n": 210}]}]}
```
`top` is for text columns, `histogram` for numbers (10 bins).

### `POST /api/sessions/{id}/query`
Read-only SQL over this task's public tables (DuckDB, row cap 500, timeout 3 s).
Calls `lab.workspace_sql.run_query(task, sql)`, then `lab.session.engine.on_query`.
```json
{"sql": "select region, avg(spend) from visits join stores using (store_id) group by 1"}
```
→
```json
{"id": "q4", "ok": true, "columns": ["region", "avg(spend)"], "rows": [["West", 3120.4]],
 "row_count": 4, "truncated": false, "ms": 12, "error": null}
```
A bad query returns `200` with `ok: false` and `error` set (it is still an event).

## Learner actions

### `POST /api/sessions/{id}/evidence`
Calls `lab.session.engine.on_evidence(id, items, action)`.
```json
{"action": "add", "items": [{"type": "column", "table": "visits", "column": "spend"}]}
```
→ `{"evidence": [ ...the full current list... ]}`

### `POST /api/sessions/{id}/answer`
Calls `lab.session.engine.on_answer(id, answer)`. The panel confers, then the
verdict arrives on the event stream.
```json
{"verdict": "fails", "trap": "unit_mismatch",
 "text": "West's spend is in cents. After dividing by 100 members spend the same.",
 "evidence": [{"type": "query", "id": "q4"}], "via": "text"}
```
→ `202 {"accepted": true}`

### `POST /api/sessions/{id}/appeal`
Calls `lab.session.engine.on_appeal(id, text)`.
```json
{"text": "My evidence did cite the West stores, see q4."}
```
→ `202 {"accepted": true, "room": "band" | "local"}`

### `POST /api/sessions/{id}/next`
Ask Vale for the next task (rotation mode). Calls `lab.session.engine.next_task(id)`.
→ `200 {"task": "t-dup-2-s1"}` or `{"task": null}` when the rotation is done.

### `POST /api/sessions/{id}/ask`
"Ask any agent why." Answers only from what that agent saw.
Calls `lab.session.engine.ask(id, agent, text)`.
```json
{"agent": "ines", "text": "Why did I lose the evidence point?"}
```
→ `{"agent": "ines", "text": "...", "seen": [{"type": "check", "id": "..."}]}`

## Learner model

### `GET /api/learners/{learner}/mastery`
Calls `lab.learner.mastery(learner)` (reads Bruin's `bkt_mastery`).
```json
{"learner": "guest", "skills": {"duplicate_rows": 0.22, "unit_mismatch": 0.61,
 "dictionary_flip": 0.15, "confounder": 0.15, "hidden_variable": 0.15, "trust_clean": 0.3},
 "history": [{"task": "t-unit-1-s3", "skill": "unit_mismatch", "before": 0.15, "after": 0.61}]}
```

## Media and side data

### `GET /api/audio/{file}`
An agent's voice line (mp3), made by Runware. Files live in `data/audio/`.

### `GET /api/agents`
The cast, for portraits and names. Calls `lab.session.cast.agents()`.
```json
[{"id": "vale", "name": "Dr. Vale", "role": "Lab head", "portrait": "/api/portraits/vale.png",
  "voice": "runware voice id or null", "color": "#7c5cff"}]
```

### `GET /api/portraits/{file}`
Runware portraits, from `data/portraits/` (falls back to `web/public/portraits/`).

### `GET /api/sponsors?session=<id>`
Sponsor strip totals (also derivable from `sponsor.call` events).
```json
{"band": {"calls": 12, "fallback": 0}, "telem": {"calls": 3, "traces": ["https://..."]},
 "bruin": {"checks": 5, "failed": 1, "runs": 2}, "runware": {"calls": 9, "cost_usd": 0.031},
 "glasser": {"calls": 2, "cost_usd": 0.0}, "teamily": {"calls": 0}}
```

### `GET /api/bench`
Benchmark results (from Bruin's `bench_results`). Owned by N4, served by N1.
```json
{"split": "dev-B", "rows": [{"dimension": "mistake_identification", "system": "panel",
  "macro_f1": 0.0, "record": 71.8}]}
```

### `GET /api/health`
`{"ok": true, "mock": false, "band": "live" | "local", "version": "0.1.0"}`

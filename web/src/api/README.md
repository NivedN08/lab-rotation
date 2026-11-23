# Front end <-> backend routes

All calls live in `client.ts`; nothing else in the front end touches `/api`. Shapes are in `types.ts`.
`mock.ts` answers the same calls with fake data. It is on by default. Add `?mock=0` to the URL to call the real server.
These names are the front end's proposal. Nived: match them, or send your real ones and `client.ts` will change to fit.
Errors: any non-2xx reply, or a JSON body with `{"error": "plain words"}`, is shown to the learner as is.

| Job | Route | Sends | Gets back |
|---|---|---|---|
| Start a session | `POST /api/session/start` | nothing | `{sessionId, tasks: [{id, title, brief, seconds}]}` |
| List tables | `GET /api/session/:id/tables` | nothing | `[{name, about, columns: [{name, type}], rowCount}]` (type: text, int, real or date) |
| Read rows | `GET /api/session/:id/tables/:table/rows?offset=&limit=` | query string | `{rows: [[cell, ...], ...]}` (cell: string, number, boolean or null) |
| New events | `GET /api/session/:id/events?since=N` | `since` = last `next` (0 first) | `{events: [{seq, t, k, text?, data?}], next}`. Polled every second. |
| Run SQL | `POST /api/session/:id/sql` | `{sql}` | `{columns: [name], rows: [[cell]], ms}` or `{error}` |
| Submit answer | `POST /api/session/:id/answer` | `{taskId, verdict: holds\|fails\|cant_tell, trap, evidence: [{kind: row\|column\|cell, source, sql?, row?, column?, value?, label}], note}` | `{accepted}`. The verdict arrives later as an event. |
| Open appeal | `POST /api/session/:id/appeal` | `{taskId, reason}` | `{appealId}` |
| Appeal message | `POST /api/session/:id/appeal/:appealId/message` | `{text}` | `{ok}`. Replies and the ruling arrive as events. |
| Mastery | `GET /api/session/:id/mastery` | nothing | `{traps: [{trap, score 0..1, attempts}]}` |

`row` is 1-based within what the learner saw. For a SQL result, `source` is `"query"` and `sql` holds the query.

// Static replay mode: every file name the app reads, in ONE place. Nived confirms the exact names; change them here only.
//
// Everything lives under one base folder, next to the page. The folder is set by the build setting VITE_STATIC_BASE
// (default "recorded/"). `id` is the recorded session's id (the `session` from demo.json).
//
//   recorded/demo.json                       {session, start, end, speed}, or {session: null}
//   recorded/agents.json                     [{id, name, role, title, reads, portrait}]
//   recorded/<id>/task.json                  {task}
//   recorded/<id>/events.json                [LabEvent], every event from the beginning (or {events: [...]})
//   recorded/<id>/tables.json                [{name, about, columns, rowCount}]
//   recorded/<id>/rows/<table>.json          [[cell, ...], ...] all rows (or {rows}); the front end slices offset and limit
//   recorded/<id>/profile/<table>.json       {table, columns: [ColumnProfile]}
//   recorded/<id>/mastery.json               {traps: [...]}
//   recorded/<id>/sponsors.json              SponsorTotals
//   recorded/bench.json                      {source, rows, lines}, the examiner benchmark (GET /api/bench)
//   recorded/portraits/<agent>.png           each agent's portrait (vale, ines, sam, telem, riley, learner)
//   recorded/audio/<file>                    the voice lines
//
// A task's tables can also be kept per task: when a task id is asked for, `<id>/<task>/tables.json`,
// `<id>/<task>/rows/<table>.json` and `<id>/<task>/profile/<table>.json` are tried first, then the plain names above.

export const STATIC_BASE: string = ((import.meta.env.VITE_STATIC_BASE as string | undefined) ?? "recorded/").replace(/\/?$/, "/");

const dir = (id: string) => `${STATIC_BASE}${encodeURIComponent(id)}/`;
const perTask = (id: string, task: string | undefined, rest: string): string[] => [...(task ? [`${dir(id)}${encodeURIComponent(task)}/${rest}`] : []), `${dir(id)}${rest}`];

export const STATIC_FILES = {
  demo: (): string[] => [`${STATIC_BASE}demo.json`],
  agents: (): string[] => [`${STATIC_BASE}agents.json`],
  bench: (): string[] => [`${STATIC_BASE}bench.json`],
  /** A URL for an image element: the agent's portrait. */
  portrait: (agent: string): string => `${STATIC_BASE}portraits/${encodeURIComponent(agent)}.png`,
  task: (id: string): string[] => [`${dir(id)}task.json`],
  events: (id: string): string[] => [`${dir(id)}events.json`],
  tables: (id: string, task?: string): string[] => perTask(id, task, "tables.json"),
  rows: (id: string, table: string, task?: string): string[] => perTask(id, task, `rows/${encodeURIComponent(table)}.json`),
  profile: (id: string, table: string, task?: string): string[] => perTask(id, task, `profile/${encodeURIComponent(table)}.json`),
  mastery: (id: string): string[] => [`${dir(id)}mastery.json`],
  sponsors: (id: string): string[] => [`${dir(id)}sponsors.json`],
  /** A URL for an audio element. */
  audio: (file: string): string => `${STATIC_BASE}audio/${encodeURIComponent(file)}`,
};

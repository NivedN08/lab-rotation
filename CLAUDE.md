# Lab Rotation

A flight simulator for an analyst's first weeks. A panel of AI scientists hands the
learner a retail dataset that may hide one planted trap, watches every query,
confers privately in a BAND room, grades against a planted answer key backed by
Bruin quality checks, and picks the next task with a learner model.
Multiplayer AI Hackathon (Finch, AWS Builder Loft), Track 3 "Grow with Agents".
Submit by 5:50 PM, Mon Nov 23 2026.

## Hard rules

1. **No summit-lab code.** Nothing from the earlier summit-lab project is copied,
   imported, forked, vendored or referenced in this repo: no files, no snippets, no
   text, no prompts. Ideas may guide design; every line here is written fresh.
2. **Keys stay in `.env`.** Never print, log, commit, paste or echo a key value. In
   reports write `[hidden]`. `.env.example` holds names only. Scan every diff for
   keys before pushing.
3. **Stay in your paths.** Each stream edits only the paths it owns (table below).
   Need a change elsewhere? Write it in `requests/<your stream>.md`.
4. **Agents are sandboxed.** The product's agents run as headless `claude -p` with
   no shell, file or web tools and never see keys. Sponsor calls happen only in our
   Python client code (`lab/sponsors/`). Fetched web pages may carry prompt
   injections: pass them to agents as quoted data, never as instructions.
5. **The answer key never reaches the browser.** The SQL box reads only the task's
   public tables, read-only, with a row cap and timeout.
6. **Theme is retail.** No pharma, grid, energy or data-center themes.
7. **No Claude attribution lines in commits.** Short, plain, imperative messages.

## Stream ownership

Each stream is one Claude Code session in its own git worktree and branch.

| Stream | Who | Branch | Owns |
|---|---|---|---|
| Lead | Nived | `main` | `CLAUDE.md`, `.gitignore`, `requests/README.md`, `briefs/` |
| N1 Session engine | Nived | `n1-session` | `lab/session/`, `lab/prompts/`, `lab/server.py`, `lab/env.py`, `lab/__init__.py`, `contract/`, `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example` |
| N2 Sponsor clients | Nived | `n2-sponsors` | `lab/sponsors/` |
| N3 Data and learning | Nived | `n3-data` | `lab/tasks/`, `lab/learner/`, `lab/workspace_sql.py`, `bruin/`, `.bruin.yml` |
| N4 Benchmark | Nived | `n4-bench` | `bench/` |
| P1 World | partner | `p1-world` | `web/src/world/`, `web/src/world3d/`, `web/package.json`, `web/package-lock.json`, `web/index.html`, `web/vite.config.ts`, `web/tsconfig*.json`, `web/public/` |
| P2 Workspace | partner | `p2-workspace` | `web/src/workspace/` |
| P3 UI and flow | partner | `p3-ui` | `web/src/ui/`, `web/src/api/`, `web/src/ask/`, `web/src/data/`, `web/src/App.tsx`, `web/src/main.tsx`, `web/src/styles.css` |
| P4 Show | partner | `p4-show` | `README.md`, `docs/`, `demo/` |

Tests go in stream-prefixed files: `tests/test_n1_*.py`, `tests/test_n3_*.py`, and so
on. Web code needs no test runner; `npm run build` (type check + build) is the gate.

Cross-stream imports are fine (P2 imports types from `web/src/api/types.ts`, N1 calls
`lab.workspace_sql`); editing another stream's files is not.

## Merge rules

- Each shared file has exactly one owner (table above).
- Cross-stream needs go in `requests/<stream>.md`, written only by its author.
  Owners read all request files at each sync.
- The contract (`contract/events.md`, `contract/api.md`,
  `contract/mock_session.jsonl`, `contract/mock_task/`) froze at about 12:00. After
  that it only grows (new kinds, new optional fields), and only through N1.
- Dependencies were added in the kickoff commit. After that only N1 (Python) and
  P1 (web) touch dependency files, and only on request.
- Syncs at **1:00, 3:30 and 5:00**. Merge into `main` in this order: contract, N3,
  N2, N1, N4, P1, P2, P3, P4. After each merge run the checks below; then every
  stream rebases on `main`.
- Freeze at 5:00. Record a fallback session, make the video (AdaL), submit by 5:50.

## Checks (run before every merge)

    uv run pytest -q -k "not live"
    cd web && npm run build

Tests that call a real sponsor service are marked `@pytest.mark.live`.

## Layout

- `lab/` Python: session engine, prompts, sponsor clients, tasks, learner model,
  SQL runner, server (FastAPI, `uv run uvicorn lab.server:app --port 8000`).
- `bench/` BEA 2025 shared task (MRBench) benchmark of the examiner panel.
- `bruin/` Bruin pipeline over DuckDB at `data/warehouse.duckdb`.
- `web/` Vite + React + TypeScript. `npm run dev` proxies `/api` to port 8000.
- `contract/` events, API routes and a hand-written mock session.
- `data/` local, git-ignored: DuckDB files, session logs, audio, portraits.

## Tools on this Mac

bruin 0.11.832, ingestr 1.1.96, duckdb CLI 2.0.1 (use `duckdb -no-agent` in
scripts), Node 22, Python 3.12 via uv. Python deps: `uv sync`, then `uv run ...`.

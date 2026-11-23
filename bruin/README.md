# Bruin pipeline

Owned by N3. DuckDB at `data/warehouse.duckdb` (connection `duckdb-default` in `../.bruin.yml`).

## Bruin in Lab Rotation

Everything runs locally on one DuckDB file; nothing goes to the cloud.

- **The five trap checks** (`bruin/assets/task/quality.sql`). Every task is checked by a real
  `bruin run`: the five checks are Bruin custom checks, and exactly the planted trap's check
  fails (none on a clean task). Ines, the grader, shows that failing check as her evidence.
  `lab/tasks/bruin_run.py` stages the task's public tables (`bruin/assets/task/*.sql`) and
  runs `bruin run --tag task`. `lab/tasks/checks.py` runs it with `run_checks(task, bruin=True)`,
  and a test keeps Bruin and the Python checks in agreement on every skill.
- **ingestr loads** (`lab/learner/refresh.py`). Recorded sessions and N4's benchmark
  results are loaded into the warehouse as `raw.session_events` and `raw.bench_results`.
- **The learning assets** (`bruin/assets/learn/*.sql`):
  - `learn.session_events`: every session event.
  - `learn.skill_attempts`: one row per graded task.
  - `learn.session_scores`: one row per session.
  - `learn.bench_results`: N4's benchmark results.

  Column checks such as `not_null` and `accepted_values` guard them.
- **BKT as a Python asset** (`bruin/assets/learn/bkt_mastery.py`, `requirements.txt`).
  `learn.bkt_mastery` replays the learner model (`lab/learner/bkt.py`, Bayesian knowledge
  tracing) over `learn.skill_attempts`, giving one mastery score per player and trap.
- **A refresh after every session** (`lab/learner/refresh.py`, `refresh()`). The session
  engine calls it before `session.end`. It flattens the sessions, runs ingestr, then runs
  `bruin run --tag learning`. The floor logs it as the Bruin call "refreshed the learner model
  (learn.bkt_mastery)". Measured: 1.8 s warm, 7.7 s on a cold first run.
- **The demo** (`bruin/demo.sh`). One command, about 2 s, on the current warehouse:
  1. `bruin query` answers "which trap do players miss most?" (attempts, misses and miss rate
     by trap).
  2. `bruin lineage` traces `learn.bkt_mastery` back to the session events.
  3. `bruin docs` writes the whole pipeline (assets, checks, lineage) to one HTML page.

  Run it with:

      bash bruin/demo.sh          # add --open to open the docs page

Run from the repo root:

    bruin validate bruin
    bruin run bruin                      # everything, on the committed samples in bruin/sample/
    bruin run --tag task bruin           # the five trap checks on one staged task
    bruin run --tag learning bruin       # session tables and BKT mastery

## Task checks (`assets/task/`, tag `task`)

`lab.tasks.bruin_run.run(task)` stages a task's public CSVs into `data/bruin/task/` (every
column the assets read, empty where the task lacks it, plus `meta.csv` with the member code the
public dictionary states) and runs `bruin run --tag task --var stage=...`. The staged tables are
`task.visits`, `task.customers`, `task.stores`, `task.loyalty_accounts`, `task.meta` and
`task.flags` (the loyalty flag wherever the task keeps it). `task.quality` carries the five
trap checks as custom checks, all on one asset so a failing check never skips the others:

| check | trap | fails when |
|---|---|---|
| `duplicate_rows.visits_unique_measured` | duplicate_rows | two visits repeat store, date, items and spend |
| `unit_mismatch.spend_range_by_region` | unit_mismatch | a region's median spend is over 3x from the median region |
| `dictionary_flip.flag_matches_points` | dictionary_flip | under half the rows the dictionary calls members have points |
| `confounder.member_share_by_pos` | confounder | a POS version shifts median spend over 1.3x and the loyalty mix over 30 points |
| `hidden_variable.flag_in_main_tables` | hidden_variable | loyalty_flag is not in visits or customers |

The same checks run in Python (`lab.tasks.checks.run_checks`) for Ines's `check.result` detail
and rows; a test keeps the two in agreement. `run_checks(task, bruin=True)` adds `bruinRun`.

## Learning (`assets/learn/`, tag `learning`)

`lab.learner.refresh.refresh()` flattens `data/sessions/*.jsonl` and copies N4's
`data/bench/results.csv` into `data/bruin/learn/`, loads both into `raw.*` with ingestr, then runs
`bruin run --tag learning --var learn=...`:

- `learn.session_events`: every event, one row each, learner carried onto each row.
- `learn.skill_attempts`: one row per graded task (skill = its true trap, correct = score >= 0.6).
- `learn.session_scores`: per session: tasks, mean score, beat Riley, queries, failed checks.
- `learn.bench_results`: MRBench results from N4.
- `learn.bkt_mastery` (Python): `lab.learner.bkt` replayed over skill_attempts.

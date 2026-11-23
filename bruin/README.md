# Bruin pipeline

Owned by N3. DuckDB at `data/warehouse.duckdb` (connection `duckdb-default` in `../.bruin.yml`).
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

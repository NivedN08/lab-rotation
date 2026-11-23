# Bench: the examiner panel on the BEA 2025 shared task (MRBench)

We score Lab Rotation's examiner panel on the BEA 2025 shared task on pedagogical
ability assessment of AI tutors. Given a math tutoring dialogue in which the student
made a mistake, and one candidate next tutor turn, label four dimensions as Yes /
To some extent / No: mistake identification (MI), mistake location (ML), providing
guidance (PG) and actionability (AC). Metric: 3-class macro-F1 per dimension.

Records (best team on the official **test** leaderboard, exact macro-F1): MI 71.8,
ML 59.8, PG 58.3, AC 70.9 (`Final_Leaderboards/*_main.pdf` in the task repository).

## Data and splits

`github.com/kaushal0494/UnifyingAITutorEvaluation`, folder `BEA_Shared_Task_2025_Datasets`,
downloaded to `data/bench/raw/` (git-ignored). Dev: 300 dialogues, 2,476 labelled
replies. Test: 191 dialogues, 1,547 replies without labels (scored on CodaBench).

Dev is split by dialogue into halves **dev-A** and **dev-B** (150 each; seeded shuffle,
seed 2025, `bench/data.py`). The guide is tuned on dev-A only. dev-B is read only to
confirm. Every number below names its split. Dev numbers are not test numbers.

## Systems

All agents are headless Claude Code on the subscription, with no tools:
`claude -p --tools "" --strict-mcp-config --no-session-persistence --setting-sources ""
--output-format json --model <m> --system-prompt <guide>`, item on stdin (`bench/llm.py`).
One call grades all replies of one dialogue (about 8). Replies get neutral ids R1..Rn in
a seeded order (tutor names such as "Expert" would leak). Calls are cached in
`data/bench/cache/`, so runs resume.

- **single**: one reader with the grading guide (`bench/guide.md`).
- **panel**: two blind readers with the same guide (reader 2 sees the replies in reverse
  order) and a referee (`bench/referee.md`) who settles only the labels they disagree on,
  seeing both readers' labels and notes (`bench/judge.py`).

## Guide tuning

`bench/tune.py` runs summit-lab's improvement loop pieces (`lab/autoloop.py`): typed
`edit_section` moves on one section of the guide (or a bundle of two), a seed move first
(`bench/seed_moves.json`, from the task's public annotator guideline), then moves from a
proposer agent (`bench/proposer.md`) that sees the guide's dev-A scores, confusion counts
and wrong examples. Each move is graded on the same dev-A dialogues and paired cell by
cell with the incumbent (`autoloop.paired`). Accepted only when the gain in mean macro-F1
is at least T (the larger of 1 point and the A/A noise of the starting guide graded
twice), and again above 0 on a second replicate. Every step goes to a hash-chained ledger
(`lab/ledger.py`) at `data/bench/tune/ledger.jsonl`. The result is `bench/guide_tuned.md`.

## Commands

    uv run python -m bench.run single --split dev-A --n 50 --model opus --name single-opus-start
    uv run python -m bench.run panel  --split dev-A --n 50 --model opus --name panel-opus-start
    uv run python -m bench.tune --n 50 --model opus --max-moves 5 --jobs 3
    uv run python -m bench.run single --split dev-B --n 50 --guide bench/guide_tuned.md --name single-opus-tuned
    uv run python -m bench.submit --name <system run on --split test>

Scores go to `data/bench/results.csv` (split, dimension, system, macro_f1, n, record),
which Bruin loads as `bench_results`.

## Results

See the table below (filled in from `data/bench/results.csv` as runs finish).

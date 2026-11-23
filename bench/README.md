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

## Test set and CodaBench upload (manual)

The test run is the single reader with the tuned guide (`single-opus-tuned`): it matches
the panel on dev-B at about a third of the calls.

    uv run python -m bench.run single --split test --guide bench/guide_tuned.md --name single-opus-tuned --jobs 4
    uv run python -m bench.submit --name single-opus-tuned

Run on 23 Nov 2026, 14:03-14:16: 191 calls, 0 errors, 1,547 replies labelled, 12 min 42 s
at 4 parallel calls, all zips written with 0 fallback labels.

This writes one zip per track, each `predictions.json` inside `predictions.json.zip`: the
test file with an `annotation` holding that track's label added to every tutor response
(the organisers' sample format; `bench/submit.py` checks every file against the test file
before zipping). Test rows go into `results.csv` with `macro_f1` blank.

| track | CodaBench competition | file to upload |
|---|---|---|
| 1 Mistake Identification | https://www.codabench.org/competitions/7195/ | `data/bench/codabench/single-opus-tuned/track1_mistake_identification/predictions.json.zip` |
| 2 Mistake Location | https://www.codabench.org/competitions/7200/ | `data/bench/codabench/single-opus-tuned/track2_mistake_location/predictions.json.zip` |
| 3 Providing Guidance | https://www.codabench.org/competitions/7202/ | `data/bench/codabench/single-opus-tuned/track3_providing_guidance/predictions.json.zip` |
| 4 Actionability | https://www.codabench.org/competitions/7203/ | `data/bench/codabench/single-opus-tuned/track4_actionability/predictions.json.zip` |

Steps, per track:

1. Sign in at codabench.org (one account submits for the whole team, per the organisers).
2. Open the track's competition page and register for it if asked.
3. Open "Get Started" and read the "Evaluation and Submission File" tab; check it still asks
   for a zipped `predictions.json` in this shape.
4. Look at the phases. If a phase is open today, go to "My Submissions", pick that phase,
   upload the zip, and wait until the submission shows Finished. If every phase has ended,
   the competition no longer scores uploads: stop there.
5. Read exact macro-F1 from the results, then record all four at once:
   `uv run python -m bench.run record-test --name single-opus-tuned --scores MI=..,ML=..,PG=..,AC=..`

Whether it still accepts uploads is unknown. The official test phase closed on 24 April
2025 and the final leaderboards are published (sig-edu.org/sharedtask/2025). The task
allowed 5 submissions per team per track. CodaBench answers scripts with a bot check, so
the phase list could not be read from here. Check step 4 by hand. If nothing is open, the
honest claim stays the dev-B result.

## Demo lines

Exact on-screen text (three lines; every number names its split):

    MRBench (BEA 2025), held-out dev data: our tuned grading guide adds +5.1 macro-F1 (95% CI +2.1 to +8.0).
    Dev, tuned guide: MI 66.4 · ML 57.1 · PG 59.7 · AC 69.8. Best teams on the test set: 71.8 · 59.8 · 58.3 · 70.9.
    Two readers plus a referee score the same as one reader (+0.5, CI -0.8 to +1.8). Test set: score pending on CodaBench.

If CodaBench turns out to be closed, end line 3 with "Test set: not scored (competition closed)."
If it returns scores, replace that clause with "Test (CodaBench): MI .. · ML .. · PG .. · AC ..".

## Results

3-class macro-F1 (%), model `claude-opus-5-5` for every agent, first 50 dialogues of each
half (`uv run python -m bench.table`). dev-A rows with the tuned guide are on the very
dialogues it was tuned on, so they flatter it; **dev-B is the held-out check**. The records
are test-set scores from other teams' systems; our dev numbers are not test numbers.

| split | system | MI | ML | PG | AC | replies |
|---|---|---|---|---|---|---|
| dev-A | single, starting guide | 62.6 | 55.7 | 57.9 | 61.4 | 412 |
| dev-A | panel, starting guide | 63.8 | 58.2 | 57.9 | 64.5 | 412 |
| dev-A (tuning set) | single, tuned guide | 71.8 | 64.5 | 64.8 | 74.7 | 412 |
| **dev-B** | single, starting guide | 58.2 | 57.9 | 56.6 | 59.9 | 411 |
| **dev-B** | single, tuned guide | 66.4 | 57.1 | 59.7 | 69.8 | 411 |
| **dev-B** | panel, starting guide | 59.0 | 58.0 | 56.3 | 60.3 | 411 |
| **dev-B** | panel, tuned guide | 66.5 | 57.3 | 60.6 | 70.6 | 411 |
| test | record (best team per track) | 71.8 | 59.8 | 58.3 | 70.9 | 1,547 |

Paired differences on dev-B with a 95% bootstrap interval over dialogues
(`uv run python -m bench.compare --split dev-B --a <system> --b <system>`):

| comparison (dev-B) | MI | ML | PG | AC | mean of 4 |
|---|---|---|---|---|---|
| tuned minus starting guide (single) | +8.2 [+3.1, +13.9] | -0.8 [-7.4, +5.1] | +3.1 [-4.0, +10.0] | +9.9 [+4.3, +15.4] | **+5.1 [+2.1, +8.0]** |
| panel minus single (tuned guide) | +0.1 [-2.0, +2.6] | +0.2 [-2.8, +3.6] | +0.9 [-0.5, +2.4] | +0.7 [-1.3, +2.8] | +0.5 [-0.8, +1.8] |
| panel minus single (starting guide) | +0.8 [-1.7, +3.3] | +0.1 [-2.6, +2.8] | -0.3 [-2.5, +1.9] | +0.4 [-1.4, +2.0] | +0.2 [-1.0, +1.4] |

What it shows:

- **Tuning transfers.** The tuned guide gains 5.1 points of mean macro-F1 on held-out
  dev-B (interval clear of zero), mostly on MI (+8.2) and AC (+9.9). On dev-A's tuning
  dialogues it gained 9.5, so about half the tuning-set gain carries over. ML does not
  improve on dev-B (-0.8, interval spans zero): the ML rewrite fit dev-A only.
- **The panel buys almost nothing here.** Two readers and a referee are within a point of
  one reader (+0.5, interval spans zero) at about 2.9 times the calls. The readers agree on
  88-90% of labels, so the referee rarely changes the outcome.
- **Against the records** (test set, not comparable): on dev-B the tuned guide reaches
  66.4 / 57.3 / 60.6 / 70.6 (panel). PG is above the PG record of 58.3; MI, ML and AC are
  below theirs. A test-set run would be needed before claiming any of this on test.
- The starting guide's main error was answering "To some extent" where annotators said
  "Yes" (on dev-A MI, 102 of 309 human Yes); the seed move from the annotator guideline
  fixed most of that.

Tuning run (`bench/tune_ledger.jsonl`): starting guide 59.4 on dev-A (A/A noise 0.22, so
T = 1.0). Kept: the seed move (+6.5, replicate +5.6), an MI + ML rewrite (+1.3, +0.4), a
PG rewrite (+1.75, +2.2). Rejected: a second "How to decide" rewrite (+0.07) and a PG + AC
bundle (-2.1). Five moves, about 450 calls.

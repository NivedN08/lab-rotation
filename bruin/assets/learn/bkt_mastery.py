""" @bruin
name: learn.bkt_mastery
type: python
tags: [learning]
description: Bayesian Knowledge Tracing per learner and skill, replayed over learn.skill_attempts with lab.learner.bkt (the same code the live session uses).

depends:
  - learn.skill_attempts

@bruin """
import pathlib
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from lab.learner.bkt import SKILLS, trace  # noqa: E402

con = duckdb.connect(str(ROOT / "data" / "warehouse.duckdb"))
rows = con.execute("""SELECT coalesce(learner, 'anon'), skill, correct FROM learn.skill_attempts
                      ORDER BY session_id, seq""").fetchall()
by: dict[str, list] = {}
for learner, skill, correct in rows:
    by.setdefault(learner, []).append({"skill": skill, "correct": bool(correct)})
out = []
for learner, attempts in sorted(by.items()):
    st = trace(attempts)
    out += [(learner, s, round(st[s]["score"], 4), st[s]["attempts"], st[s]["correct"]) for s in SKILLS]
con.execute("""CREATE OR REPLACE TABLE learn.bkt_mastery
               (learner VARCHAR, trap VARCHAR, score DOUBLE, attempts BIGINT, correct BIGINT)""")
if out:
    con.executemany("INSERT INTO learn.bkt_mastery VALUES (?, ?, ?, ?, ?)", out)
con.close()
print(f"bkt_mastery: {len(by)} learners, {len(out)} rows")

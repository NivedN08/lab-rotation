/* @bruin
name: learn.skill_attempts
type: duckdb.sql
tags: [learning]
description: One row per graded task - the learner, the skill it tested (its true trap, or none) and whether the score counts as correct (0.6 or more).

depends:
  - learn.session_events

materialization:
  type: table

columns:
  - name: skill
    type: varchar
    checks:
      - name: not_null
      - name: accepted_values
        value: [duplicate_rows, unit_mismatch, dictionary_flip, confounder, hidden_variable, none]
  - name: score
    type: double
    checks:
      - name: non_negative

@bruin */

WITH picked AS (
    SELECT session_id, task, any_value(tier) AS tier FROM learn.session_events
    WHERE k = 'task.picked' GROUP BY session_id, task),
ended AS (
    SELECT * FROM learn.session_events WHERE k = 'task.end' AND trap IS NOT NULL)
SELECT e.learner, e.session_id, e.task, e.trap AS skill, p.tier, e.score, e.score >= 0.6 AS correct,
       e.beat_rival, e.mode, e.t, e.seq
FROM ended e LEFT JOIN picked p USING (session_id, task)
ORDER BY e.session_id, e.seq

/* @bruin
name: learn.session_scores
type: duckdb.sql
tags: [learning]
description: One row per session - learner, mode, tasks graded, mean score and how often the learner beat Riley.

depends:
  - learn.session_events

materialization:
  type: table

columns:
  - name: session_id
    type: varchar
    checks:
      - name: not_null
      - name: unique

@bruin */

SELECT session_id, any_value(learner) AS learner, any_value(mode) AS mode,
       count(*) FILTER (WHERE k = 'task.end') AS tasks,
       round(avg(score) FILTER (WHERE k = 'task.end'), 3) AS mean_score,
       count(*) FILTER (WHERE k = 'task.end' AND beat_rival) AS beat_rival,
       count(*) FILTER (WHERE k = 'learner.query') AS queries,
       count(*) FILTER (WHERE k = 'check.result' AND NOT passed) AS checks_failed,
       max(t) AS seconds
FROM learn.session_events
GROUP BY session_id

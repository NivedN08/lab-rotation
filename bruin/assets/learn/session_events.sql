/* @bruin
name: learn.session_events
type: duckdb.sql
tags: [learning]
description: Every recorded session event (data/sessions/*.jsonl), flattened by lab.learner.refresh, the learner carried onto each row.

materialization:
  type: table

columns:
  - name: session_id
    type: varchar
    checks:
      - name: not_null
  - name: k
    type: varchar
    checks:
      - name: not_null

@bruin */

SELECT * FROM read_csv('{{ var.learn }}/session_events.csv', header = true, columns = {
    'session_id': 'VARCHAR', 'seq': 'BIGINT', 't': 'DOUBLE', 'k': 'VARCHAR', 'agent': 'VARCHAR',
    'task': 'VARCHAR', 'learner': 'VARCHAR', 'mode': 'VARCHAR', 'trap': 'VARCHAR', 'tier': 'BIGINT',
    'score': 'DOUBLE', 'beat_rival': 'BOOLEAN', 'verdict': 'VARCHAR', 'passed': 'BOOLEAN', 'data': 'VARCHAR'})

/* @bruin
name: task.visits
type: duckdb.sql
tags: [task]
description: The current task's visits, staged from its public CSV by lab.tasks.bruin_run.

materialization:
  type: table

columns:
  - name: visit_id
    type: varchar
    checks:
      - name: not_null
      - name: unique
  - name: spend
    type: double
    checks:
      - name: not_null


@bruin */

SELECT * FROM read_csv('{{ var.stage }}/visits.csv', header = true, columns = {
    'visit_id': 'VARCHAR', 'customer_id': 'VARCHAR', 'store_id': 'VARCHAR', 'visit_date': 'DATE',
    'items': 'BIGINT', 'spend': 'DOUBLE', 'points_earned': 'BIGINT'})

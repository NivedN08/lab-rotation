/* @bruin
name: learn.bench_results
type: duckdb.sql
tags: [learning]
description: The examiner panel's MRBench results (N4 writes data/bench/results.csv; lab.learner.refresh stages it).

materialization:
  type: table

columns:
  - name: system
    type: varchar
    checks:
      - name: not_null
  - name: macro_f1
    type: double
    checks:
      - name: non_negative

@bruin */

SELECT * FROM read_csv('{{ var.learn }}/bench.csv', header = true, columns = {
    'split': 'VARCHAR', 'dimension': 'VARCHAR', 'system': 'VARCHAR', 'macro_f1': 'DOUBLE', 'n': 'BIGINT',
    'record': 'VARCHAR'})

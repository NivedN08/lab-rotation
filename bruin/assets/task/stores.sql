/* @bruin
name: task.stores
type: duckdb.sql
tags: [task]
description: The current task's stores (empty when the task has no stores table).

materialization:
  type: table


@bruin */

SELECT * FROM read_csv('{{ var.stage }}/stores.csv', header = true, columns = {
    'store_id': 'VARCHAR', 'region': 'VARCHAR', 'pos_version': 'VARCHAR', 'opened': 'BIGINT'})

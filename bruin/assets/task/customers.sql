/* @bruin
name: task.customers
type: duckdb.sql
tags: [task]
description: The current task's customers. loyalty_flag and points_balance are empty when the task keeps them elsewhere.

materialization:
  type: table

columns:
  - name: customer_id
    type: varchar
    checks:
      - name: not_null
      - name: unique

@bruin */

SELECT * FROM read_csv('{{ var.stage }}/customers.csv', header = true, columns = {
    'customer_id': 'VARCHAR', 'loyalty_flag': 'BIGINT', 'points_balance': 'BIGINT', 'card_id': 'VARCHAR',
    'joined': 'DATE', 'home_store': 'VARCHAR'})

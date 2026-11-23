/* @bruin
name: task.loyalty_accounts
type: duckdb.sql
tags: [task]
description: The current task's loyalty accounts table, when it has one (else empty).

materialization:
  type: table

@bruin */

SELECT * FROM read_csv('{{ var.stage }}/loyalty_accounts.csv', header = true, columns = {
    'customer_id': 'VARCHAR', 'card_id': 'VARCHAR', 'loyalty_flag': 'BIGINT', 'points_balance': 'BIGINT',
    'enrolled': 'DATE'})

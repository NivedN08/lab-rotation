/* @bruin
name: task.flags
type: duckdb.sql
tags: [task]
description: customer_id, loyalty_flag and account points, wherever the task keeps the flag (customers, or loyalty_accounts by customer or card).

depends:
  - task.visits
  - task.customers
  - task.loyalty_accounts
  - task.stores
  - task.meta

materialization:
  type: table


@bruin */

SELECT customer_id, loyalty_flag, points_balance AS points FROM task.customers WHERE loyalty_flag IS NOT NULL
UNION ALL
SELECT c.customer_id, a.loyalty_flag, a.points_balance AS points
FROM task.loyalty_accounts a JOIN task.customers c
  ON a.customer_id = c.customer_id OR a.card_id = c.card_id

/* @bruin
name: task.meta
type: duckdb.sql
tags: [task]
description: One row about the current task - the member code its data dictionary states and the table holding loyalty_flag.

materialization:
  type: table


@bruin */

SELECT * FROM read_csv('{{ var.stage }}/meta.csv', header = true, columns = {
    'stated_member_code': 'BIGINT', 'flag_table': 'VARCHAR', 'tables': 'VARCHAR'})

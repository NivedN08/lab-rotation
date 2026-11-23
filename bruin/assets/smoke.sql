/* @bruin
name: lab.smoke
type: duckdb.sql
description: Tiny asset that proves Bruin, the DuckDB CLI and the Python package share one file format.

materialization:
  type: table

columns:
  - name: store_id
    type: varchar
    checks:
      - name: not_null
      - name: unique
  - name: spend
    type: double
    checks:
      - name: positive

@bruin */

SELECT 'st01' AS store_id, 42.5 AS spend
UNION ALL
SELECT 'st02' AS store_id, 37.1 AS spend

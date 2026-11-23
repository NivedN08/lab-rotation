/* @bruin
name: task.quality
type: duckdb.sql
tags: [task]
description: |
  Row counts of the staged task tables. Its custom checks are the five trap checks, one per
  trap; they all sit here so that one failing check never stops the others from running.
  The same checks run in Python in lab/tasks/checks.py (Ines's evidence); a test keeps them equal.

depends:
  - task.visits
  - task.customers
  - task.loyalty_accounts
  - task.stores
  - task.meta
  - task.flags

materialization:
  type: table

custom_checks:
  - name: duplicate_rows.visits_unique_measured
    description: No two visits repeat store, date, items and spend to the cent.
    query: |
      SELECT count(*) FROM (
        SELECT store_id, visit_date, items, spend FROM task.visits
        GROUP BY store_id, visit_date, items, spend HAVING count(*) > 1)
    value: 0
  - name: unit_mismatch.spend_range_by_region
    description: Every region's median spend sits within 3x of the median region (no region in cents).
    query: |
      WITH r AS (SELECT s.region, median(v.spend) AS med
                 FROM task.visits v JOIN task.stores s USING (store_id) GROUP BY s.region),
           ref AS (SELECT median(med) AS m FROM r)
      SELECT count(*) FROM r, ref WHERE abs(ln(r.med / ref.m)) > ln(3)
    value: 0
  - name: dictionary_flip.flag_matches_points
    description: Rows the data dictionary calls members mostly have loyalty points.
    query: |
      WITH m AS (SELECT stated_member_code AS code FROM task.meta),
           acct AS (SELECT count(points) AS n, avg((points > 0)::INT) AS share
                    FROM task.flags, m WHERE loyalty_flag = m.code),
           vis AS (SELECT count(v.points_earned) AS n, avg((v.points_earned > 0)::INT) AS share
                   FROM task.visits v JOIN task.flags f USING (customer_id), m WHERE f.loyalty_flag = m.code)
      SELECT count(*) FROM acct, vis
      WHERE CASE WHEN acct.n > 0 THEN acct.share WHEN vis.n > 0 THEN vis.share ELSE 1 END < 0.5
    value: 0
  - name: confounder.member_share_by_pos
    description: No POS version shifts both median spend (over 1.3x) and the loyalty mix (over 30 points).
    query: |
      WITH g AS (SELECT s.pos_version, avg(f.loyalty_flag) AS share, median(v.spend) AS med
                 FROM task.visits v JOIN task.stores s USING (store_id) JOIN task.flags f USING (customer_id)
                 GROUP BY s.pos_version)
      SELECT count(*) FROM (SELECT max(share) - min(share) AS gap, max(med) / min(med) AS ratio, count(*) AS n FROM g)
      WHERE n >= 2 AND gap > 0.3 AND ratio > 1.3
    value: 0
  - name: hidden_variable.flag_in_main_tables
    description: The claim's loyalty flag sits in visits or customers.
    query: SELECT count(*) FROM task.meta WHERE flag_table IS NULL OR flag_table NOT IN ('visits', 'customers')
    value: 0

@bruin */

SELECT 'visits' AS tbl, count(*) AS n FROM task.visits
UNION ALL SELECT 'customers', count(*) FROM task.customers
UNION ALL SELECT 'stores', count(*) FROM task.stores
UNION ALL SELECT 'loyalty_accounts', count(*) FROM task.loyalty_accounts

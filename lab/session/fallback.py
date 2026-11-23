"""Built-in stand-ins used when N3's task bank, checks or learner model are not there.

The stub bank holds one task: `contract/mock_task/` with its sealed key (West's spend is
in cents). Hint ladders and recorded Telem cases cover every trap, so a session can run
on any bank task even when a sponsor or the bank leaves them out.
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
MOCK_DIR = ROOT / "contract" / "mock_task"
STUB_ID = "stub-unit-1"

STUB_KEY = {
    "trap": "unit_mismatch",
    "verdict": "fails",
    "columns": ["spend", "region", "loyalty_member"],
    "careful": {"verdict": "fails", "trap": "unit_mismatch",
                "note": "West spend is in cents (max 5600 vs about 74 elsewhere). With West divided by 100, "
                        "members average 37.05 and others 35.00: not 2.4x."},
    "careless": {"verdict": "holds", "trap": "none",
                 "note": "Members average 1067 vs 441 for others. That's 2.4x. Claim holds."},
    # N3's shape: the careless headline number and the careful one for the same group.
    "naive": {"value": 1067, "unit": "USD per visit", "label": "members' average spend per visit, before the fix",
              "group": "members", "fixed": 37.05},
    "checks": [
        {"check": "duplicate_rows.unique_visit", "trap": "duplicate_rows",
         "sql": "select visit_id, count(*) as n from visits group by 1 having count(*) > 1 order by 1 limit 5",
         "pass": "visit_id is unique", "fail": "some visit ids appear more than once"},
        {"check": "dictionary_flip.loyalty_flag_values", "trap": "dictionary_flip",
         "sql": "select customer_id, loyalty_member from customers where loyalty_member not in (0, 1) limit 5",
         "pass": "loyalty_member holds only 0 and 1, as the dictionary says",
         "fail": "loyalty_member holds values the dictionary does not describe"},
        {"check": "confounder.pos_version_balance", "trap": "confounder",
         "sql": "select pos_version, round(100 * avg(loyalty_member)) as member_pct from visits "
                "join stores using (store_id) join customers using (customer_id) group by 1 "
                "having abs(avg(loyalty_member) - (select avg(loyalty_member) from visits "
                "join customers using (customer_id))) > 0.15 order by 1",
         "pass": "members' share of visits is similar on every point-of-sale version",
         "fail": "members' share of visits differs a lot between point-of-sale versions"},
        {"check": "hidden_variable.joins_complete", "trap": "hidden_variable",
         "sql": "select v.visit_id from visits v left join customers c on c.customer_id = v.customer_id "
                "left join stores s on s.store_id = v.store_id "
                "where c.customer_id is null or s.store_id is null limit 5",
         "pass": "every visit joins to a customer and a store",
         "fail": "some visits join to no customer or no store"},
        {"check": "unit_mismatch.spend_range_by_region", "trap": "unit_mismatch",
         "sql": "select visit_id, store_id, spend from visits join stores using (store_id) "
                "where spend > 20 * (select median(spend) from visits) order by spend desc limit 5",
         "pass": "every region's spend is in the same range",
         "fail": "one region's spend is about a hundred times the others (West runs 792 to 5600; "
                 "every other region runs 4 to 74)"},
    ],
}

HINTS = {
    "duplicate_rows": ["Does every row stand for a different visit?",
                       "Count the rows per visit id, or per customer, store and day.",
                       "Some visits appear twice with the same values: count them once."],
    "unit_mismatch": ["Is every row of spend in the same unit? What does spend look like store by store?",
                      "Compare the range of spend across regions.",
                      "Look at the largest spend in each region: one is about a hundred times the others."],
    "dictionary_flip": ["Does the data dictionary agree with what the data shows?",
                        "Check how the flag lines up with the columns that should go with it.",
                        "Read the dictionary's line for the flag again, then compare it with the data."],
    "confounder": ["Is something else different between the two groups?",
                   "Look at how the groups spread across stores and point-of-sale versions.",
                   "Compare the groups within one point-of-sale version at a time."],
    "hidden_variable": ["Is everything you need in this one table?",
                        "Look at the other tables: is there a column that changes the picture?",
                        "Join the second table and compare the groups again."],
    "none": ["What would you expect to see if something were wrong with this data?",
             "Check the usual suspects: repeats, units, the dictionary, mix of stores.",
             "If every check comes back clean, the claim may simply hold."],
}

CASES = {
    "duplicate_rows": {"query": "retail transactions counted twice after a system migration",
                       "title": "A retailer found sales double-counted after a point-of-sale migration",
                       "snippet": "Duplicate transaction records inflated reported sales until a reconciliation."},
    "unit_mismatch": {"query": "retail sales data reported in cents instead of dollars restated",
                      "title": "A chain restated regional sales after an export unit bug",
                      "snippet": "One region's export switched to minor units, so its sales looked 100x larger."},
    "dictionary_flip": {"query": "survey flag coded backwards data dictionary error",
                        "title": "A coding flip in a flag reversed a study's headline finding",
                        "snippet": "A yes/no field was coded opposite to its documentation."},
    "confounder": {"query": "loyalty program spend confounded by store mix",
                   "title": "Loyalty members looked like big spenders because of where they shop",
                   "snippet": "Members clustered in larger-format stores; within a store the gap shrank."},
    "hidden_variable": {"query": "sales analysis missed a variable in another table",
                        "title": "A promotion table explained a sales jump the main table could not",
                        "snippet": "The deciding factor sat in a table the analysts never joined."},
    "none": {"query": "retail analysts checked a sales result and it held up",
             "title": "A retailer ran its checks on a surprising sales result and shipped it unchanged",
             "snippet": "Every check came back clean, so the team trusted the number instead of second-guessing it."},
}

# Telem's pre-answer background when the search is down: the same for every claim.
TOPIC = {"title": "Checking a retail claim before it goes to the board",
         "snippet": "Analysts trace a headline number back to the rows behind it, read how each column was "
                    "recorded, and compare like with like before they repeat it."}


def case_for(trap: str) -> dict:
    """A recorded Telem result for one kind of trap, or for trusting a clean result (labelled cached)."""
    c = CASES.get(trap) or CASES["none"]
    return {"query": c["query"], "cached": True, "trace": "",
            "results": [{"title": c["title"], "url": "", "snippet": c["snippet"]}]}


def topic_for(query: str) -> dict:
    """Recorded background for Telem's pre-answer search (labelled cached); claim-independent."""
    return {"query": query, "cached": True, "trace": "", "results": [{"title": TOPIC["title"], "url": "",
                                                                         "snippet": TOPIC["snippet"]}]}


def stub_task(bank_id: str = STUB_ID) -> dict:
    public = json.loads((MOCK_DIR / "task.json").read_text())
    return {"id": bank_id, "public": public, "dir": str(MOCK_DIR), "key": STUB_KEY}

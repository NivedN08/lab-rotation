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
    "checks": [
        {"check": "duplicate_rows.unique_visit", "trap": "duplicate_rows",
         "sql": "select visit_id, count(*) as n from visits group by 1 having count(*) > 1 order by 1 limit 5",
         "pass": "visit_id is unique", "fail": "some visit ids appear more than once"},
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
}


def case_for(trap: str) -> dict:
    """A recorded Telem result for one kind of trap (labelled cached)."""
    c = CASES.get(trap) or CASES["unit_mismatch"]
    return {"query": c["query"], "cached": True, "trace": "",
            "results": [{"title": c["title"], "url": "", "snippet": c["snippet"]}]}


def stub_task(bank_id: str = STUB_ID) -> dict:
    public = json.loads((MOCK_DIR / "task.json").read_text())
    return {"id": bank_id, "public": public, "dir": str(MOCK_DIR), "key": STUB_KEY}

import json

import pytest

from bench import data, score


def test_macro_f1_toy():
    gold = {"a": "Yes", "b": "Yes", "c": "No", "d": "To some extent"}
    pred = {"a": "Yes", "b": "No", "c": "No", "d": "Yes"}
    # Yes: tp 1, fp 1, fn 1 -> 0.5; No: tp 1, fp 1 -> 2/3; To some extent: tp 0 -> 0
    assert score.macro_f1(gold, pred) == pytest.approx((0.5 + 2 / 3 + 0) / 3)
    assert score.accuracy(gold, pred) == 0.5


def test_perfect_and_missing():
    gold = {"a": "Yes", "b": "No", "c": "To some extent"}
    assert score.macro_f1(gold, dict(gold)) == 1.0
    # c missing, b unknown label: both are misses for their gold class
    pred = {"a": "Yes", "b": "maybe"}
    assert score.macro_f1(gold, pred) == pytest.approx(1 / 3)
    assert score.report(gold, pred)["missing"] == 2


def test_extra_predictions_ignored():
    gold = {"a": "Yes"}
    assert score.accuracy(gold, {"a": "Yes", "zz": "No"}) == 1.0


def test_lenient_merges_partial_into_yes():
    gold = {"a": "Yes", "b": "To some extent", "c": "No"}
    pred = {"a": "To some extent", "b": "Yes", "c": "No"}
    assert score.lenient_macro_f1(gold, pred) == 1.0
    assert score.macro_f1(gold, pred) == pytest.approx(1 / 3)


def test_empty_gold_raises():
    with pytest.raises(ValueError):
        score.macro_f1({}, {})


TOY = [
    {"conversation_id": f"c{i}", "conversation_history": f"Tutor: q{i}\nStudent: a{i}",
     "tutor_responses": {"T1": {"response": "r1", "annotation": {
         "Mistake_Identification": "Yes", "Mistake_Location": "No",
         "Providing_Guidance": "To some extent", "Actionability": "No"}},
         "T2": {"response": "r2", "annotation": {
             "Mistake_Identification": "No", "Mistake_Location": "No",
             "Providing_Guidance": "No", "Actionability": "No"}}}}
    for i in range(7)
]


def test_parse_and_gold():
    ds = data.parse(TOY)
    assert len(ds) == 7 and len(ds[0].replies) == 2
    g = data.gold(ds, "Mistake_Identification")
    assert g["c0::T1"] == "Yes" and g["c0::T2"] == "No" and len(g) == 14


def test_parse_test_set_shape_has_no_labels():
    doc = [{"conversation_id": "x", "conversation_history": "h",
            "tutor_responses": {"Tutor_1": {"response": "r"}}}]
    ds = data.parse(doc)
    assert ds[0].replies[0].labels == {}
    assert data.gold(ds, "Actionability") == {}


def test_parse_rejects_unknown_label_and_duplicates():
    bad = json.loads(json.dumps(TOY[:1]))
    bad[0]["tutor_responses"]["T1"]["annotation"]["Actionability"] = "Maybe"
    with pytest.raises(ValueError):
        data.parse(bad)
    with pytest.raises(ValueError):
        data.parse(TOY[:1] + TOY[:1])


def test_split_by_dialogue_fixed_and_disjoint():
    ds = data.parse(TOY)
    a, b = data.split(ds)
    assert len(a) == 4 and len(b) == 3
    assert not {d.id for d in a} & {d.id for d in b}
    assert {d.id for d in a} | {d.id for d in b} == {d.id for d in ds}
    a2, _ = data.split(list(reversed(ds)))
    assert [d.id for d in a] == [d.id for d in a2]


def test_submission_adds_annotations_with_fallback():
    from bench import submit
    doc = [{"conversation_id": "x", "conversation_history": "h",
            "tutor_responses": {"Tutor_1": {"response": "r"}, "Tutor_2": {"response": "s"}}}]
    preds = {"x::Tutor_1": {"Mistake_Identification": "No"}}
    out, fallbacks = submit.build(doc, preds, ("Mistake_Identification",))
    assert out[0]["tutor_responses"]["Tutor_1"]["annotation"] == {"Mistake_Identification": "No"}
    assert out[0]["tutor_responses"]["Tutor_2"]["annotation"] == {"Mistake_Identification": "Yes"}
    assert fallbacks == 1 and "annotation" not in doc[0]["tutor_responses"]["Tutor_1"]


def test_table_one_row_per_split_and_system():
    from bench import table
    rows = [{"split": "dev-B", "system": "s", "dimension": d, "macro_f1": "50.0", "n": "8", "record": "1"}
            for d in data.DIMENSIONS]
    out = table.table(rows).splitlines()
    assert out[2] == "| dev-B | s | 50.0 | 50.0 | 50.0 | 50.0 | 8 |" and out[-1].startswith("| test | record")


def test_bootstrap_zero_for_same_preds_and_sign_for_better():
    from bench import compare
    ds = data.parse(TOY)
    gold = {r.key: dict(r.labels) for d in ds for r in d.replies}
    worse = {k: {**v, "Mistake_Identification": "Yes"} for k, v in gold.items()}
    same = compare.bootstrap(ds, gold, gold, reps=50)
    assert all(v == (0.0, 0.0, 0.0) for v in same.values())
    better = compare.bootstrap(ds, worse, gold, reps=50)
    assert better["MI"][0] > 0 and better["MI"][1] > 0 and better["ML"] == (0.0, 0.0, 0.0)


def test_submission_check_catches_changes():
    from bench import submit
    doc = [{"conversation_id": "x", "conversation_history": "h",
            "tutor_responses": {"Tutor_1": {"response": "r"}, "Tutor_2": {"response": "s"}}}]
    sub, _ = submit.build(doc, {}, ("Actionability",))
    assert submit.check(sub, doc, "Actionability") == []
    sub[0]["tutor_responses"]["Tutor_2"]["response"] = "changed"
    assert submit.check(sub, doc, "Actionability")
    assert submit.check(sub[:0], doc, "Actionability")

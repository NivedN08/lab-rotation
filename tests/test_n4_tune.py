import json

from bench import data, tune
from lab.autoloop import Move

GUIDE = "# Grading guide\n\n## Role\n\nGrade.\n\n## Mistake location\n\nold rule\n\n## Output\n\n{\"R1\": {}}\n"

DIALOGUES = data.parse([{
    "conversation_id": f"c{i}", "conversation_history": "Tutor: q\nStudent: a",
    "tutor_responses": {f"T{j}": {"response": f"r{j}", "annotation": {
        "Mistake_Identification": ("Yes", "No", "To some extent")[j % 3],
        "Mistake_Location": ("Yes", "No", "To some extent")[(j + 1) % 3],
        "Providing_Guidance": "Yes", "Actionability": "No"}} for j in range(3)}} for i in range(4)])


def edit(target, value, kind="edit_section"):
    return Move("m", kind, target, value)


def test_validate_edit_rules():
    assert tune.validate(edit("guide.md#Mistake location", "new rule"), GUIDE) == []
    assert tune.validate(edit("guide.md#Output", "x"), GUIDE)
    assert tune.validate(edit("guide.md#Nope", "x"), GUIDE)
    assert tune.validate(edit("other.md#Role", "x"), GUIDE)
    assert tune.validate(edit("guide.md#Role", "## Sneaky\nx"), GUIDE)
    assert tune.validate(edit("guide.md#Role", "Grade."), GUIDE)
    assert tune.validate(edit("guide.md#Role", "x", kind="toggle"), GUIDE)


def test_bundle_applies_both_parts():
    m = Move("b", "bundle", "bundle", [{"kind": "edit_section", "target": "guide.md#Role", "value": "A"},
                                       {"kind": "edit_section", "target": "guide.md#Mistake location", "value": "B"}])
    assert tune.validate(m, GUIDE) == []
    out = tune.apply(m, GUIDE)
    assert "\nA\n" in out and "\nB\n" in out and "old rule" not in out and '{"R1": {}}' in out
    same = Move("b", "bundle", "bundle", [{"kind": "edit_section", "target": "guide.md#Role", "value": "A"}] * 2)
    assert tune.validate(same, GUIDE)


def gold_preds(flip_dim=None):
    preds = {}
    for d in DIALOGUES:
        for r in d.replies:
            p = dict(r.labels)
            if flip_dim:
                p[flip_dim] = "Yes"
            preds[r.key] = p
    return preds


def test_loop_accepts_real_gain_and_rejects_none(tmp_path):
    def grade(guide, replicate):
        return (gold_preds() if "better" in guide else gold_preds("Mistake_Location")), {"notes": {}}

    proposals = iter([
        Move("g01", "edit_section", "guide.md#Mistake location", "better rule", "why"),
        Move("g02", "edit_section", "guide.md#Role", "Grade carefully.", "why"),
    ])

    def proposer(guide, rep, conf, exs, history, model, move_id):
        assert exs and all("human" in e for e in exs) or "better" in guide
        return next(proposals), [], {}

    t = tune.Tuner(DIALOGUES, "m", 1, root=tmp_path, grade=grade, proposer=proposer)
    out = t.run(GUIDE, max_moves=2)
    assert out["accepted"] == ["edit_section guide.md#Mistake location = <11 characters>"]
    assert out["final"] > out["start"] + 20
    assert "better rule" in out["guide"]
    kinds = [json.loads(line)["kind"] for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert kinds.count("move.accepted") == 1 and kinds.count("move.rejected") == 1


def test_examples_spread_over_dimensions():
    preds = gold_preds("Mistake_Location")
    exs = tune.examples(DIALOGUES, preds, {}, limit=4)
    assert len(exs) == 4 and {e["dimension"] for e in exs} == {"ML"}
    assert all(e["guide"] == "Yes" and e["human"] != "Yes" for e in exs)


def test_seed_moves_come_first_and_ship_valid():
    seen = []

    def grade(guide, replicate):
        return gold_preds("Mistake_Location"), {"notes": {}}

    def proposer(*a):
        seen.append("proposer")
        return None, ["nothing"], {}

    t = tune.Tuner(DIALOGUES, "m", 1, grade=grade, proposer=proposer, root=__import__("pathlib").Path(
        __import__("tempfile").mkdtemp()))
    out = t.run(GUIDE, max_moves=2, aa=False, seeds=[Move("s1", "edit_section", "guide.md#Role", "Seeded.", "r")])
    assert t.history[0]["path"] == "seed" and seen == ["proposer"] and out["moves"] == 1
    from bench import judge
    shipped = json.loads((judge.HERE / "seed_moves.json").read_text())
    for m in shipped:
        assert tune.validate(Move("s", m["kind"], m["target"], m["value"]), judge.GUIDE.read_text()) == []

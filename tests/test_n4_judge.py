import json
import re

from bench import data, judge, llm, run

DIALOGUE = data.parse([{
    "conversation_id": "d1", "conversation_history": "Tutor: 2+2?\nStudent: 5",
    "tutor_responses": {
        "Expert": {"response": "Check the sum <again>.", "annotation": {
            "Mistake_Identification": "Yes", "Mistake_Location": "Yes",
            "Providing_Guidance": "Yes", "Actionability": "Yes"}},
        "Novice": {"response": "Great job!", "annotation": {
            "Mistake_Identification": "No", "Mistake_Location": "No",
            "Providing_Guidance": "No", "Actionability": "No"}}}}])[0]


def fake(answer_for):
    calls = []

    def runner(model, system, prompt):
        calls.append((model, system, prompt))
        return {"text": answer_for(model, system, prompt), "usd": 0.01, "ms": 1, "error": None}
    runner.calls = calls
    return runner


def all_labels(prompt, label="Yes"):
    rids = re.findall(r'<reply id="(R\d+)">', prompt)
    return json.dumps({r: {"MI": label, "ML": label, "PG": label, "AC": label, "note": "n"} for r in rids})


def test_prompt_hides_tutor_names_and_quotes_text():
    ids = judge.order(DIALOGUE)
    p = judge.item_prompt(DIALOGUE, ids)
    assert "Expert" not in p and "Novice" not in p
    assert "<again>" not in p and "‹again›" in p
    assert [r for r, _ in ids] == ["R1", "R2"]


def test_parse_labels_normalises_and_reports_missing():
    text = 'Sure:\n```json\n{"R1": {"MI": "yes", "ML": "partially", "PG": "No.", "AC": "To Some Extent"}}\n```'
    labels, missing = judge.parse_labels(text, ["R1", "R2"])
    assert labels["R1"] == {"MI": "Yes", "ML": "To some extent", "PG": "No", "AC": "To some extent"}
    assert missing == ["R2.MI", "R2.ML", "R2.PG", "R2.AC"]


def test_single_caches_and_retries(tmp_path):
    answers = iter(["not json", None])

    def answer(model, system, prompt):
        a = next(answers, None)
        return a if a is not None else all_labels(prompt)
    runner = fake(answer)
    preds, meta = judge.grade_single(DIALOGUE, "guide", "m", runner=runner, cache=tmp_path)
    assert len(runner.calls) == 2      # first answer failed the check, retried once
    assert preds["d1::Expert"]["Mistake_Identification"] == "Yes"
    preds2, meta2 = judge.grade_single(DIALOGUE, "guide", "m", runner=runner, cache=tmp_path)
    assert len(runner.calls) == 2 and meta2["calls"][0]["cached"] and preds2 == preds


def test_panel_agreement_skips_referee(tmp_path):
    runner = fake(lambda m, s, p: all_labels(p, "No"))
    preds, meta = judge.grade_panel(DIALOGUE, "# G\n\n## Role\n\nx\n\n## Output\n\ny\n", "# R\n",
                                    ("a", "a", "a"), runner=runner, cache=tmp_path)
    assert len(runner.calls) == 2 and meta["disputed_cells"] == 0
    assert preds["d1::Novice"]["Actionability"] == "No"


def test_panel_referee_settles_disputes(tmp_path):
    def answer(model, system, prompt):
        if model == "ref":
            assert "Examiner 1" in prompt and "Output" not in system.split("## The examiners")[1]
            disputed = re.findall(r'<reply id="(R\d+)">', prompt)
            return json.dumps({r: {"MI": "To some extent", "ML": "To some extent", "PG": "To some extent",
                                   "AC": "To some extent"} for r in disputed})
        return all_labels(prompt, "Yes" if model == "r1" else "No")
    runner = fake(answer)
    guide = "# G\n\n## Role\n\nx\n\n## Mistake location\n\ndef\n\n## Output\n\ny\n"
    preds, meta = judge.grade_panel(DIALOGUE, guide, "# R\n\n## Role\n\nref\n", ("r1", "r2", "ref"),
                                    runner=runner, cache=tmp_path)
    assert len(runner.calls) == 3 and meta["disputed_cells"] == 8
    assert preds["d1::Expert"]["Mistake_Location"] == "To some extent"


def test_scores_and_results_csv(tmp_path):
    preds = {r.key: dict(r.labels) for r in DIALOGUE.replies}
    rep = run.scores([DIALOGUE], preds)
    assert rep["Mistake_Identification"]["macro_f1"] == 100.0 or rep["Mistake_Identification"]["n"] == 2
    path = tmp_path / "r.csv"
    run.upsert_results(run.result_rows("dev-A", "s", rep), path)
    run.upsert_results(run.result_rows("dev-A", "s", rep) + run.result_rows("dev-B", "s", rep), path)
    lines = path.read_text().strip().splitlines()
    assert lines[0] == "split,dimension,system,macro_f1,n,record" and len(lines) == 1 + 8


def test_usage_stop_on_limit(monkeypatch):
    class P:
        returncode = 1
        stdout = json.dumps({"is_error": True, "result": "Claude AI usage limit reached"})
        stderr = ""
    monkeypatch.setattr(llm.subprocess, "run", lambda *a, **k: P())
    try:
        llm.run_cli("m", "s", "p")
    except llm.UsageStop:
        return
    raise AssertionError("no UsageStop")


def test_command_has_no_tools_and_no_settings():
    cmd = llm.command("opus", "sys")
    assert cmd[cmd.index("--tools") + 1] == "" and "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--setting-sources") + 1] == "" and "--no-session-persistence" in cmd
    assert cmd[cmd.index("--model") + 1] == "claude-opus-5-5"


def test_record_test_fills_blank_scores(tmp_path):
    path = tmp_path / "r.csv"
    run.upsert_results([{"split": "test", "dimension": d, "system": "s", "macro_f1": "", "n": 1547,
                         "record": run.RECORDS[d]} for d in data.DIMENSIONS], path)
    run.record_test("s", "MI=0.705,AC=68.1", path)
    rows = {r.split(",")[1]: r.split(",")[3] for r in path.read_text().splitlines()[1:]}
    assert rows["Mistake_Identification"] == "70.5" and rows["Actionability"] == "68.1"
    assert rows["Mistake_Location"] == ""

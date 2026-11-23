"""Teamily stub: summary text, local file, optional webhook post."""

from lab.sponsors.teamily import Teamily, practice_summary

TASKS = [{"title": "West spend", "trap": "unit_mismatch", "score": 1.0},
         {"title": "Loyalty lift", "trap": "dictionary_flip", "score": 0.5}]
MASTERY = {"unit_mismatch": {"from": 0.3, "to": 0.55}}


def test_summary_text():
    title, text = practice_summary(TASKS, MASTERY, learner="Ana")
    assert title == "Rotation summary: 1.5 of 2"
    assert "1. West spend: the trap was mixed units. Score 1.00." in text
    assert "- mixed units: 0.30 to 0.55" in text


def test_no_url_saves_locally(tmp_path, monkeypatch):
    monkeypatch.delenv("TEAMILY_POST_URL", raising=False)
    calls = []
    out = Teamily(on_call=calls.append, out_dir=tmp_path).post_summary("s1", TASKS, MASTERY)
    assert out["provider"] == "recorded" and not out["posted"] and (tmp_path / "s1.md").exists()
    assert calls[0].sponsor == "teamily" and calls[0].fallback


def test_webhook_post_and_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("TEAMILY_POST_URL", "https://teamily.test/hook")
    monkeypatch.delenv("TEAMILY_API_KEY", raising=False)
    sent = []
    out = Teamily(out_dir=tmp_path, poster=lambda u, b, h: sent.append((u, b, h))).post_summary("s2", TASKS)
    assert out["posted"] and out["provider"] == "teamily" and sent[0][1]["session"] == "s2"

    def boom(u, b, h):
        raise ConnectionError

    calls = []
    out = Teamily(on_call=calls.append, out_dir=tmp_path, poster=boom).post_summary("s3", TASKS)
    assert not out["posted"] and out["provider"] == "recorded" and calls[0].ok is False

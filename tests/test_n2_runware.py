"""Runware: voices, portraits and Riley through a fake client, with every fallback."""

import types

import pytest

from lab.sponsors import runware as rwmod
from lab.sponsors.runware import Runware, mp3_seconds, speech_seconds

# 38 MPEG1 layer 3 frames at 128 kbps, 44.1 kHz: 417 bytes and 1152 samples each, 0.99 s.
FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413
MP3 = FRAME * 38
MP3_S = round(38 * 1152 / 44100, 2)


class FakeClient:
    def __init__(self, fail=None):
        self.fail = fail
        self.requests = []

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def _maybe_fail(self, req):
        self.requests.append(req)
        if self.fail:
            raise RuntimeError({"code": self.fail, "message": "secret details"})

    async def audioInference(self, req):
        await self._maybe_fail(req)
        return [types.SimpleNamespace(audioURL="https://x.test/a.mp3", cost=0.0215)]

    async def imageInference(self, req):
        await self._maybe_fail(req)
        return [types.SimpleNamespace(imageURL="https://x.test/p.png", cost=0.001)]

    async def textInference(self, req):
        await self._maybe_fail(req)
        return [types.SimpleNamespace(text="Spend went up. Holds.", cost=0.0004)]


def make(tmp_path, fail=None, calls=None, fallback=None):
    client = FakeClient(fail)

    def download(url, path):
        with open(path, "wb") as f:
            f.write(MP3 if url.endswith(".mp3") else b"\x89PNG fake")

    rw = Runware(on_call=(calls.append if calls is not None else None), client_factory=lambda: client,
                 offline=False, fallback=fallback or (lambda s, u: "Looks fine to me. Holds."),
                 audio_dir=tmp_path / "audio", portrait_dir=tmp_path / "portraits", download=download)
    return rw, client


def test_mp3_seconds_and_estimate(tmp_path):
    p = tmp_path / "a.mp3"
    p.write_bytes(MP3)
    assert mp3_seconds(p) == MP3_S == 0.99
    # VBR: the duration counts frames, so a low-bitrate first frame does not stretch it.
    low = b"\xff\xfb\x10\x00" + b"\x00" * 100  # 32 kbps, 104 bytes
    p.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00" + low + MP3)
    assert mp3_seconds(p) == round(39 * 1152 / 44100, 2)
    assert speech_seconds("one two three four five six") == 2.3


def test_tts_saves_mp3_with_cost_and_caches(tmp_path):
    calls = []
    rw, client = make(tmp_path, calls=calls)
    line = rw.tts("ines", "Check spend by region.", line_of=7)
    assert line["provider"] == "runware" and line["file"].endswith(".mp3") and line["lineOf"] == 7
    assert line["seconds"] == MP3_S and line["cost"] == 0.0215
    assert (tmp_path / "audio" / line["file"]).exists()
    sp = client.requests[0].speech
    assert (sp.text, sp.voice) == ("Check spend by region.", "Serena")
    assert calls[0].event_data() == {"sponsor": "runware", "label": "Voiced a line for Ines", "count": 1,
                                     "op": "tts", "by": "ines", "ms": calls[0].ms, "fallback": False, "cost": 0.0215}
    again = rw.tts("ines", "Check spend by region.")
    assert again["file"] == line["file"] and len(client.requests) == 1


def test_tts_without_credit_goes_to_browser_and_stops_trying(tmp_path):
    calls = []
    rw, client = make(tmp_path, fail="thirdPartyInsufficientCredits", calls=calls)
    line = rw.tts("vale", "Next task.")
    assert line == {"file": "", "seconds": speech_seconds("Next task."), "provider": "browser"}
    assert calls[0].ok is False and calls[0].fallback and calls[0].error == "thirdPartyInsufficientCredits"
    rw.tts("vale", "Another line.")
    assert len(client.requests) == 1  # no second paid attempt this session


def test_offline_tts_is_browser(tmp_path):
    rw = Runware(offline=True, audio_dir=tmp_path)
    assert rw.tts("sam", "Hint one.")["provider"] == "browser"


def test_portrait_saved_then_reused(tmp_path):
    rw, client = make(tmp_path)
    p = rw.portrait("riley")
    assert p == {"file": "riley.png", "cost": 0.001, "provider": "runware"}
    assert "intern" in client.requests[0].positivePrompt
    assert rw.portrait("riley")["provider"] == "saved" and len(client.requests) == 1


def test_riley_on_open_model(tmp_path):
    calls = []
    rw, client = make(tmp_path, calls=calls)
    ans = rw.riley(system="Be careless.", user="Is the claim true?")
    assert ans == {"text": "Spend went up. Holds.", "model": rwmod.TEXT_MODEL, "provider": "runware", "cost": 0.0004}
    req = client.requests[0]  # Runware refuses a "system" message: the prompt rides in settings
    assert [m.role for m in req.messages] == ["user"]
    assert req.settings.systemPrompt == "Be careless." + rwmod.RILEY_GUARD  # keeps the planted verdict
    assert calls[0].op == "chat" and calls[0].by == "riley"


def test_riley_falls_back_to_claude(tmp_path):
    seen = []
    rw, _ = make(tmp_path, fail="thirdPartyInsufficientCredits",
                 fallback=lambda s, u: seen.append((s, u)) or "Fine. Holds.")
    ans = rw.riley(system="Be careless.", user="Is the claim true?")
    assert ans["provider"] == "claude_fallback" and ans["text"] == "Fine. Holds."
    assert seen == [("Be careless." + rwmod.RILEY_GUARD, "Is the claim true?")]


def test_riley_fallback_failure_is_silent_not_fatal(tmp_path):
    def boom(s, u):
        raise TimeoutError

    rw = Runware(offline=True, fallback=boom, audio_dir=tmp_path)
    assert rw.riley(system="x", user="y") == {"text": "", "model": "claude", "provider": "claude_fallback",
                                              "cost": None}


def test_fallback_env_has_no_keys(monkeypatch):
    monkeypatch.setenv("RUNWARE_API_KEY", "abc")
    monkeypatch.setenv("BAND_VALE_API_KEY", "abc")
    env = rwmod._clean_env()
    assert "RUNWARE_API_KEY" not in env and "BAND_VALE_API_KEY" not in env and "PATH" in env


@pytest.mark.live
def test_live_portrait(tmp_path):
    rw = Runware(audio_dir=tmp_path, portrait_dir=tmp_path)
    if rw.offline:
        pytest.skip("no Runware key")
    assert rw.portrait("sam")["provider"] == "runware"


def test_voices_are_valid_and_distinct(monkeypatch):
    for agent in rwmod.PORTRAIT_PROMPTS:
        monkeypatch.delenv(f"RUNWARE_VOICE_{agent.upper()}", raising=False)
    inworld = [rwmod.voice_for(a, "inworld:tts@1.5-mini") for a in rwmod.PORTRAIT_PROMPTS]
    assert set(inworld) <= rwmod.INWORLD_VOICES and len(set(inworld)) == len(inworld)
    assert rwmod.voice_for("riley", "inworld:tts@2") == "Timothy"
    assert rwmod.voice_for("sam", "alibaba:qwen@3-tts-1.7b-customvoice") == "ryan"
    monkeypatch.setenv("RUNWARE_VOICE_SAM", "Craig")
    assert rwmod.voice_for("sam", "inworld:tts@1.5-mini") == "Craig"


def test_check_reports_cost_per_line_and_riley_latency(tmp_path):
    rw, client = make(tmp_path)
    out = rwmod.check(rw)
    assert set(out["lines"]) == set(rwmod.CHECK_LINES) and out["costPerLine"] == 0.0215
    assert out["riley"]["provider"] == "runware" and out["riley"]["ms"] >= 0
    assert [r.speech.voice for r in client.requests[:5]] == [rwmod.voice_for(a, rw.tts_model) for a in rwmod.CHECK_LINES]


def test_overlong_line_goes_to_browser_without_a_call(tmp_path):
    rw, client = make(tmp_path)
    line = rw.tts("vale", "word " * 500)
    assert line["provider"] == "browser" and client.requests == []


def test_default_models_and_env_override(monkeypatch):
    monkeypatch.delenv("RUNWARE_TTS_MODEL", raising=False)
    monkeypatch.delenv("RUNWARE_TEXT_MODEL", raising=False)
    rw = Runware(offline=True)
    assert (rw.tts_model, rw.text_model) == ("inworld:tts@2", "openai:gpt@5.4-mini")
    monkeypatch.setenv("RUNWARE_TTS_MODEL", "inworld:tts@1.5-mini")
    monkeypatch.setenv("RUNWARE_TEXT_MODEL", "google:gemma@4-31b")
    rw = Runware(offline=True)
    assert (rw.tts_model, rw.text_model) == ("inworld:tts@1.5-mini", "google:gemma@4-31b")

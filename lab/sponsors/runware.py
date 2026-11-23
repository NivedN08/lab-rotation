"""Runware: agent voices, agent portraits, and Riley's careless analysis on a non-Claude model.

What Runware serves (checked 2026-11-23 with modelSearch and test calls):
- Images: Runware's own models (FLUX schnell `runware:100@1`) work on the current
  balance, $0.001 per 512x512 portrait.
- Speech: ElevenLabs (`elevenlabs:24@1` Flash v2.5 ...), Inworld, MiniMax Speech, Gemini
  TTS, xAI TTS and the open Qwen3-TTS (`alibaba:qwen@3-tts-1.7b-customvoice`, about
  $0.02 a line). Third-party models need a paid invoice or $5 of credit first.
- Text: modelSearch lists open models (Gemma 4 31B, DeepSeek V4 Flash, GLM, Kimi), but on
  our account every one of them returns `invalidModel` (checked after the top-up, by SDK and
  REST). OpenAI's GPT-5.4 mini (`openai:gpt@5.4-mini`) answers. Runware refuses a "system"
  message; the system prompt goes in `settings.systemPrompt`.

Chosen (from Runware's model docs and schemas, before any paid call):
- Voice: Inworld TTS-2 (`inworld:tts@2`), $0.000035 per character, so a 100-160 character
  line is about $0.0035-0.0056; Runware's examples show 1.8-3.7 s per line. One voice per
  agent from the 73 voices it shares with TTS-1.5 (INWORLD_VOICES). `RUNWARE_TTS_MODEL`
  overrides it, e.g. `inworld:tts@1.5-mini` ($0.000025 per character, same voices).
  Voice sets also exist for MiniMax Speech 2.8 (`minimax:speech@2.8`, $0.10 per 1,000 characters,
  emotion calm and speed 0.95) and Gemini 3.8 Flash TTS (`google:gemini@3.8-flash-tts`, about
  $0.025 per 1,000; it takes text and voice only and reads a spoken style direction aloud).
  ElevenLabs returns `invalidModel` on our account. `speakable()` cleans each line first.
- Riley: GPT-5.4 mini (`openai:gpt@5.4-mini`) through Runware, about $0.0002 and 2-3 s an
  answer. `RUNWARE_TEXT_MODEL` overrides it (e.g. `google:gemma@4-31b` once Runware enables it).

After the credit lands, `uv run python -m lab.sponsors.runware check` voices one line per
agent and asks Riley once, then prints cost per line and Riley's latency (about $0.02 all in).

Fallbacks: a line Runware can't voice comes back as `provider: "browser"` with an empty
file (the browser speaks the `agent.say` text); Riley runs on `claude -p` with no tools
(`provider: "claude_fallback"`); a portrait falls back to the file already on disk.

    rw = Runware(on_call=engine.sponsor_call)
    line = rw.tts("ines", "Your spend total mixes cents and dollars.")  # {file, seconds, cost, provider}
    rw.portrait("vale")                                                   # data/portraits/vale.png
    ans = rw.riley(system=careless_prompt, user=task_text)              # {text, model, provider, cost}
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import threading
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from lab.sponsors.calls import DATA, Reporter, SponsorCall, Timer, report

AUDIO = DATA / "audio"
PORTRAITS = DATA / "portraits"
TTS_MODEL = "inworld:tts@2"
TEXT_MODEL = "openai:gpt@5.4-mini"
IMAGE_MODEL = "runware:100@1"
TIMEOUT_S = 45
TTS_MAX_CHARS = 2000  # Inworld's limit per line; longer lines go to browser speech
WORDS_PER_S = 2.6

# One voice per agent, per TTS family. Override one with RUNWARE_VOICE_<AGENT>. The voices match
# the portraits (PORTRAIT_PROMPTS names each one's gender): Vale and Sam are men, Ines and Telem
# women, Riley a young man.
VOICE_SETS = {
    "inworld:": {"vale": "Craig", "ines": "Serena", "sam": "Dennis", "telem": "Ashley", "riley": "Timothy"},
    "minimax:speech": {"vale": "English_Trustworth_Man", "ines": "English_ConfidentWoman",
                       "sam": "English_PatientMan", "telem": "English_SereneWoman", "riley": "English_DecentYoungMan"},
    "google:gemini": {"vale": "Charon", "ines": "Kore", "sam": "Achird", "telem": "Sulafat", "riley": "Puck"},
    "alibaba:qwen@3-tts": {"vale": "eric", "ines": "serena", "sam": "ryan", "telem": "vivian", "riley": "dylan"},
}
# Inworld voices from Runware's schema for inworld:tts@1.5-mini; inworld:tts@2 accepts all of these too.
INWORLD_VOICES = frozenset(
    "Loretta Darlene Marlene Hank Evelyn Celeste Pippa Tessa Liam Callum Hamish Abby Graham Rupert Mortimer "
    "Snik Anjali Saanvi Arjun Claire Oliver Simon Elliot James Serena Gareth Vinny Lauren Jessica Ethan Tyler "
    "Jason Chloe Veronica Victoria Miranda Sebastian Victor Malcolm Kayla Nate Jake Brian Amina Kelsey Derek "
    "Grant Evan Alex Ashley Craig Deborah Dennis Edward Elizabeth Hades Julia Pixie Mark Olivia Priya Ronald "
    "Sarah Shaun Theodore Timothy Wendy Dominus Hana Clive Carter Blake Luna".split())


def voice_for(agent: str, model: str) -> str:
    override = os.environ.get(f"RUNWARE_VOICE_{agent.upper()}")
    if override:
        return override
    for prefix, voices in VOICE_SETS.items():
        if model.startswith(prefix):
            return voices.get(agent, next(iter(voices.values())))
    return VOICE_SETS["inworld:"].get(agent, "Dennis")


def speech_settings(agent: str, model: str) -> dict:
    """Extra `speech` fields per model family. Runware's Gemini and xAI voices take text and voice
    only; Inworld takes speed; MiniMax also takes an emotion. RUNWARE_TTS_SPEED sets the speed."""
    out: dict = {}
    if model.startswith("minimax:"):
        out = {"emotion": "happy" if agent == "riley" else "calm", "speed": 0.95}
    speed = os.environ.get("RUNWARE_TTS_SPEED")
    if speed and model.startswith(("inworld:", "minimax:")):
        out["speed"] = min(1.5, max(0.5, float(speed)))
    return out


_STAGE = r"(?:smiles?|laughs?|chuckles?|grins?|nods?|sighs?|pauses?|beat|shrugs?|winks?)"


def speakable(text: str) -> str:
    """The line as it should sound: verdict tokens as words, no markdown, no stage directions."""
    t = re.sub(r"\bcant_tell\b", "can't tell", text)
    t = re.sub(r"(\*\*|__)(.+?)\1", r"\2", t)                      # **bold**, __bold__
    t = re.sub(r"\*[^*\n]{1,40}\*", " ", t)                          # *nods*
    t = re.sub(r"\[[^\]\n]{1,40}\]", " ", t)                         # [laughs]
    t = re.sub(rf"\(\s*{_STAGE}\b[^)\n]{{0,30}}\)", " ", t, flags=re.I)  # (smiles warmly)
    t = re.sub(r"`([^`\n]*)`", r"\1", t)                              # `code`
    t = re.sub(r"(?m)^\s*(?:#{1,6}|[-*•])\s+", "", t)                  # headings and bullets
    t = re.sub(r"\b([A-Za-z]+)_(?=[A-Za-z])", r"\1 ", t)               # duplicate_rows -> duplicate rows
    t = re.sub(r"\b([A-Za-z]+)_(?=[A-Za-z])", r"\1 ", t)
    return re.sub(r"\s+", " ", t).strip()

PORTRAIT_PROMPTS = {
    "vale": "a man in his fifties, head of a retail analytics lab, calm and exacting, reading glasses, "
            "warm office light",
    "ines": "a woman in her forties, data examiner holding a clipboard of failing checks, precise and fair, "
            "cool light",
    "sam": "a man in his thirties, methods reviewer with a marker at a whiteboard of SQL, patient and kind",
    "telem": "a woman in her thirties, research librarian among shelves of store reports and receipts, curious",
    "riley": "an eager young man, AI intern at a messy desk with spreadsheets, overconfident grin",
}
PORTRAIT_STYLE = "flat vector portrait, soft colors, plain background, friendly, no text"


def _run(coro):
    """Run a coroutine from sync code, even inside a running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict = {}

    def target():
        try:
            box["v"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001
            box["e"] = exc

    th = threading.Thread(target=target)
    th.start()
    th.join()
    if "e" in box:
        raise box["e"]
    return box["v"]


def error_code(exc: BaseException) -> str:
    """Runware's error code (e.g. `thirdPartyInsufficientCredits`), never the message text."""
    m = re.search(r"'code': '([A-Za-z]+)'", str(exc))
    return m.group(1) if m else type(exc).__name__


def mp3_seconds(path) -> float:
    """Duration by walking every MPEG layer 3 frame (Runware's MP3s are VBR); 0 when it can't tell."""
    data = Path(path).read_bytes()
    i = 0
    if data[:3] == b"ID3" and len(data) > 10:
        i = 10 + ((data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9])
    rates = {1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],  # MPEG1 layer 3
             2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}  # MPEG2/2.5 layer 3
    srates = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}
    total = 0.0
    while i + 4 <= len(data):
        b1, b2 = data[i + 1], data[i + 2]
        if data[i] == 0xFF and (b1 & 0xE0) == 0xE0 and (b1 >> 1) & 0x03 == 0x01:
            ver, idx, sri = (b1 >> 3) & 0x03, b2 >> 4, (b2 >> 2) & 0x03
            if ver != 1 and 0 < idx < 15 and sri < 3:
                mpeg1, sr = ver == 3, srates[ver][sri]
                size = (144 if mpeg1 else 72) * rates[1 if mpeg1 else 2][idx] * 1000 // sr + ((b2 >> 1) & 1)
                total += (1152 if mpeg1 else 576) / sr
                i += size
                continue
        i += 1
    return round(total, 2)


def speech_seconds(text: str) -> float:
    return round(max(1.0, len(text.split()) / WORDS_PER_S), 1)


def _clean_env() -> dict:
    """The environment for a fallback `claude -p`: no sponsor keys."""
    return {k: v for k, v in os.environ.items() if not re.search(r"(KEY|TOKEN|SECRET)", k)}


def claude_fallback(system: str, user: str, *, model: str = "haiku", timeout_s: int = 90) -> str:
    """Riley on `claude -p` with no tools, no MCP, no settings; the prompt goes on stdin."""
    cmd = ["claude", "-p", "--model", model, "--output-format", "text", "--strict-mcp-config",
           "--setting-sources", "", "--tools", "", "--system-prompt", system]
    proc = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=timeout_s, env=_clean_env())
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p exited {proc.returncode}")
    return proc.stdout.strip()


class Runware:
    def __init__(self, *, on_call: Reporter = None, client_factory: Optional[Callable] = None,
                 offline: Optional[bool] = None, fallback: Optional[Callable[[str, str], str]] = None,
                 audio_dir: Path = AUDIO, portrait_dir: Path = PORTRAITS, download=None):
        from lab.env import load_env

        load_env()
        self.on_call = on_call
        self.offline = (os.environ.get("RUNWARE_OFFLINE") == "1" or not os.environ.get("RUNWARE_API_KEY")) \
            if offline is None else offline
        self._factory = client_factory or self._make_client
        self._fallback = fallback or claude_fallback
        self.audio_dir, self.portrait_dir = Path(audio_dir), Path(portrait_dir)
        self._download = download or (lambda url, path: urllib.request.urlretrieve(url, path))
        self.tts_model = os.environ.get("RUNWARE_TTS_MODEL", TTS_MODEL)
        self.text_model = os.environ.get("RUNWARE_TEXT_MODEL", TEXT_MODEL)
        self.image_model = os.environ.get("RUNWARE_IMAGE_MODEL", IMAGE_MODEL)
        self.no_credit: set = set()  # ops refused for credit; skip them for the rest of the session

    @staticmethod
    def _make_client():
        from runware import Runware as RW

        return RW(api_key=os.environ["RUNWARE_API_KEY"])

    async def _call(self, method: str, request):
        client = self._factory()
        await client.connect()
        try:
            out = await asyncio.wait_for(getattr(client, method)(request), TIMEOUT_S)
        finally:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        return out[0] if isinstance(out, list) else out

    def _refused(self, op: str, exc: BaseException) -> None:
        if "Credit" in error_code(exc) or "Balance" in error_code(exc) or "concurrentRequest" in error_code(exc):
            self.no_credit.add(op)

    # -- voice ----------------------------------------------------------------

    def tts(self, agent: str, text: str, *, line_of: Optional[int] = None) -> dict:
        """{file, seconds, cost, provider, lineOf}: the `voice.line` data. Cached by text and voice."""
        voice = voice_for(agent, self.tts_model)
        said, extra = speakable(text), speech_settings(agent, self.tts_model)
        tag = "|" + json.dumps(extra, sort_keys=True) if extra else ""
        name = hashlib.sha1(f"{self.tts_model}|{voice}|{said}{tag}".encode()).hexdigest()[:16] + ".mp3"
        path = self.audio_dir / name
        label = f"Voiced a line for {agent.capitalize()}"
        base = {"lineOf": line_of} if line_of is not None else {}
        if path.exists() and path.stat().st_size > 0:
            report(self.on_call, SponsorCall("runware", "tts", label + " (saved audio)", by=agent, fallback=True))
            return dict(base, file=name, seconds=mp3_seconds(path) or speech_seconds(text), cost=0.0,
                        provider="runware")
        if said and not self.offline and "tts" not in self.no_credit and len(said) <= TTS_MAX_CHARS:
            from runware import IAudioInference

            t = Timer()
            try:
                a = _run(self._call("audioInference", IAudioInference(
                    model=self.tts_model, speech={"text": said, "voice": voice, **extra}, outputType="URL",
                    outputFormat="MP3", includeCost=True)))
                self.audio_dir.mkdir(parents=True, exist_ok=True)
                self._download(a.audioURL, str(path))
                cost = float(a.cost or 0.0)
                report(self.on_call, SponsorCall("runware", "tts", label, ms=t.ms, by=agent, cost_usd=cost))
                return dict(base, file=name, seconds=mp3_seconds(path) or speech_seconds(text), cost=cost,
                            provider="runware")
            except Exception as exc:  # noqa: BLE001
                self._refused("tts", exc)
                report(self.on_call, SponsorCall("runware", "tts", label, ok=False, ms=t.ms, by=agent, fallback=True,
                                                 error=error_code(exc)))
        return dict(base, file="", seconds=speech_seconds(text), provider="browser")

    # -- portraits ------------------------------------------------------------

    def portrait(self, agent: str, *, force: bool = False) -> dict:
        """{file, cost, provider}; the PNG lands in data/portraits/<agent>.png."""
        path = self.portrait_dir / f"{agent}.png"
        if path.exists() and not force:
            return {"file": path.name, "cost": 0.0, "provider": "saved"}
        label = f"Drew a portrait of {agent.capitalize()}"
        if not self.offline and "image" not in self.no_credit:
            from runware import IImageInference

            t = Timer()
            try:
                img = _run(self._call("imageInference", IImageInference(
                    positivePrompt=f"{PORTRAIT_PROMPTS.get(agent, agent)}, {PORTRAIT_STYLE}", model=self.image_model,
                    width=512, height=512, numberResults=1, outputFormat="PNG", includeCost=True)))
                self.portrait_dir.mkdir(parents=True, exist_ok=True)
                self._download(img.imageURL, str(path))
                cost = float(img.cost or 0.0)
                report(self.on_call, SponsorCall("runware", "image", label, ms=t.ms, by=agent, cost_usd=cost))
                return {"file": path.name, "cost": cost, "provider": "runware"}
            except Exception as exc:  # noqa: BLE001
                self._refused("image", exc)
                report(self.on_call, SponsorCall("runware", "image", label, ok=False, ms=t.ms, by=agent,
                                                 fallback=True, error=error_code(exc)))
        return {"file": "", "cost": 0.0, "provider": "none"}

    # -- Riley ----------------------------------------------------------------

    def riley(self, *, system: str, user: str, max_tokens: int = 600) -> dict:
        """{text, model, provider, cost}: Riley's careless take, for `rival.answer`.

        RILEY_GUARD goes after the engine's system prompt: without it GPT-5.4 mini sometimes re-checks
        the planted careless analysis and states the opposite verdict."""
        system = system + RILEY_GUARD
        if not self.offline and "text" not in self.no_credit:
            from runware import ITextInference, ITextInferenceMessage

            t = Timer()
            try:
                x = _run(self._call("textInference", ITextInference(
                    model=self.text_model,
                    # Runware refuses a "system" message (invalidMessageRole); it takes settings.systemPrompt.
                    messages=[ITextInferenceMessage(role="user", content=user)],
                    includeCost=True, settings={"maxTokens": max_tokens, "systemPrompt": system})))
                text = (x.text or "").strip()
                if not text:
                    raise RuntimeError("empty")
                cost = float(x.cost or 0.0)
                report(self.on_call, SponsorCall("runware", "chat", "Riley answered on Runware", ms=t.ms,
                                                 by="riley", cost_usd=cost))
                return {"text": text, "model": self.text_model, "provider": "runware", "cost": cost}
            except Exception as exc:  # noqa: BLE001
                self._refused("text", exc)
                report(self.on_call, SponsorCall("runware", "chat", "Riley answered on Runware", ok=False,
                                                 ms=t.ms, by="riley", fallback=True, error=error_code(exc)))
        try:
            text = self._fallback(system, user)
        except Exception:  # noqa: BLE001 - the engine shows Riley as silent rather than breaking
            text = ""
        return {"text": text, "model": "claude", "provider": "claude_fallback", "cost": None}


RILEY_GUARD = ("\n\nYour quick analysis is final. Repeat its verdict and only the numbers it gives; never add, "
               "re-check or reverse anything. If it gives no number, name its suspicion and say you can't tell. "
               "Plain words, no markdown.")

CHECK_LINES = {
    "vale": "Welcome to the lab. Your first task is on your desk.",
    "ines": "Your answer says the claim holds, but the spend check failed for the West region.",
    "sam": "Try comparing average spend by region before you trust the total.",
    "telem": "I found a real case where a retailer counted the same receipts twice.",
    "riley": "Easy one. Spend went up, so the claim holds. Next!",
}
CHECK_RILEY = ("You are Riley, an eager AI intern who answers fast and checks nothing. Reply in two short "
               "sentences and end with a verdict word: holds, fails or cant_tell.",
               "Claim: average spend per visit rose 12% in the West region last quarter. The visits table has "
               "300 rows with store, region, visit_date and spend.")


def check(rw: "Runware") -> dict:
    """Live check after a top-up: one voice line per agent and one Riley answer (about $0.02)."""
    import time

    lines = {}
    for agent, text in CHECK_LINES.items():
        t0 = time.monotonic()
        line = rw.tts(agent, text)
        lines[agent] = dict(line, chars=len(text), voice=voice_for(agent, rw.tts_model),
                            ms=int((time.monotonic() - t0) * 1000))
    t0 = time.monotonic()
    riley = rw.riley(system=CHECK_RILEY[0], user=CHECK_RILEY[1])
    riley_ms = int((time.monotonic() - t0) * 1000)
    paid = [x for x in lines.values() if x["provider"] == "runware" and x.get("cost")]
    return {"ttsModel": rw.tts_model, "textModel": rw.text_model, "lines": lines,
            "costPerLine": round(sum(x["cost"] for x in paid) / len(paid), 5) if paid else None,
            "costPerChar": round(sum(x["cost"] for x in paid) / sum(x["chars"] for x in paid), 7) if paid else None,
            "riley": dict(riley, ms=riley_ms)}


if __name__ == "__main__":
    import json
    import sys

    rw = Runware(on_call=lambda c: print(c.event_data()))
    if sys.argv[1:2] == ["portraits"]:
        for a in PORTRAIT_PROMPTS:
            print(a, rw.portrait(a, force="--force" in sys.argv))
    elif sys.argv[1:2] == ["say"] and len(sys.argv) >= 4:
        print(rw.tts(sys.argv[2], " ".join(sys.argv[3:])))
    elif sys.argv[1:2] == ["check"]:
        print(json.dumps(check(rw), indent=2))
    else:
        print("usage: python -m lab.sponsors.runware portraits [--force] | say <agent> <text> | check")

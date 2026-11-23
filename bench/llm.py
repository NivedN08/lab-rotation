"""One text-in, text-out call to headless Claude Code on the user's plan, with a disk cache.

    claude -p --tools "" --strict-mcp-config --no-session-persistence --setting-sources "" \
        --output-format json --model <model> --system-prompt <system>   (the item on stdin)

No tools, no MCP servers, no settings, no session files; API keys are stripped from the
environment so the CLI uses the subscription login. Replies are cached in
data/bench/cache/ by (model, system, prompt, replicate), so a stopped run resumes where it
left off and a rerun costs nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import time

from bench.data import ROOT

CACHE = ROOT / "data" / "bench" / "cache"
CLAUDE = shutil.which("claude") or "/opt/homebrew/bin/claude"
MODELS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5",
          "fable": "claude-fable-5-2"}
STRIPPED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "EXA_API_KEY", "PAST_API_KEY")
LIMIT_WORDS = ("usage limit", "rate limit", "limit reached", "credit balance", "out of extra usage")
TIMEOUT_S = 300


class UsageStop(RuntimeError):
    """The plan's usage limit was hit: stop the run instead of retrying."""


def model_id(name: str) -> str:
    return MODELS.get(name, name)


def cache_key(model: str, system: str, prompt: str, replicate: int = 0) -> str:
    blob = json.dumps([model_id(model), system, prompt, replicate], ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def cache_path(key: str, root: pathlib.Path = CACHE) -> pathlib.Path:
    return root / key[:2] / f"{key}.json"


def command(model: str, system: str) -> list[str]:
    return [CLAUDE, "-p", "--tools", "", "--strict-mcp-config", "--no-session-persistence",
            "--setting-sources", "", "--output-format", "json", "--model", model_id(model),
            "--system-prompt", system]


def _env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in STRIPPED_ENV}


def run_cli(model: str, system: str, prompt: str) -> dict:
    """One CLI call: {"text", "usd", "ms", "error"}. Raises UsageStop on a usage limit."""
    t0 = time.time()
    proc = subprocess.run(command(model, system), input=prompt, capture_output=True, text=True,
                          timeout=TIMEOUT_S, env=_env(), cwd=str(CACHE.parent))
    ms = int(1000 * (time.time() - t0))
    try:
        doc = json.loads(proc.stdout)
    except ValueError:
        doc = {}
    text = str(doc.get("result") or "")
    error = bool(doc.get("is_error")) or proc.returncode != 0 or not text
    blob = (text + " " + proc.stderr[-500:]).lower()
    if error and any(w in blob for w in LIMIT_WORDS):
        raise UsageStop(text or proc.stderr[-300:])
    return {"text": text, "usd": doc.get("total_cost_usd"), "ms": doc.get("duration_ms") or ms,
            "error": (proc.stderr[-300:] or text[:300]) if error else None}


def call(model: str, system: str, prompt: str, *, replicate: int = 0, cache: pathlib.Path = CACHE,
         runner=run_cli, check=None) -> dict:
    """A cached call. `check(text)` returns a problem string or None; a reply that fails it (or
    errors) is retried once and is cached only when it passes. Adds "cached": bool."""
    path = cache_path(cache_key(model, system, prompt, replicate), cache)
    if path.is_file():
        try:
            out = json.loads(path.read_text())
            return {**out, "cached": True}
        except ValueError:
            pass
    out = {}
    for _ in range(2):
        out = runner(model, system, prompt)
        problem = out.get("error") or (check(out["text"]) if check else None)
        if not problem:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({**out, "model": model_id(model), "replicate": replicate}))
            tmp.replace(path)
            return {**out, "cached": False}
        out = {**out, "error": problem}
    return {**out, "cached": False}

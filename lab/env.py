"""Load settings from the repo's .env. Never print or log the values."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """Read ROOT/.env into os.environ (existing variables win)."""
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)


def need(name: str) -> str:
    """Return a required setting or raise, naming only the key."""
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"missing setting {name} (add it to .env)")
    return value

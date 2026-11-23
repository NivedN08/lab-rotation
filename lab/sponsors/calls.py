"""The `sponsor.call` record every sponsor client returns or reports.

Shape follows `contract/events.md` (Sponsors): sponsor, label, count, failed?, cost?,
trace?, op, by, ms, fallback. `ok` and `error` are kept for our own logs; `error` is a
short class name and status code only, never a response body (bodies can echo
headers, and headers carry keys).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
RECORDED = Path(__file__).resolve().parent / "recorded"
DATA = ROOT / "data"


@dataclass
class SponsorCall:
    sponsor: str
    op: str
    label: str
    ok: bool = True
    ms: int = 0
    fallback: bool = False
    by: str = "system"
    cost_usd: Optional[float] = None
    trace: Optional[str] = None
    count: int = 1
    error: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def event_data(self) -> dict:
        """The `data` of a `sponsor.call` event (camelCase, optional fields dropped)."""
        d = {
            "sponsor": self.sponsor,
            "label": self.label,
            "count": self.count,
            "op": self.op,
            "by": self.by,
            "ms": self.ms,
            "fallback": self.fallback,
        }
        if not self.ok:
            d["failed"] = True
        if self.cost_usd is not None:
            d["cost"] = round(self.cost_usd, 6)
        if self.trace:
            d["trace"] = self.trace
        return d

    def as_dict(self) -> dict:
        return asdict(self)


Reporter = Optional[Callable[[SponsorCall], None]]


def report(on_call: Reporter, call: SponsorCall) -> SponsorCall:
    if on_call is not None:
        try:
            on_call(call)
        except Exception:  # noqa: BLE001 - a reporter must never break a session
            pass
    return call


def short_error(exc: BaseException) -> str:
    """Class name plus HTTP status if there is one. Never the message text."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    name = type(exc).__name__
    return f"{name} {status}" if status else name


class Timer:
    def __init__(self) -> None:
        self.t0 = time.monotonic()

    @property
    def ms(self) -> int:
        return int((time.monotonic() - self.t0) * 1000)


def load_recorded(name: str, default=None):
    path = RECORDED / name
    if not path.exists():
        return default
    return json.loads(path.read_text())


def save_recorded(name: str, value) -> Path:
    RECORDED.mkdir(parents=True, exist_ok=True)
    path = RECORDED / name
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    return path

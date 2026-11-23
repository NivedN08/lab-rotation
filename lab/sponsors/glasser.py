"""Glasser: real retail numbers for N3's task generator, with the cost of every call.

Glasser is a pay-per-call broker of third-party APIs. We call its MCP server
(`https://api.glasser.ai/mcp`, JSON-RPC over HTTPS) with `GLASSER_API_KEY`; no extra
package. Two endpoints:

- `financialdatasets /kpi/metrics` ($0.02): a retailer's disclosed KPIs, such as
  `total_stores`, `traffic_growth`, `comparable_store_sales_growth`.
- `serper /shopping` ($0.002): Google Shopping listings, for price levels.

Every run reports a `sponsor.call` with `cost` (Glasser's `charge_usd`) and `trace`
(the run's page on app.glasser.ai). `retail_params()` is what N3 reads; it falls back
to `recorded/glasser_retail.json` when Glasser is down, `GLASSER_OFFLINE=1`, or the
session budget (`GLASSER_BUDGET_USD`, default 0.25) is spent.

    g = Glasser(on_call=engine.sponsor_call)
    p = g.retail_params()   # {stores, prices, basket, cost, cached, sources}

Record the fallback set (about $0.03):

    uv run python -m lab.sponsors.glasser record
"""

from __future__ import annotations

import json
import os
import re
import statistics
import uuid
from typing import Optional

from lab.sponsors.calls import DATA, Reporter, SponsorCall, Timer, load_recorded, report, save_recorded, short_error

MCP_URL = "https://api.glasser.ai/mcp"
CACHE = DATA / "glasser_cache.json"
RECORDED = "glasser_retail.json"
TIMEOUT_S = 30
USE_CASE = ("Get real retail numbers (store counts, basket sizes, price levels) to calibrate a small "
            "synthetic retail dataset for analyst training.")
TICKERS = ("TGT",)  # Target discloses total_stores and traffic_growth
ITEMS = ("gallon of whole milk", "loaf of white bread", "ground coffee 12 oz", "paper towels 6 pack")
# Basket size is not disclosed by the KPI endpoint; this is a fixed planning value, labelled as such.
BASKET = {"avgBasketUsd": 38.0, "itemsPerBasket": 9, "source": "fixed value (not from Glasser)"}


class GlasserError(RuntimeError):
    pass


def parse_price(text) -> Optional[float]:
    m = re.search(r"(\d[\d,]*\.?\d*)", str(text or ""))
    return float(m.group(1).replace(",", "")) if m else None


class Glasser:
    def __init__(self, *, on_call: Reporter = None, offline: Optional[bool] = None, transport=None,
                 budget_usd: Optional[float] = None):
        from lab.env import load_env

        load_env()
        self.on_call = on_call
        self.offline = (os.environ.get("GLASSER_OFFLINE") == "1" or not os.environ.get("GLASSER_API_KEY")) \
            if offline is None else offline
        self._transport = transport  # tests pass a callable(tool, args) -> dict
        self.budget = float(os.environ.get("GLASSER_BUDGET_USD", "0.25")) if budget_usd is None else budget_usd
        self.spent = 0.0

    # -- transport --------------------------------------------------------------

    def _tool(self, name: str, args: dict) -> dict:
        if self._transport is not None:
            return self._transport(name, args)
        import httpx

        headers = {"Authorization": f"Bearer {os.environ['GLASSER_API_KEY']}", "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        body = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/call",
                "params": {"name": name, "arguments": args}}
        r = httpx.post(MCP_URL, headers=headers, json=body, timeout=TIMEOUT_S)
        if r.status_code != 200:
            raise GlasserError(f"http {r.status_code}")
        d = r.json()
        if "error" in d:
            raise GlasserError(f"rpc {d['error'].get('code')}")
        res = d.get("result", {})
        text = "".join(c.get("text", "") for c in res.get("content", []))
        if res.get("isError"):
            raise GlasserError("tool error")
        return json.loads(text)

    def run(self, provider: str, endpoint: str, input: dict, *, label: str, by: str = "system") -> dict:
        """One paid Run. Returns its output; reports cost and run link."""
        if self.spent >= self.budget:
            raise GlasserError("budget spent")
        t = Timer()
        try:
            r = self._tool("run", {"provider": provider, "endpoint": endpoint, "input": input,
                                   "idempotency_key": str(uuid.uuid4())})
            cost = float(r.get("charge_usd") or 0.0)
            self.spent += cost
            if r.get("status") != "COMPLETED":
                raise GlasserError(f"run {r.get('status')}")
            report(self.on_call, SponsorCall("glasser", "run", label, ms=t.ms, by=by, cost_usd=cost,
                                             trace=r.get("run_url")))
            return {"output": r.get("output") or {}, "cost": cost, "runUrl": r.get("run_url", "")}
        except Exception as exc:  # noqa: BLE001
            report(self.on_call, SponsorCall("glasser", "run", label, ok=False, ms=t.ms, by=by, fallback=True,
                                             error=short_error(exc)))
            raise

    # -- retail numbers ---------------------------------------------------------

    def store_kpis(self, ticker: str) -> dict:
        """{ticker, period, totalStores, trafficGrowthPct, comparableSalesGrowthPct, cost, source}."""
        r = self.run("financialdatasets", "/kpi/metrics", {"ticker": ticker, "period": "annual", "limit": 50},
                     label=f"Read store numbers for {ticker}")
        rows = r["output"].get("kpi_metrics", [])
        latest = max((m["period"] for m in rows), default="")
        pick = {m["metric_name"]: m["value"] for m in rows if m["period"] == latest}
        return {"ticker": ticker, "period": latest, "totalStores": pick.get("total_stores"),
                "trafficGrowthPct": pick.get("traffic_growth"),
                "comparableSalesGrowthPct": pick.get("comparable_store_sales_growth"),
                "cost": r["cost"], "source": r["runUrl"]}

    def price_level(self, item: str) -> dict:
        """{item, median, low, high, n, cost, source}: US Google Shopping prices, quartiles as low/high."""
        r = self.run("serper", "/shopping", {"q": item, "gl": "us"}, label=f"Priced {item}")
        prices = sorted(p for p in (parse_price(x.get("price")) for x in r["output"].get("shopping", [])) if p)
        if len(prices) >= 4:
            q1, med, q3 = statistics.quantiles(prices, n=4)
        else:
            q1 = med = q3 = statistics.median(prices) if prices else None
        rnd = (lambda v: round(v, 2) if v is not None else None)
        return {"item": item, "median": rnd(med), "low": rnd(q1), "high": rnd(q3), "n": len(prices),
                "cost": r["cost"], "source": r["runUrl"]}

    def retail_params(self, *, refresh: bool = False) -> dict:
        """{stores: [...], prices: [...], basket, cost, cached, sources}. Cached per day in data/."""
        if not refresh:
            cached = self._read_cache()
            if cached:
                return dict(cached, cached=True, cost=0.0)
        if not self.offline:
            try:
                out = {"stores": [self.store_kpis(t) for t in TICKERS],
                       "prices": [self.price_level(i) for i in ITEMS], "basket": BASKET}
                out["cost"] = round(sum(x["cost"] for x in out["stores"] + out["prices"]), 4)
                out["sources"] = [x["source"] for x in out["stores"] + out["prices"]]
                out["cached"] = False
                self._write_cache(out)
                return out
            except Exception:  # noqa: BLE001 - recorded numbers answer instead
                pass
        rec = load_recorded(RECORDED) or {"stores": [], "prices": [], "basket": BASKET, "sources": []}
        report(self.on_call, SponsorCall("glasser", "run", "Used recorded retail numbers", ms=0, fallback=True))
        return dict(rec, cached=True, cost=0.0)

    def _read_cache(self) -> Optional[dict]:
        try:
            return json.loads(CACHE.read_text())
        except (OSError, ValueError):
            return None

    def _write_cache(self, out: dict) -> None:
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(out, indent=1))
        except OSError:
            pass


def record() -> None:
    g = Glasser(offline=False, on_call=lambda c: print(c.event_data()))
    out = g.retail_params(refresh=True)
    if out.get("cached"):
        raise SystemExit("Glasser did not answer; nothing recorded")
    out = {k: v for k, v in out.items() if k != "cached"}
    print("saved", save_recorded(RECORDED, out), "cost", out["cost"])


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["record"]:
        record()
    else:
        print("usage: python -m lab.sponsors.glasser record")

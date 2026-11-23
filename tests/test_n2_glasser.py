"""Glasser: retail numbers through a fake transport, costs, budget and recorded fallback."""

import pytest

from lab.sponsors import glasser
from lab.sponsors.glasser import Glasser, parse_price


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(glasser, "CACHE", tmp_path / "glasser_cache.json")


def fake(fail=False):
    seen = []

    def transport(tool, args):
        seen.append((tool, args))
        if fail:
            raise ConnectionError("down")
        assert tool == "run" and args["idempotency_key"]
        if args["provider"] == "financialdatasets":
            out = {"kpi_metrics": [
                {"period": "FY 2025", "metric_name": "total_stores", "value": 1995},
                {"period": "FY 2025", "metric_name": "traffic_growth", "value": -2.2},
                {"period": "FY 2024", "metric_name": "total_stores", "value": 1978}]}
            return {"status": "COMPLETED", "output": out, "charge_usd": "0.02", "run_url": "https://g.test/r1"}
        out = {"shopping": [{"price": p} for p in ("$2.89", "$4.79", "$1,009.99", "$3.50", "n/a", "$5.00")]}
        return {"status": "COMPLETED", "output": out, "charge_usd": "0.002", "run_url": "https://g.test/r2"}

    transport.seen = seen
    return transport


def test_parse_price():
    assert parse_price("$1,009.99") == 1009.99 and parse_price("n/a") is None and parse_price(None) is None


def test_store_kpis_takes_latest_period():
    calls = []
    k = Glasser(on_call=calls.append, offline=False, transport=fake()).store_kpis("TGT")
    assert k["totalStores"] == 1995 and k["trafficGrowthPct"] == -2.2 and k["period"] == "FY 2025"
    assert calls[0].event_data()["cost"] == 0.02 and calls[0].trace == "https://g.test/r1"


def test_price_level_quartiles():
    p = Glasser(offline=False, transport=fake()).price_level("milk")
    assert p["n"] == 5 and p["low"] <= p["median"] <= p["high"] and p["median"] == 4.79


def test_retail_params_live_then_cached():
    t = fake()
    g = Glasser(offline=False, transport=t)
    out = g.retail_params()
    assert not out["cached"] and out["cost"] == round(0.02 + 0.002 * len(glasser.ITEMS), 4)
    assert out["basket"]["source"].startswith("fixed value")
    n = len(t.seen)
    again = g.retail_params()
    assert again["cached"] and again["cost"] == 0.0 and len(t.seen) == n


def test_down_uses_recorded_set():
    calls = []
    out = Glasser(on_call=calls.append, offline=False, transport=fake(fail=True)).retail_params()
    assert out["cached"] and out["stores"][0]["totalStores"] and len(out["prices"]) == len(glasser.ITEMS)
    assert calls[0].ok is False and calls[-1].fallback


def test_budget_stops_paid_runs():
    t = fake()
    g = Glasser(offline=False, transport=t, budget_usd=0.021)
    out = g.retail_params()
    assert out["cached"]  # second run would pass the budget, so the recorded set answered
    assert g.spent <= 0.022


@pytest.mark.live
def test_live_price_level():
    g = Glasser(offline=False)
    if not g._transport and not __import__("os").environ.get("GLASSER_API_KEY"):
        pytest.skip("no Glasser key")
    assert g.price_level("gallon of whole milk")["n"] > 0


# -- benchmark(): an agent buys one real fact -------------------------------------------------

def test_benchmark_basket_sums_items_and_reports_each_run():
    calls = []
    b = Glasser(on_call=calls.append, offline=False, transport=fake()).benchmark("basket", by="sam")
    n = len(glasser.ITEMS)
    assert b["unit"] == "USD" and b["value"] == round(4.79 * n, 2) and b["low"] <= b["value"] <= b["high"]
    assert b["cost"] == round(0.002 * n, 4) and not b["cached"] and b["trace"] == "https://g.test/r2"
    assert len(calls) == n and all(c.by == "sam" and c.event_data()["cost"] == 0.002 for c in calls)


def test_benchmark_retailer_kpi():
    calls = []
    k = Glasser(on_call=calls.append, offline=False, transport=fake()).benchmark("retailer_kpi", by="vale")
    assert k["value"] == 1995 and k["unit"] == "stores" and k["cost"] == 0.02 and k["trace"] == "https://g.test/r1"
    assert k["label"] == "Target stores, FY 2025 (traffic -2.2%)" and k["extra"]["trafficGrowthPct"] == -2.2
    assert calls[0].event_data()["trace"] == "https://g.test/r1"


def test_benchmark_repeat_is_free_in_session():
    t = fake()
    calls = []
    g = Glasser(on_call=calls.append, offline=False, transport=t)
    first = g.benchmark("retailer_kpi")
    again = g.benchmark("retailer_kpi")
    assert again["value"] == first["value"] and again["cost"] == 0.0 and len(t.seen) == 1
    assert calls[-1].count == 0 and calls[-1].event_data()["cost"] == 0.0 and calls[-1].trace == "https://g.test/r1"
    assert g.spent == 0.02


def test_benchmark_falls_back_to_recorded():
    calls = []
    for g in (Glasser(on_call=calls.append, offline=False, transport=fake(fail=True)), Glasser(offline=True)):
        b = g.benchmark("basket")
        k = g.benchmark("retailer_kpi", ticker="KR")  # not recorded: the recorded retailer answers
        assert b["cached"] and b["cost"] == 0.0 and b["value"] > 0 and b["trace"].startswith("https://app.glasser.ai/")
        assert k["cached"] and k["value"] and k["extra"]["ticker"] == "TGT"
    assert calls[-1].fallback


def test_benchmark_respects_budget_before_paying():
    t = fake()
    g = Glasser(offline=False, transport=t, budget_usd=0.019)
    k = g.benchmark("retailer_kpi")  # a $0.02 Run would pass the budget
    assert k["cached"] and t.seen == [] and g.spent == 0.0


def test_benchmark_unknown_kind():
    with pytest.raises(ValueError):
        Glasser(offline=True).benchmark("weather")

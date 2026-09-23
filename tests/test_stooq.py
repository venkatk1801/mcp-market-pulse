"""Tests for Stooq fetching/parsing with a mocked httpx (no network)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_pulse import market_hours, server

QUOTE_OK = (
    "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
    "AAPL.US,2026-09-22,21:59,238.10,240.55,237.40,239.80,51234567\n"
)

QUOTE_MISSING = (
    "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
    "ZZZZ.US,2026-09-22,21:59,N/D,N/D,N/D,N/D,N/D\n"
)


def _history_csv(n_days: int = 40) -> str:
    from datetime import date, timedelta

    lines = ["Date,Open,High,Low,Close,Volume"]
    # trading-ish days ending 2026-09-22; close drifts up 0.5/day
    end = date(2026, 9, 22)
    for i in range(n_days):
        day = (end - timedelta(days=n_days - 1 - i)).isoformat()
        close = 200.0 + 0.5 * i
        lines.append(
            f"{day},{close-1:.2f},{close+1:.2f},{close-2:.2f},{close:.2f},1000000"
        )
    return "\n".join(lines) + "\n"


class _FakeResp:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


def _fake_get(url, params=None, **kwargs):
    params = params or {}
    unknown = params.get("s") == "zzzz.us"
    if "q/l/" in url:  # quote endpoint
        return _FakeResp(QUOTE_MISSING if unknown else QUOTE_OK)
    if unknown:  # daily endpoint: header only -> no rows
        return _FakeResp("Date,Open,High,Low,Close,Volume\n")
    return _FakeResp(_history_csv())


@pytest.fixture(autouse=True)
def _mock_httpx(monkeypatch):
    monkeypatch.setattr("market_pulse.server.httpx.get", _fake_get)


def test_candidates_aliases():
    assert server._candidates("^GSPC") == ["^spx"]
    assert server._candidates("AAPL") == ["aapl.us"]
    assert server._candidates("aapl.us") == ["aapl.us"]
    assert server._candidates("BTC") == ["btcusd"]
    with pytest.raises(ValueError):
        server._candidates("   ")


def test_get_quote_parses_and_computes_change():
    q = server.get_quote("AAPL")
    assert q["symbol"] == "AAPL"
    assert q["source"] == "stooq_quote"
    assert q["price"] == pytest.approx(239.80)
    # previous daily close from fake history (2026-09-21 -> 200 + 0.5*38 = 219.0)
    assert q["previous_close"] == pytest.approx(219.00)
    assert q["change"] == pytest.approx(239.80 - 219.00)
    assert q["change_pct"] == pytest.approx(round((239.80 - 219.00) / 219.00 * 100, 2))
    assert q["change_basis"] == "previous_close"
    assert q["volume"] == 51234567


def test_get_quote_falls_back_to_daily_when_quote_endpoint_down(monkeypatch):
    def boom(url, params=None, **kwargs):
        if "q/l/" in url:
            raise RuntimeError("market data request failed: 404")
        return _fake_get(url, params, **kwargs)

    monkeypatch.setattr("market_pulse.server.httpx.get", boom)
    q = server.get_quote("AAPL")
    assert q["source"].startswith("stooq_daily")
    # latest daily bar: 2026-09-22 close 219.5; previous bar 219.0
    assert q["price"] == pytest.approx(219.50)
    assert q["previous_close"] == pytest.approx(219.00)
    assert q["change"] == pytest.approx(0.50)


def test_get_quote_unknown_symbol_raises():
    with pytest.raises(ValueError, match="No market data found"):
        server.get_quote("ZZZZ")


def test_get_history_returns_window():
    h = server.get_history("AAPL", days=30)
    assert h["count"] == 30
    assert len(h["rows"]) == 30
    assert h["rows"][0]["close"] == pytest.approx(200 + 0.5 * 10)  # 40-day series, last 30
    assert h["rows"][-1]["date"] == "2026-09-22"
    assert h["from"] == h["rows"][0]["date"]
    assert h["to"] == h["rows"][-1]["date"]


def test_get_history_unknown_symbol_raises():
    with pytest.raises(ValueError, match="No market data"):
        server.get_history("ZZZZ")


def test_indicator_rsi_uses_history():
    out = server.indicator("AAPL", "rsi")
    assert out["indicator"] == "RSI"
    assert out["period"] == 14
    assert out["data_points"] == 40
    assert 0 <= out["value"] <= 100


def test_indicator_sma_matches_math():
    out = server.indicator("AAPL", "sma")
    # fake series closes: 200, 200.5, ..., 219.5 ; SMA-20 of last 20 = avg of 210..219.5
    expected = sum(200 + 0.5 * i for i in range(20, 40)) / 20
    assert out["value"] == pytest.approx(expected, abs=0.01)


def test_indicator_unknown_kind():
    with pytest.raises(ValueError, match="unknown indicator"):
        server.indicator("AAPL", "macd")

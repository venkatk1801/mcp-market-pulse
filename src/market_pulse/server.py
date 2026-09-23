"""Market Pulse MCP server.

Exposes market-data tools over stdio using the official MCP Python SDK
(``MCPServer`` is the FastMCP successor in mcp>=2). Quotes and history come
from Stooq's free CSV endpoints -- real data, no API key required.

Run it directly (stdio transport)::

    python -m market_pulse.server

or point Claude Desktop at it (see README).
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, timedelta
from io import StringIO

import httpx
from mcp.server.mcpserver import MCPServer

from market_pulse import indicators, market_hours

server = MCPServer("market-pulse")

QUOTE_URL = "https://stooq.com/q/l/"
HISTORY_URL = "https://stooq.com/q/d/l/"
_TIMEOUT = 15.0

# Common aliases so "^GSPC", "SPX", "DJI" etc. just work.
_ALIASES = {
    "^gspc": "^spx",
    "spx": "^spx",
    "^dji": "^dji",
    "dji": "^dji",
    "^ixic": "^ndq",
    "ixic": "^ndq",
    "comp": "^ndq",
    "ndq": "^ndq",
    "rut": "^rut",
    "vix": "^vix",
    "btc": "btcusd",
    "eth": "ethusd",
}


def _candidates(symbol: str) -> list[str]:
    """Possible Stooq tickers for a user-supplied symbol, best first."""
    s = symbol.strip().lower().replace(" ", "")
    if not s:
        raise ValueError("symbol must not be empty")
    if s in _ALIASES:
        return [_ALIASES[s]]
    if s.startswith("^"):
        return [s]
    if "." in s:  # e.g. already "aapl.us"
        return [s]
    return [f"{s}.us"]


def _get(url: str, params: dict) -> str:
    try:
        resp = httpx.get(url, params=params, timeout=_TIMEOUT,
                         headers={"User-Agent": "mcp-market-pulse/0.1.0"})
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"market data request failed: {exc}") from exc
    return resp.text


def _rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(text.strip()))
    return [dict(r) for r in reader]


def _to_float(raw: str | None) -> float | None:
    if raw is None or raw.strip() in ("", "N/D"):
        return None
    return float(raw.replace(",", ""))


def _to_int(raw: str | None) -> int | None:
    value = _to_float(raw)
    return None if value is None else int(value)


def _fetch_history_rows(stooq_symbol: str, days: int) -> list[dict[str, str]]:
    """Daily OHLC rows (oldest first) for a Stooq ticker, or [] if unknown."""
    today = date.today()
    # Ask for extra days so weekends/holidays don't starve the window.
    d1 = (today - timedelta(days=days * 2 + 12)).strftime("%Y%m%d")
    d2 = today.strftime("%Y%m%d")
    text = _get(HISTORY_URL, {"s": stooq_symbol, "d1": d1, "d2": d2, "i": "d"})
    rows = [r for r in _rows(text) if _to_float(r.get("Close")) is not None]
    return rows


def _resolve(symbol: str, days: int = 45) -> tuple[str, list[dict[str, str]]]:
    """First candidate ticker with real history, else raise."""
    tried: list[str] = []
    for cand in _candidates(symbol):
        tried.append(cand)
        rows = _fetch_history_rows(cand, days)
        if rows:
            return cand, rows
    raise ValueError(
        f"No market data found for symbol {symbol!r} "
        f"(tried Stooq tickers: {', '.join(tried)}). "
        "Use a US ticker like AAPL, an index alias like ^GSPC, or a crypto pair like BTC."
    )


@server.tool()
def get_quote(symbol: str) -> dict:
    """Latest quote for a symbol: price, day change, OHLC and volume.

    Accepts US tickers (AAPL), index aliases (^GSPC, DJI, ^IXIC) and crypto
    pairs (BTC, ETH). Change is measured against the previous daily close.
    If Stooq's live quote endpoint is unreachable, falls back to the latest
    daily bar (noted in the ``source`` field).
    """
    symbol = symbol.strip()
    tried: list[str] = []
    snapshot: dict[str, str] | None = None
    stooq_symbol = ""
    for cand in _candidates(symbol):
        tried.append(cand)
        try:
            text = _get(QUOTE_URL, {"s": cand, "f": "sd2t2ohlcv", "h": "", "e": "csv"})
        except RuntimeError:
            # Quote endpoint down/blocked -- use the daily endpoint instead.
            break
        rows = _rows(text)
        if rows and _to_float(rows[0].get("Close")) is not None:
            snapshot, stooq_symbol = rows[0], cand
            break

    if snapshot is not None:
        return _quote_from_snapshot(symbol, stooq_symbol, snapshot)

    # Fallback: latest daily bar.
    stooq_symbol, rows = _resolve(symbol, 10)
    last = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None
    close = _to_float(last["Close"])
    assert close is not None
    prev_close = _to_float(prev["Close"]) if prev else None
    change_basis = "previous_daily_close"
    if prev_close is None:
        prev_close = _to_float(last.get("Open"))
        change_basis = "intraday_open"
    assert prev_close is not None
    change = close - prev_close
    return {
        "symbol": symbol.upper(),
        "stooq_symbol": stooq_symbol,
        "source": "stooq_daily (quote endpoint unavailable; latest daily bar)",
        "price": round(close, 2),
        "change": round(change, 2),
        "change_pct": round(change / prev_close * 100, 2),
        "change_basis": change_basis,
        "open": _to_float(last.get("Open")),
        "high": _to_float(last.get("High")),
        "low": _to_float(last.get("Low")),
        "previous_close": round(prev_close, 2),
        "volume": _to_int(last.get("Volume")),
        "as_of": last.get("Date", ""),
    }


def _quote_from_snapshot(symbol: str, stooq_symbol: str,
                         quote: dict[str, str]) -> dict:
    price = _to_float(quote["Close"])
    assert price is not None
    day = quote.get("Date", "")

    # Previous close from daily history; fall back to intraday open if needed.
    change_basis = "previous_close"
    prev_close = None
    hist = _fetch_history_rows(stooq_symbol, 10)
    earlier = [r for r in hist if r["Date"] < day]
    if earlier:
        prev_close = _to_float(earlier[-1]["Close"])
    if prev_close is None:
        prev_close = _to_float(quote.get("Open"))
        change_basis = "intraday_open"
    assert prev_close is not None

    change = price - prev_close
    return {
        "symbol": symbol.upper(),
        "stooq_symbol": stooq_symbol,
        "source": "stooq_quote",
        "price": round(price, 2),
        "change": round(change, 2),
        "change_pct": round(change / prev_close * 100, 2),
        "change_basis": change_basis,
        "open": _to_float(quote.get("Open")),
        "high": _to_float(quote.get("High")),
        "low": _to_float(quote.get("Low")),
        "previous_close": round(prev_close, 2),
        "volume": _to_int(quote.get("Volume")),
        "as_of": f"{quote.get('Date', '')} {quote.get('Time', '')}".strip(),
    }


@server.tool()
def get_history(symbol: str, days: int = 30) -> dict:
    """Daily OHLCV bars for a symbol, most recent ``days`` trading days.

    ``days`` is clamped to 1-365.
    """
    days = max(1, min(365, int(days)))
    stooq_symbol, rows = _resolve(symbol, days)

    def clean(r: dict[str, str]) -> dict:
        return {
            "date": r["Date"],
            "open": _to_float(r.get("Open")),
            "high": _to_float(r.get("High")),
            "low": _to_float(r.get("Low")),
            "close": _to_float(r.get("Close")),
            "volume": _to_int(r.get("Volume")),
        }

    window = [clean(r) for r in rows[-days:]]
    return {
        "symbol": symbol.strip().upper(),
        "stooq_symbol": stooq_symbol,
        "count": len(window),
        "from": window[0]["date"],
        "to": window[-1]["date"],
        "rows": window,
    }


@server.tool()
def indicator(symbol: str, kind: str = "rsi") -> dict:
    """Technical indicator for a symbol.

    ``kind``: "rsi" (RSI-14), "sma" (SMA-20) or "ema" (EMA-20).
    Returns the latest value plus the data window used.
    """
    key = kind.strip().lower()
    specs = {
        "rsi": ("RSI", 14, indicators.rsi, 60),
        "rsi14": ("RSI", 14, indicators.rsi, 60),
        "sma": ("SMA", 20, indicators.sma, 30),
        "sma20": ("SMA", 20, indicators.sma, 30),
        "ema": ("EMA", 20, indicators.ema, 60),
        "ema20": ("EMA", 20, indicators.ema, 60),
    }
    if key not in specs:
        raise ValueError(
            f"unknown indicator {kind!r}; choose one of: rsi, sma, ema"
        )
    name, period, fn, lookback = specs[key]
    stooq_symbol, rows = _resolve(symbol, lookback)
    closes = [_to_float(r["Close"]) for r in rows]
    closes = [c for c in closes if c is not None]
    value = fn(closes, period)
    return {
        "symbol": symbol.strip().upper(),
        "indicator": name,
        "period": period,
        "value": round(value, 2),
        "as_of": rows[-1]["Date"],
        "data_points": len(closes),
    }


@server.tool()
def market_status() -> dict:
    """Whether the US stock market (NYSE) is open right now, in ET.

    Returns open/closed plus the reason (regular session 09:30-16:00 ET,
    pre-market, after-hours, weekend or market holiday).
    """
    return market_hours.market_status()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="market-pulse-server",
        description="Market Pulse MCP server (stdio transport). "
                    "Tools: get_quote, get_history, indicator, market_status.",
    )
    parser.parse_args()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

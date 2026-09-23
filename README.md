# mcp-market-pulse

A [Model Context Protocol](https://modelcontextprotocol.io/) server that gives Claude
live market-data superpowers — plus a Claude-powered CLI client that answers
natural-language questions about stocks.

Ask things like **"is AAPL trending up? check the RSI"** and watch Claude call
real tools, read real prices, and reason over them.

```
You: is AAPL trending up? check the RSI
  [tool] indicator({"symbol": "AAPL", "kind": "rsi"})
  [tool] get_history({"symbol": "AAPL", "days": 30})
AAPL's RSI(14) is 62.4 — bullish momentum but not overbought (overbought is 70+).
Over the last 30 trading days it closed at $239.80, up from $219.00, with higher
highs through the window. Trend: up, momentum: strong but not extreme.
```

## Tools

| Tool | What it does |
|---|---|
| `get_quote(symbol)` | Latest price, day change vs previous close, OHLC, volume |
| `get_history(symbol, days=30)` | Daily OHLCV bars (up to 365 trading days) |
| `indicator(symbol, kind)` | `rsi` (RSI-14), `sma` (SMA-20), `ema` (EMA-20) — math implemented from scratch in `indicators.py` |
| `market_status()` | Whether the NYSE is open right now (ET, weekends + 2026 holidays) |

Symbol handling: bare US tickers (`AAPL`), index aliases (`^GSPC`, `DJI`, `^IXIC`),
and crypto (`BTC`, `ETH`) all resolve to the right Stooq ticker.

## Architecture

```
┌──────────┐   tool calls    ┌────────────┐   JSON-RPC    ┌────────────┐   HTTPS   ┌───────┐
│  Claude  │ ◄─────────────► │ MCP client │ ◄───────────► │ MCP server │ ◄───────► │ Stooq │
│ (Sonnet) │  Messages API   │ (client.py)│     stdio     │ (server.py)│   CSV API │       │
└──────────┘                 └────────────┘               └────────────┘           └───────┘
```

The server speaks MCP over stdio (any MCP host — Claude Desktop, Claude Code —
can use it). The bundled CLI client spawns the server itself and runs an
agentic loop: Claude decides which tools to call, reads the results, and
answers.

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/venkatk1801/mcp-market-pulse
cd mcp-market-pulse
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Use with Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`
on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "market-pulse": {
      "command": "/absolute/path/to/mcp-market-pulse/.venv/bin/market-pulse-server"
    }
  }
}
```

Restart Claude Desktop and the four tools appear in the 🔌 menu.

## Use the CLI client

The client needs an Anthropic API key:

```bash
cp .env.example .env   # then put your key in .env
# or: export ANTHROPIC_API_KEY=sk-ant-...
```

```bash
market-pulse "is NVDA overbought right now?"
market-pulse --interactive          # REPL mode
market-pulse --model claude-sonnet-4-5 "compare AAPL and MSFT this month"
```

## Example session

```
$ market-pulse "is AAPL trending up? check RSI"
  [tool] indicator({'symbol': 'AAPL', 'kind': 'rsi'})
  [tool] get_quote({'symbol': 'AAPL'})
  [tool] market_status({})
AAPL is at $239.80 (+2.3% on the day) with RSI(14) at 62.4. The market is
currently open. Price is above its 20-day average and momentum is bullish
without being overbought — the trend is up.
```

## Development

```bash
pytest            # 28 tests, no network (httpx is mocked)
```

Project layout:

```
src/market_pulse/
  server.py       MCP server (MCPServer from the official MCP Python SDK, stdio)
  client.py       agentic CLI client (Messages API tool-use loop over stdio)
  indicators.py   SMA / EMA / Wilder RSI, from scratch
  market_hours.py NYSE hours in America/New_York
tests/            indicator math, CSV parsing (mocked), market-hours logic
```

## Data source & limits

- Prices come from **Stooq's free CSV endpoints** — real market data, no API key.
  Quotes may be delayed ~15 minutes; daily bars are end-of-day.
- `get_quote` uses Stooq's quote endpoint and falls back to the latest daily bar
  if it's unreachable (the `source` field tells you which served the data).
- Change is measured against the previous daily close; after-hours quotes may
  look "stale" — that's the last print, not a bug.
- `market_status` covers regular NYSE hours 09:30–16:00 ET, weekends, and a
  static 2026 holiday list. Early closes (e.g. day after Thanksgiving) are not
  modeled.
- Not investment advice. This is a data pipe with a chatbot on top — do your
  own diligence.

## License

MIT — see [LICENSE](LICENSE).

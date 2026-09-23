"""Market Pulse CLI client.

Spawns the MCP server over stdio, exposes its tools to Claude, and runs an
agentic tool-use loop so you can ask natural-language market questions.

Requires ``ANTHROPIC_API_KEY`` in the environment (or a ``.env`` file).

Examples:
    market-pulse "is AAPL trending up? check the RSI"
    market-pulse --interactive
    market-pulse --model claude-sonnet-4-5 "compare AAPL and MSFT this month"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"

SYSTEM_PROMPT = (
    "You are a market analyst with live data tools. Answer concisely. "
    "Use get_quote for current prices, get_history for trends over time, "
    "indicator for RSI/SMA/EMA readings, and market_status for market hours. "
    "Interpret RSI: below 30 is oversold, above 70 is overbought. "
    "Always cite the numbers your tools returned. "
    "Never invent prices, dates or indicator values -- if a tool fails, say so."
)

MAX_ITERS = 12


def _anthropic_tools(session_tools) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.inputSchema,
        }
        for t in session_tools
    ]


def _tool_text(result) -> str:
    """Extract plain text from an MCP CallToolResult."""
    parts = []
    for block in result.content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
        else:
            parts.append(str(block))
    return "\n".join(parts) or "(empty tool result)"


async def ask(session: ClientSession, client: anthropic.Anthropic,
              model: str, max_tokens: int, prompt: str) -> str:
    """One agentic turn: Claude may call tools repeatedly until it answers."""
    tools = _anthropic_tools((await session.list_tools()).tools)
    messages: list[dict] = [{"role": "user", "content": prompt}]

    for _ in range(MAX_ITERS):
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )
        messages.append(
            {"role": "assistant", "content": [b for b in resp.content]}
        )

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            return "".join(b.text for b in resp.content if b.type == "text")

        results = []
        for tu in tool_uses:
            print(f"  [tool] {tu.name}({tu.input})", file=sys.stderr)
            try:
                out = await session.call_tool(tu.name, tu.input or {})
                text = _tool_text(out)
                is_error = bool(getattr(out, "isError", False))
            except Exception as exc:  # keep the loop alive on tool failure
                text, is_error = f"tool error: {exc}", True
            results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": text,
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": results})

    return "(stopped after too many tool steps without a final answer)"


async def _run(args: argparse.Namespace) -> int:
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "error: ANTHROPIC_API_KEY is not set.\n"
            "Set it in your environment or copy .env.example to .env and fill it in.",
            file=sys.stderr,
        )
        return 2

    client = anthropic.Anthropic(api_key=api_key)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "market_pulse.server"],
        env=env,
        cwd=str(PROJECT_ROOT),
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def one(prompt: str) -> None:
                print(await ask(session, client, args.model, args.max_tokens, prompt))

            if args.interactive or not args.prompt:
                print("Market Pulse -- ask about stocks (type 'exit' to quit).")
                while True:
                    try:
                        prompt = input("\n> ").strip()
                    except (EOFError, KeyboardInterrupt):
                        print()
                        break
                    if prompt.lower() in {"exit", "quit"}:
                        break
                    if prompt:
                        await one(prompt)
            else:
                await one(args.prompt)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="market-pulse",
        description="Ask Claude natural-language market questions via the Market Pulse MCP server.",
    )
    p.add_argument("prompt", nargs="?", help="question to ask (omit for interactive mode)")
    p.add_argument("-i", "--interactive", action="store_true",
                   help="interactive REPL mode")
    p.add_argument("--model", default=os.environ.get("MODEL", "claude-sonnet-4-5"),
                   help="Anthropic model id (default: claude-sonnet-4-5)")
    p.add_argument("--max-tokens", type=int, default=1024,
                   help="max output tokens per Claude turn")
    return p


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()

"""Technical indicator math, implemented from scratch.

All functions take a list of closing prices (oldest first) and return a float.
They raise :class:`ValueError` when there is not enough data.
"""

from __future__ import annotations


def sma(values: list[float], period: int) -> float:
    """Simple moving average of the last ``period`` values."""
    _require(values, period)
    return sum(values[-period:]) / period


def ema(values: list[float], period: int) -> float:
    """Exponential moving average of the last ``period`` values.

    Seeded with the SMA of the first ``period`` closes, then smoothed with
    Wilder's multiplier ``k = 2 / (period + 1)`` over the remaining closes.
    """
    _require(values, period)
    k = 2 / (period + 1)
    avg = sum(values[:period]) / period  # seed with SMA
    for price in values[period:]:
        avg = price * k + avg * (1 - k)
    return avg


def rsi(values: list[float], period: int = 14) -> float:
    """Relative Strength Index using Wilder's smoothing.

    Needs at least ``period + 1`` closes. Returns a value in ``[0, 100]``:
    100 when every move was up, 0 when every move was down, and a smoothed
    momentum reading in between.
    """
    if len(values) < period + 1:
        raise ValueError(
            f"RSI({period}) needs at least {period + 1} closes, got {len(values)}"
        )

    gains = [max(values[i] - values[i - 1], 0.0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0.0) for i in range(1, len(values))]

    # Seed with simple averages over the first `period` deltas.
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder's recursive smoothing over the rest.
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _require(values: list[float], period: int) -> None:
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    if len(values) < period:
        raise ValueError(
            f"need at least {period} closes, got {len(values)}"
        )

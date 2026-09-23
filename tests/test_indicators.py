"""Tests for indicator math, using hand-computable synthetic data."""

import pytest

from market_pulse import indicators


def test_sma_basic():
    assert indicators.sma([1, 2, 3, 4, 5], 5) == 3.0
    assert indicators.sma([1, 2, 3, 4, 5], 3) == pytest.approx(4.0)


def test_sma_uses_last_n_values():
    assert indicators.sma([10, 10, 10, 1, 2, 3], 3) == pytest.approx(2.0)


def test_sma_not_enough_data():
    with pytest.raises(ValueError):
        indicators.sma([1, 2], 5)


def test_ema_basic():
    # period 1 -> EMA is just the last price
    assert indicators.ema([5, 6, 7], 1) == pytest.approx(7.0)
    # flat series -> EMA equals the constant
    assert indicators.ema([4.0] * 10, 5) == pytest.approx(4.0)


def test_rsi_all_gains_is_100():
    # every move up: no losses -> RSI hits the ceiling
    assert indicators.rsi([10, 11, 12, 13, 14, 15], period=3) == 100.0


def test_rsi_all_losses_is_0():
    assert indicators.rsi([15, 14, 13, 12, 11, 10], period=3) == 0.0


def test_rsi_flat_series_is_100():
    # avg_loss == 0 with zero gains is a degenerate "no downside" series
    assert indicators.rsi([7.0] * 20, period=14) == 100.0


def test_rsi_known_series():
    # Classic Wilder RSI example; the textbook answer after the first
    # 15 closes (14 deltas) is ~70.46.
    closes = [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
        46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41,
        46.22, 46.03,
    ]
    assert indicators.rsi(closes[:15], period=14) == pytest.approx(70.46, abs=0.05)
    # Full 20 closes, smoothed through the last 5 days -> ~63.29
    assert indicators.rsi(closes, period=14) == pytest.approx(63.29, abs=0.05)


def test_rsi_bounded():
    closes = [100 + (i % 7) * (-1) ** i for i in range(60)]
    value = indicators.rsi(closes, period=14)
    assert 0.0 <= value <= 100.0


def test_rsi_not_enough_data():
    with pytest.raises(ValueError):
        indicators.rsi([1, 2, 3], period=14)

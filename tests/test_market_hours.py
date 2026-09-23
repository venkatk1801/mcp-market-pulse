"""Tests for market_status with frozen datetimes (no real clock)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from market_pulse import market_hours

ET = ZoneInfo("America/New_York")


def test_open_regular_session():
    # Monday 2026-09-21 10:00 ET
    s = market_hours.market_status(datetime(2026, 9, 21, 10, 0, tzinfo=ET))
    assert s["open"] is True
    assert s["status"] == "open"


def test_closed_weekend():
    # Saturday 2026-09-26 12:00 ET
    s = market_hours.market_status(datetime(2026, 9, 26, 12, 0, tzinfo=ET))
    assert s["open"] is False
    assert s["reason"] == "weekend"


def test_closed_pre_market():
    s = market_hours.market_status(datetime(2026, 9, 21, 8, 0, tzinfo=ET))
    assert s["open"] is False
    assert "pre-market" in s["reason"]


def test_closed_after_hours():
    s = market_hours.market_status(datetime(2026, 9, 25, 16, 30, tzinfo=ET))
    assert s["open"] is False
    assert "after-hours" in s["reason"]


def test_open_boundary_930():
    s = market_hours.market_status(datetime(2026, 9, 21, 9, 30, tzinfo=ET))
    assert s["open"] is True


def test_closed_boundary_1600():
    s = market_hours.market_status(datetime(2026, 9, 21, 16, 0, tzinfo=ET))
    assert s["open"] is False


def test_closed_holiday_christmas():
    # 2026-12-25 is a Friday
    s = market_hours.market_status(datetime(2026, 12, 25, 11, 0, tzinfo=ET))
    assert s["open"] is False
    assert s["reason"] == "market holiday"


def test_naive_datetime_assumed_et():
    s = market_hours.market_status(datetime(2026, 9, 21, 10, 0))
    assert s["open"] is True


def test_other_timezone_converted():
    # 14:00 UTC == 10:00 ET (EDT) on 2026-09-21
    s = market_hours.market_status(
        datetime(2026, 9, 21, 14, 0, tzinfo=ZoneInfo("UTC"))
    )
    assert s["open"] is True

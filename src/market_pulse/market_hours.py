"""US equity market hours (NYSE) in America/New_York.

Regular session: 09:30-16:00 ET, Monday-Friday. Weekends and a small static
list of US market holidays are treated as closed. Holiday coverage is
best-effort (see ``MARKET_HOLIDAYS``); add more dates as needed.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

OPEN = time(9, 30)
CLOSE = time(16, 0)

# NYSE full-day closures for 2026. (Early closes, e.g. day after
# Thanksgiving / Christmas Eve, are treated as regular days here.)
MARKET_HOLIDAYS: frozenset[date] = frozenset(
    {
        date(2026, 1, 1),   # New Year's Day
        date(2026, 1, 19),  # Martin Luther King Jr. Day
        date(2026, 2, 16),  # Presidents Day
        date(2026, 4, 3),   # Good Friday
        date(2026, 5, 25),  # Memorial Day
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),   # Independence Day (observed)
        date(2026, 9, 7),   # Labor Day
        date(2026, 11, 26), # Thanksgiving
        date(2026, 12, 25), # Christmas Day
    }
)


def market_status(now: datetime | None = None) -> dict:
    """Return whether the US market is open right now.

    ``now`` is injectable for tests; it may be naive (assumed ET) or aware
    (converted to ET).
    """
    now = now or datetime.now(ET)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    else:
        now = now.astimezone(ET)

    today = now.date()
    stamp = now.strftime("%Y-%m-%d %H:%M %Z")

    if today.weekday() >= 5:
        return _closed("weekend", stamp)
    if today in MARKET_HOLIDAYS:
        return _closed("market holiday", stamp)
    if now.time() < OPEN:
        return _closed("pre-market (opens 09:30 ET)", stamp)
    if now.time() >= CLOSE:
        return _closed("after-hours (opens 09:30 ET next trading day)", stamp)
    return {
        "open": True,
        "status": "open",
        "reason": "regular session 09:30-16:00 ET",
        "et_time": stamp,
    }


def _closed(reason: str, stamp: str) -> dict:
    return {"open": False, "status": "closed", "reason": reason, "et_time": stamp}

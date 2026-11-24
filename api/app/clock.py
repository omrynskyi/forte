"""The only place the app asks what time it is. Tests monkeypatch `clock.now`.

All timestamps are stored as UTC `timestamptz`. Business dates (pay dates, cutoffs, "today")
are in the company's time zone, which is always America/Los_Angeles for the MVP (California only).
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def now() -> datetime:
    return datetime.now(UTC)


def today_pacific() -> date:
    return now().astimezone(PACIFIC).date()

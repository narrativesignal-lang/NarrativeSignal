"""Product wall-clock timezone: US Eastern (America/New_York, DST-aware).

Cron evaluation, monitoring buckets, and Celery Beat schedules use this zone unless noted.
UTC may still be used for auth token expiry and similar internals.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

PLATFORM_TZ_NAME = "America/New_York"
PLATFORM_TZ = ZoneInfo(PLATFORM_TZ_NAME)


def now_platform() -> datetime:
    """Current time in America/New_York (Eastern with DST)."""
    return datetime.now(PLATFORM_TZ)

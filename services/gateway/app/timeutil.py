from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Current UTC time truncated to whole seconds (tz-aware)."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def format_ts(dt: datetime) -> str:
    """Format as YYYY-MM-DDTHH:MM:SSZ."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    dt = dt.replace(microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(value: str) -> datetime:
    """Parse YYYY-MM-DDTHH:MM:SSZ into aware UTC datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0)


def add_seconds(dt: datetime, seconds: int) -> datetime:
    from datetime import timedelta

    return (dt + timedelta(seconds=seconds)).replace(microsecond=0)

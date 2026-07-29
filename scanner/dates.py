"""
Timestamp parsing and the timeframe window.

Job boards return timestamps in half a dozen shapes. Everything is normalised
to timezone-aware UTC here so the window comparison is never naive-vs-aware.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value) -> datetime | None:
    """Parse the timestamp formats the supported boards actually emit."""

    if value is None or value == "":
        return None

    # Epoch milliseconds (Lever) or seconds.
    if isinstance(value, (int, float)):
        seconds = float(value)

        if seconds > 1e11:
            seconds /= 1000.0

        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()

    if not text:
        return None

    if text.isdigit():
        return parse_timestamp(int(text))

    # ISO 8601, with or without a trailing Z.
    candidate = text.replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        parsed = None

    if parsed is None:
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def window_start(lookback_hours: float) -> datetime:
    """The cutoff for a lookback window. Postings older than this are out."""

    return now_utc() - timedelta(hours=float(lookback_hours))


def within_window(value, lookback_hours: float) -> bool:
    """
    Is this posting inside the chosen window?

    A posting with no parseable timestamp is treated as OUT. Boards that omit
    a date are usually re-listing something old, and letting them through
    silently defeats the point of picking a timeframe.
    """

    posted = parse_timestamp(value)

    if posted is None:
        return False

    return posted >= window_start(lookback_hours)


def age_hours(value) -> float | None:
    posted = parse_timestamp(value)

    if posted is None:
        return None

    delta = now_utc() - posted

    return round(delta.total_seconds() / 3600.0, 2)


def iso(value: datetime | None = None) -> str:
    return (value or now_utc()).isoformat()

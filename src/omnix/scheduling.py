"""Native schedule parsing for OMNI-X's SQLite-owned TaskService."""
from __future__ import annotations

import datetime as dt
import re
import time


def parse_schedule(value: str) -> tuple[str, float, float | None]:
    """Parse a one-time ISO timestamp or recurring interval (s/m/h/d)."""
    raw = value.strip()
    match = re.fullmatch(r"(?:every\s+)?(\d+(?:\.\d+)?)([smhd])", raw.lower())
    if match:
        amount, unit = float(match.group(1)), match.group(2)
        seconds = amount * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
        if seconds <= 0:
            raise ValueError("schedule interval must be positive")
        return "interval", time.time() + seconds, seconds
    try:
        when = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("schedule must be a positive interval such as 'every 1m' or an ISO timestamp") from exc
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return "once", when.timestamp(), None

"""Native schedule parsing for OMNI-X's SQLite-owned TaskService."""
from __future__ import annotations

import datetime as dt
import re
import time


def parse_schedule(value: str) -> tuple[str, float, float | None]:
    """Parse a one-time ISO timestamp or recurring interval (s/m/h/d)."""
    raw = value.strip()
    fields = raw.split()
    if len(fields) == 5:
        limits = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
        sets = []
        for field, (low, high) in zip(fields, limits):
            values = set()
            for part in field.split(","):
                base, slash, step_text = part.partition("/")
                if slash and (not step_text.isdigit() or int(step_text) < 1):
                    raise ValueError("invalid cron step")
                step = int(step_text) if slash else 1
                if base == "*":
                    start, end = low, high
                elif re.fullmatch(r"\d+-\d+", base):
                    start, end = map(int, base.split("-"))
                elif base.isdigit():
                    start = end = int(base)
                else:
                    raise ValueError("invalid cron field")
                if start < low or end > high or start > end:
                    raise ValueError("cron field out of range")
                values.update(range(start, end + 1, step))
            sets.append(values)
        candidate = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
        for _ in range(60 * 24 * 366 * 5):
            weekday = (candidate.weekday() + 1) % 7
            day_match = candidate.day in sets[2]
            week_match = weekday in sets[4] or (weekday == 0 and 7 in sets[4])
            day_ok = (day_match or week_match) if fields[2] != "*" and fields[4] != "*" else (day_match and week_match)
            if candidate.minute in sets[0] and candidate.hour in sets[1] and candidate.month in sets[3] and day_ok:
                return "cron", candidate.timestamp(), None
            candidate += dt.timedelta(minutes=1)
        raise ValueError("cron expression has no occurrence within five years")
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

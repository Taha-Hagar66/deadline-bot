"""Turn what a user types ("in 2h", "25.11.2026 14:00") into a datetime."""
import re
from datetime import datetime, time, timedelta

UNITS = {"m": "minutes", "min": "minutes", "h": "hours", "d": "days", "w": "weeks"}
RELATIVE = re.compile(r"(\d+)\s*(min|m|h|d|w)\b")
DATE_FORMATS = ["%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d", "%d.%m.%Y"]

HELP = 'Try "in 2h", "in 3d 4h", "2026-11-25 14:00" or "25.11.2026" (date only means 23:59).'


def parse_when(text: str, now: datetime) -> datetime:
    """Return the moment `text` refers to, in the same timezone as `now`.

    Raises ValueError with a friendly message if it can't be understood
    or is in the past.
    """
    text = text.strip().lower()

    if text.startswith("in "):
        parts = RELATIVE.findall(text[3:])
        leftover = RELATIVE.sub("", text[3:]).strip()
        if not parts or leftover:
            raise ValueError(f"I didn't understand '{text}'. {HELP}")
        delta = timedelta()
        for amount, unit in parts:
            delta += timedelta(**{UNITS[unit]: int(amount)})
        if delta < timedelta(minutes=1):
            raise ValueError("Pick a time at least 1 minute from now.")
        return now + delta

    for fmt in DATE_FORMATS:
        try:
            when = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if "%H" not in fmt:  # date only: end of that day
            when = datetime.combine(when.date(), time(23, 59))
        when = when.replace(tzinfo=now.tzinfo)
        if when <= now:
            raise ValueError("That time is already in the past.")
        return when

    raise ValueError(f"I didn't understand '{text}'. {HELP}")

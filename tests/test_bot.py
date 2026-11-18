from datetime import datetime, timedelta, timezone

import pytest

from deadline_bot.store import DAY, Store
from deadline_bot.timeparse import parse_when

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone(timedelta(hours=1)))


@pytest.mark.parametrize("text, expected", [
    ("in 30m", NOW + timedelta(minutes=30)),
    ("in 2h", NOW + timedelta(hours=2)),
    ("in 3d 4h", NOW + timedelta(days=3, hours=4)),
    ("In 1w", NOW + timedelta(weeks=1)),
    ("2026-11-25 14:00", NOW.replace(day=25, hour=14)),
    ("25.11.2026 14:00", NOW.replace(day=25, hour=14)),
    ("25.11.2026", NOW.replace(day=25, hour=23, minute=59)),
])
def test_parse_when_understands_formats(text, expected):
    assert parse_when(text, NOW) == expected


@pytest.mark.parametrize("text", ["tomorrow", "in 2 lightyears", "in", "1.1.2020"])
def test_parse_when_rejects_bad_or_past_input(text):
    with pytest.raises(ValueError):
        parse_when(text, NOW)


def test_store_reminder_flow():
    s = Store(":memory:")  # temporary in-memory database
    now = 1_000_000
    far = s.add(user_id=1, channel_id=9, title="Essay", due=now + 3 * DAY, now=now)
    soon = s.add(user_id=1, channel_id=9, title="Quiz", due=now + 3600, now=now)

    assert [d.title for d in s.upcoming(1)] == ["Quiz", "Essay"]
    # "Quiz" is under a day away, so it never gets a 24h warning.
    assert s.needing_warning(now) == []
    assert [d.id for d in s.needing_warning(now + 2 * DAY)] == [far]
    assert [d.id for d in s.due_now(now + 3600)] == [soon]

    assert not s.remove(far, user_id=2)  # can't delete someone else's
    assert s.remove(far, user_id=1)
    assert [d.title for d in s.upcoming(1)] == ["Quiz"]

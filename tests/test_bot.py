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


@pytest.mark.parametrize("text", ["in 0m", "in 0h 0d"])
def test_parse_when_rejects_zero_delay(text):
    with pytest.raises(ValueError):
        parse_when(text, NOW)


def test_parse_when_uses_the_users_timezone():
    from zoneinfo import ZoneInfo
    vienna_now = datetime(2026, 11, 18, 12, 0, tzinfo=ZoneInfo("Europe/Vienna"))
    due = parse_when("25.11.2026 14:00", vienna_now)
    # 14:00 in Vienna (winter, UTC+1) is 13:00 UTC, no matter where the bot runs.
    assert due.astimezone(timezone.utc).hour == 13


def test_store_remembers_timezones():
    s = Store(":memory:")
    assert s.get_timezone(1) is None
    s.set_timezone(1, "Europe/Vienna")
    s.set_timezone(1, "Asia/Tokyo")  # changing it overwrites
    assert s.get_timezone(1) == "Asia/Tokyo"


def test_fit_lines_stays_under_discords_limit():
    from deadline_bot import MAX_MESSAGE, fit_lines
    lines = [f"**#{i}** " + "x" * 100 for i in range(50)]
    text = fit_lines(lines)
    assert len(text) <= MAX_MESSAGE
    assert text.endswith("more.")
    assert fit_lines(["a", "b"]) == "a\nb"


def test_bot_pings_nobody_by_default():
    from deadline_bot import DeadlineBot
    bot = DeadlineBot(Store(":memory:"), None, timezone.utc)
    mentions = bot.allowed_mentions
    assert not mentions.everyone and not mentions.roles and not mentions.users

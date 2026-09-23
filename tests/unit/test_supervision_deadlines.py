"""Supervisor-set deadlines: the follow-up rule is pure and each stage fires once; registry reminders are configuration."""
from datetime import date

from services.supervision.deadlines import _period_end, reminders, stage_for


def test_follow_up_stages():
    r = {"before_due_days": 14, "after_due_days": 1}
    due = date(2026, 4, 30)
    assert stage_for(due, date(2026, 3, 1), r) is None
    assert stage_for(due, date(2026, 4, 16), r) == "reminder"
    assert stage_for(due, date(2026, 4, 30), r) == "reminder"     # on the day: still a reminder
    assert stage_for(due, date(2026, 5, 1), r) == "overdue"


def test_reminder_windows_come_from_the_registry():
    r = reminders()
    assert r["before_due_days"] > 0 and r["after_due_days"] >= 0


def test_period_label_to_period_end():
    assert _period_end("FY2025") == date(2025, 12, 31) and _period_end("2024") == date(2024, 12, 31)


def test_period_label_with_quarter_suffix_keeps_the_real_year():
    """Regression for the 2026-09-23 bug: stripping all digits from '2026-Q3' first gives '20263', whose LAST
    4 digits are '0263' — a valid-looking but wrong date (year 263) that silently passed every downstream
    check until caught live. Must extract the first 4-digit run instead."""
    assert _period_end("2026-Q3") == date(2026, 12, 31)
    assert _period_end("Q3 2026") == date(2026, 12, 31)

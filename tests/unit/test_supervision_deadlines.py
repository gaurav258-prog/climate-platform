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

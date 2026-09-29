"""Supervisor-set deadlines: the follow-up rule is pure and each stage fires once; registry reminders are configuration."""
from datetime import date

import pytest

from services.supervision.deadlines import canonical_period, reminders, stage_for


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


def test_a_period_is_a_financial_year_with_a_derived_label():
    assert canonical_period("FY2025") == ("FY2025", date(2025, 12, 31))
    assert canonical_period("2024") == ("FY2024", date(2024, 12, 31))
    assert canonical_period(" fy2026 ") == ("FY2026", date(2026, 12, 31))


@pytest.mark.parametrize("label", ["2026-Q3", "Q3 2026", "FY26", "20263", ""])
def test_anything_but_a_financial_year_is_refused(label):
    """'2026-Q3' was once accepted and became an annual period ending 31 December labelled as a quarter (found in
    the 2026-09-29 walkthrough); before that, the digits were mis-read as year 263. The calendar is annual."""
    with pytest.raises(ValueError, match="not a financial year"):
        canonical_period(label)

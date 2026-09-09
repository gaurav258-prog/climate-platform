"""Trend and timeliness rules are pure and say nothing a single period cannot support."""
from datetime import date

from services.supervision.trend import classify, pivot_cells


def test_pivot_reports_change_only_where_two_periods_exist():
    periods = [{"period_label": "FY2024", "cells": {"ES|D": {"geography": "ES", "sector": "D", "gross_carrying_amount_eur": 100, "sensitive_physical_eur": 40},
                                                   "FR|D": {"geography": "FR", "sector": "D", "gross_carrying_amount_eur": 50, "sensitive_physical_eur": 5}}},
               {"period_label": "FY2025", "cells": {"ES|D": {"geography": "ES", "sector": "D", "gross_carrying_amount_eur": 120, "sensitive_physical_eur": 72},
                                                   "IT|C": {"geography": "IT", "sector": "C", "gross_carrying_amount_eur": 10, "sensitive_physical_eur": 1}}}]
    rows = {r["key"]: r for r in pivot_cells(periods)}
    assert rows["ES|D"]["share_pct"] == {"FY2024": 40.0, "FY2025": 60.0} and rows["ES|D"]["change_pp"] == 20.0 and rows["ES|D"]["moved"]
    assert rows["FR|D"]["change_pp"] is None and not rows["FR|D"]["moved"] and rows["FR|D"]["in_periods"] == ["FY2024"]
    assert rows["IT|C"]["change_pp"] is None
    assert pivot_cells(periods)[0]["key"] == "ES|D"          # biggest move first


def test_timeliness_states():
    today = date(2026, 9, 9)
    assert classify(date(2026, 3, 31), date(2026, 3, 20), today) == ("filed_on_time", 11)
    assert classify(date(2026, 3, 31), date(2026, 4, 10), today) == ("filed_late", 10)
    assert classify(date(2026, 3, 31), None, today) == ("outstanding_overdue", 162)
    assert classify(date(2026, 12, 31), None, today) == ("not_yet_due", 113)
    assert classify(None, None, today) == ("no_due_date", None) and classify(None, date(2026, 1, 1), today) == ("filed", None)

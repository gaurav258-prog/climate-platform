"""A reporting period is its end and its kind (E354): a financial year, or the first half of one.

Every report was filed for a financial year until Pillar 3 ESG's semi-annual disclosure: large institutions disclose the
information of Article 449a CRR 'on a semi-annual basis' (Regulation (EU) No 575/2013 Art. 433a(1)(b)(xv)), at the
reference date of their financial reports 'for the corresponding period' (Arts 433, 434(2)) — the half-yearly financial
report covers 'the first six months of the financial year' (Directive 2004/109/EC Art. 5(1), read through CRR Art.
4(1)(149)), and EBA Q&A 2022_6444 (final, 30 Jun 2023) aligns the Part Eight reference date with the financial reports'.

A period's label is derived from its end and kind, never typed: 'FY2026' for a financial year ending in 2026, 'FY2026-H1'
for the first half of the financial year ending in 2026 (the half ends six months before the year). The database checks
the same rule on filings and obligations (LABEL_SQL) and keeps a half-year to the reports that owe one (HALF_YEAR_REPORTS).
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

FINANCIAL_YEAR, HALF_YEAR = "financial_year", "half_year"
KINDS = (FINANCIAL_YEAR, HALF_YEAR)
# the reports an act owes for a half-year (services.governance.crr_filers: Pillar 3 ESG of a semi-annual discloser)
HALF_YEAR_REPORTS = frozenset({"bank_p3esg"})
WORDS = {FINANCIAL_YEAR: "Financial year", HALF_YEAR: "First half of the financial year"}

# the label rule in SQL, for the CHECK constraints (migration p3_semiannual_20261031) — the same as label()
LABEL_SQL = ("CASE WHEN period_kind = 'half_year' "
             "THEN 'FY' || EXTRACT(YEAR FROM period_end + INTERVAL '6 months')::int || '-H1' "
             "ELSE 'FY' || EXTRACT(YEAR FROM period_end)::int END")


class PeriodError(ValueError):
    """A period kind the platform does not know."""


def check_kind(kind: str | None) -> str:
    k = kind or FINANCIAL_YEAR
    if k not in KINDS:
        raise PeriodError(f"a reporting period is one of {', '.join(KINDS)}")
    return k


def add_months(d: date, months: int) -> date:
    """d moved by whole months; a month end stays a month end (31 Dec − 6 months = 30 June)."""
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    last = calendar.monthrange(y, m)[1]
    month_end = d.day == calendar.monthrange(d.year, d.month)[1]
    return date(y, m, last if month_end else min(d.day, last))


def financial_year_end(end: date, kind: str = FINANCIAL_YEAR) -> date:
    """The end of the financial year the period belongs to."""
    return add_months(end, 6) if check_kind(kind) == HALF_YEAR else end


def half_year_end(fy_end: date) -> date:
    """The end of the first six months of the financial year ending fy_end."""
    return add_months(fy_end, -6)


def start(end: date, kind: str = FINANCIAL_YEAR) -> date:
    """The first day of the period: a financial year runs twelve months to its end, its first half six."""
    return add_months(end, -6 if check_kind(kind) == HALF_YEAR else -12) + timedelta(days=1)


def label(end: date, kind: str = FINANCIAL_YEAR) -> str:
    """'FY2026' or 'FY2026-H1' — derived, never typed (the database checks LABEL_SQL)."""
    if check_kind(kind) == HALF_YEAR:
        return f"FY{financial_year_end(end, kind).year}-H1"
    return f"FY{end.year}"


def year_before(reference_date: date) -> tuple[date, date]:
    """The year prior to a disclosure reference date, both ends included — the window of a flow KPI ('new exposures
    that have been incurred during the year prior to the disclosure reference date', EBA Q&A 2024_7082; Delegated
    Regulation (EU) 2021/2178 Annex V, 1.1.2(b)), whatever the period's kind (E355)."""
    return add_months(reference_date, -12) + timedelta(days=1), reference_date


def view(end: date, kind: str = FINANCIAL_YEAR) -> dict:
    """The period as the snapshot and the screens carry it."""
    k = check_kind(kind)
    return {"end": end.isoformat(), "kind": k, "label": label(end, k), "start": start(end, k).isoformat(),
            "words": WORDS[k]}

"""A reporting period is its end and kind (services.governance.periods, E354) — and a flow KPI's window is the year prior
to the disclosure reference date whatever the period's kind (E355).

The database's label rule is checked against periods.label in tests/integration/test_e2e_p3_semiannual.py.
"""
from __future__ import annotations

import ast
import inspect
from datetime import date

import pytest

from services.governance import periods as P


@pytest.mark.parametrize("end, kind, label, start", [
    (date(2026, 12, 31), "financial_year", "FY2026", date(2026, 1, 1)),
    (date(2026, 6, 30), "half_year", "FY2026-H1", date(2026, 1, 1)),        # the first half of FY2026
    (date(2026, 3, 31), "financial_year", "FY2026", date(2025, 4, 1)),      # a financial year ending in March
    (date(2025, 9, 30), "half_year", "FY2026-H1", date(2025, 4, 1)),        # ... and its first half
    (date(2025, 12, 31), "half_year", "FY2026-H1", date(2025, 7, 1)),       # a financial year ending in June
    (date(2026, 2, 28), "half_year", "FY2026-H1", date(2025, 9, 1)),        # ending in August
])
def test_a_period_is_labelled_and_started_from_its_end_and_kind(end, kind, label, start):
    assert P.label(end, kind) == label and P.start(end, kind) == start
    assert P.view(end, kind) == {"end": end.isoformat(), "kind": kind, "label": label, "start": start.isoformat(),
                                 "words": P.WORDS[kind]}


def test_the_half_year_ends_six_months_before_its_financial_year():
    assert P.half_year_end(date(2026, 12, 31)) == date(2026, 6, 30)
    assert P.half_year_end(date(2027, 3, 31)) == date(2026, 9, 30)
    assert P.half_year_end(date(2026, 8, 31)) == date(2026, 2, 28)          # a month end stays a month end
    assert P.financial_year_end(date(2026, 6, 30), P.HALF_YEAR) == date(2026, 12, 31)
    assert P.financial_year_end(date(2026, 12, 31)) == date(2026, 12, 31)


def test_an_unknown_kind_is_refused():
    with pytest.raises(P.PeriodError):
        P.label(date(2026, 6, 30), "quarter")
    assert P.check_kind(None) == P.FINANCIAL_YEAR


def test_a_half_year_is_only_for_the_reports_that_owe_one():
    from services.governance.filings import FRAMEWORKS
    assert P.HALF_YEAR_REPORTS == {"bank_p3esg"} and P.HALF_YEAR_REPORTS <= set(FRAMEWORKS)


def test_the_flow_window_is_the_year_before_the_reference_date():
    assert P.year_before(date(2026, 12, 31)) == (date(2026, 1, 1), date(2026, 12, 31))
    assert P.year_before(date(2026, 6, 30)) == (date(2025, 7, 1), date(2026, 6, 30))
    assert P.year_before(date(2026, 3, 31)) == (date(2025, 4, 1), date(2026, 3, 31))


def _assets(origination: str) -> list[dict]:
    return [{"outstanding_loan_balance_eur": 100, "country": "DE", "hazards": [], "nace_code": "64.19",
             "counterparty_sector": "credit_institution", "loan_origination_date": origination,
             "counterparty_taxonomy_kpi": {"turnover:ccm": {"eligible": 100, "aligned": 100}}}]


@pytest.mark.parametrize("origination, new", [("2025-07-01", True), ("2025-12-15", True), ("2026-06-30", True),
                                              ("2025-06-30", False), ("2026-07-01", False)])
def test_a_half_years_gar_flow_counts_the_year_before_it(origination, new):
    """EBA Q&A 2024_7082 (final, 15 Nov 2024): 'only new exposures that have been incurred during the year prior to the
    disclosure reference date' — at 30 June 2026 that is 1 July 2025 to 30 June 2026, not 1 January 2026 on (E355)."""
    import services.regspec as R
    from services.governance import pillar3_gar
    spec = R.load("bank_p3esg", next(s["version"] for s in R.versions("bank_p3esg") if s["status"] == "adopted"))
    out = pillar3_gar.build(spec, _assets(origination), date(2026, 6, 30))
    assert out["counts"]["new_in_period"] == (1 if new else 0)
    assert out["counts"]["period"] == ["2025-07-01", "2026-06-30"]


def test_no_flow_window_starts_on_the_first_of_january():
    """The Pillar 3 and the EU Taxonomy GAR builders take their flow window from periods.year_before, never from
    1 January of the period's year (the fault of E355: a half-year or a financial year not ending in December counted
    the wrong exposures)."""
    from services.governance import pillar3_gar, taxonomy_gar
    for mod in (pillar3_gar, taxonomy_gar):
        tree = ast.parse(inspect.getsource(mod))
        jan = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "date"
               and len(n.args) == 3 and all(isinstance(a, ast.Constant) and a.value == 1 for a in n.args[1:])]
        assert jan == [], mod.__name__
        assert "year_before" in inspect.getsource(mod), mod.__name__


def test_every_filing_matched_to_an_obligation_by_period_end_also_matches_its_kind():
    """A half-year and a financial year can end on the same date (a financial year ending in June, the first half of one
    ending in December): every SQL in services/ and api/ that matches one period row to another by end date compares the
    kind too (E354) — a new one without it fails here."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    pair = re.compile(r"\b(\w+)\.period_end\s*=\s*(\w+)\.period_end\b")
    missing = []
    for path in [*root.glob("services/**/*.py"), *root.glob("api/**/*.py")]:
        src = path.read_text()
        for m in pair.finditer(src):
            a, b = m.group(1), m.group(2)
            near = src[max(0, m.start() - 300): m.end() + 300]
            if not re.search(rf"\b{a}\.period_kind\s*=\s*{b}\.period_kind\b|\b{b}\.period_kind\s*=\s*{a}\.period_kind\b", near):
                missing.append(f"{path.relative_to(root)}: {m.group(0)}")
    assert missing == [], missing

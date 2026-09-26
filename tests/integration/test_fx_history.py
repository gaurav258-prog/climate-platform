"""FX rates are versioned (multi-currency phase 2): a corrected or removed rate is kept in append-only history; an
unchanged re-send is not logged; rate_changes_since finds corrections to the rates a filing used."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from core.db.session import get_session
from services.reference.fx import rate_changes_since

pytestmark = pytest.mark.integration
KEY = ("XTS", date(2026, 6, 30), "ecb", "reference_daily")


def test_corrections_are_kept_and_found_unchanged_resends_are_not():
    with get_session() as s:
        try:
            s.execute(text("DELETE FROM fx_rates WHERE ccy = 'XTS'"))
            s.execute(text("""INSERT INTO fx_rates (ccy, rate_date, eur_per_unit, units_per_eur, source, basis, fetched_at)
                              VALUES ('XTS', '2026-06-30', 0.1, 10, 'ecb', 'reference_daily', now())"""))
            t0 = s.execute(text("SELECT clock_timestamp()")).scalar()
            s.execute(text("UPDATE fx_rates SET fetched_at = now() WHERE ccy = 'XTS'"))                  # re-sent, same value
            assert rate_changes_since(s, t0, [KEY]) == []
            s.execute(text("UPDATE fx_rates SET units_per_eur = 11, eur_per_unit = 1.0/11 WHERE ccy = 'XTS'"))   # corrected
            s.execute(text("DELETE FROM fx_rates WHERE ccy = 'XTS'"))                                    # withdrawn
            got = rate_changes_since(s, t0, [KEY, ("XTS", date(2026, 6, 29), "ecb", "reference_daily")])
            assert [(g["change"], g["was"], g["now"]) for g in got] == [("corrected", 10.0, 11.0), ("removed", 11.0, None)]
        finally:
            s.rollback()


def test_history_is_append_only():
    with get_session() as s:
        try:
            s.execute(text("""INSERT INTO fx_rate_history (ccy, rate_date, source, basis, units_per_eur, change)
                              VALUES ('XTS', '2026-06-30', 'ecb', 'reference_daily', 10, 'corrected')"""))
            with pytest.raises(DBAPIError, match="append-only"):
                s.execute(text("DELETE FROM fx_rate_history WHERE ccy = 'XTS'"))
        finally:
            s.rollback()

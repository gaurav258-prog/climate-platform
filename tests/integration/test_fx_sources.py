"""The FX source order and staleness rule (services/reference/fx.py rate_for), with the ISO test currency XTS, inside a
rolled-back transaction."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.reference.fx import FxError, rate_for
from services.reference.imf_fx import cross_check

pytestmark = pytest.mark.integration
D = date(2026, 9, 26)


def _rate(s, d, src, basis, units):
    s.execute(text("""INSERT INTO fx_rates (ccy, rate_date, eur_per_unit, units_per_eur, source, basis)
                      VALUES ('XTS', :d, :e, :u, :s, :b)"""), {"d": d, "e": 1 / units, "u": units, "s": src, "b": basis})


@pytest.fixture()
def s():
    with get_session() as s:
        s.execute(text("DELETE FROM fx_rates WHERE ccy = 'XTS'"))
        s.execute(text("DELETE FROM fx_pegs WHERE ccy = 'XTS'"))
        try:
            yield s
        finally:
            s.rollback()


def test_fresh_ecb_wins_over_imf(s):
    _rate(s, date(2026, 9, 25), "ecb", "reference_daily", 10.0)
    _rate(s, date(2026, 8, 31), "imf", "month_end", 11.0)
    r = rate_for(s, "XTS", D)
    assert (r["source"], r["units_per_eur"], r["stale"]) == ("ecb", 10.0, False)


def test_stale_ecb_falls_through_to_fresh_imf(s):
    _rate(s, date(2022, 3, 1), "ecb", "reference_daily", 10.0)       # the ECB stopped quoting it
    _rate(s, date(2026, 8, 31), "imf", "month_end", 11.0)
    r = rate_for(s, "XTS", D)
    assert (r["source"], r["basis"], r["age_days"], r["stale"]) == ("imf", "month_end", 26, False)


def test_a_peg_beats_the_imf_and_is_never_stale(s):
    _rate(s, date(2026, 8, 31), "imf", "month_end", 11.0)
    s.execute(text("INSERT INTO fx_pegs VALUES ('XTS', 12.5, '2000-01-01', NULL, 'test treaty')"))
    r = rate_for(s, "XTS", D)
    assert (r["source"], r["units_per_eur"], r["stale"]) == ("peg", 12.5, False) and "test treaty" in r["note"]


def test_nothing_fresh_returns_the_freshest_marked_stale(s):
    _rate(s, date(2026, 1, 31), "imf", "month_end", 11.0)
    _rate(s, date(2025, 1, 2), "ecb", "reference_daily", 10.0)
    r = rate_for(s, "XTS", D)
    assert (r["source"], r["stale"]) == ("imf", True) and "limit 62" in r["note"]


def test_the_monthly_average_is_never_used_for_a_spot_conversion(s):
    _rate(s, date(2026, 8, 31), "imf", "period_average", 11.0)
    with pytest.raises(FxError):                                      # an average is not a spot rate: no guess
        rate_for(s, "XTS", D)


def test_a_date_before_any_rate_uses_the_first_later_spot_rate_marked_stale(s):
    _rate(s, date(2026, 10, 1), "ecb", "reference_daily", 10.0)
    r = rate_for(s, "XTS", D)
    assert r["stale"] is True and r["rate_date"] == "2026-10-01" and "earliest later" in r["note"]


def test_unknown_currency_is_never_guessed(s):
    with pytest.raises(FxError):
        rate_for(s, "XTS", D)


def test_a_misfiled_series_is_refused_by_the_cross_check(s):
    for m, d in enumerate([date(2026, 5, 29), date(2026, 6, 30), date(2026, 7, 31)]):
        _rate(s, d, "ecb", "reference_daily", 1.14)
    rows = [("XTS", d, "month_end", 150.0 + m, "HTI") for m, d in enumerate([date(2026, 5, 31), date(2026, 6, 30), date(2026, 7, 31)])]
    bad = cross_check(s, rows)
    assert "XTS" in bad and "not the same currency" in bad["XTS"]

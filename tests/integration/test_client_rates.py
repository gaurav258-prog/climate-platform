"""An organisation's own exchange rates (multi-currency decision 4): used first for its own amounts, always compared
with the official rate; beyond its tolerance → a second person (intake) or refused (direct inputs). Append-only.
Runs in rolled-back transactions."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from core.db.session import get_session
from services.intake import pipeline
from services.intake.catalog import TEMPLATES
from services.intake.money import MoneyError, convert_amount
from services.reference import client_fx
from services.reference.fx import rate_for
from tests.integration.test_intake_pipeline import BANK_ORG, _rows

pytestmark = pytest.mark.integration
BOOK = date(2026, 6, 30)


def _ecb_usd(s):
    return rate_for(s, "USD", BOOK)["units_per_eur"]


def test_own_rate_within_tolerance_is_used_and_compared():
    with get_session() as s:
        try:
            out = client_fx.submit(s, BANK_ORG, [{"currency": "usd", "rate_date": "2026-06-30",
                                                  "units_per_eur": _ecb_usd(s) * 1.004}], None)       # 0.4% off
            assert out["n_accepted"] == 1 and out["accepted"][0]["difference_pct"] == pytest.approx(0.4, abs=0.01)
            c = convert_amount(s, 1_000_000, "USD", BOOK, org_id=BANK_ORG)
            assert c["rate"]["source"] == "client" and c["rate"]["difference_pct"] == pytest.approx(0.4, abs=0.01)
            assert c["eur"] == pytest.approx(round(1e6 / (_ecb_usd(s) * 1.004), 2))
            # another organisation is not affected
            other = s.execute(text("SELECT org_id::text FROM organizations WHERE org_id <> CAST(:o AS uuid) LIMIT 1"),
                              {"o": BANK_ORG}).scalar()
            assert convert_amount(s, 1, "USD", BOOK, org_id=other)["rate"]["source"] == "ecb"
        finally:
            s.rollback()


def test_own_rate_beyond_tolerance_is_refused_directly_and_needs_a_second_person_in_intake():
    with get_session() as s:
        try:
            client_fx.submit(s, BANK_ORG, [{"currency": "USD", "rate_date": "2026-06-30", "units_per_eur": _ecb_usd(s) * 1.05}], None)
            with pytest.raises(MoneyError, match="beyond your 1% tolerance"):
                convert_amount(s, 1_000_000, "USD", BOOK, org_id=BANK_ORG)
            tag = uuid.uuid4().hex[:8]
            df = pd.DataFrame([{**r, "external_ref": f"{tag}-{i}"} for i, r in enumerate(_rows(tag, n=3))])
            ctl = pipeline._run_controls(s, BANK_ORG, TEMPLATES["bank_assets"], uuid.uuid4().hex, df, None,
                                         money_ctx={"currency": "USD", "book_date": BOOK, "field_currency": {},
                                                    "org_id": BANK_ORG, "flow_policy": "period_average"})
            assert ctl["controls"]["gate"]["status"] == "needs_signoff"
            assert any(r.startswith("Currency:") and "5.00% apart" in r for r in ctl["controls"]["gate"]["reasons"])
        finally:
            s.rollback()


def test_an_own_average_applies_only_to_its_exact_period_and_old_closings_do_not_stand_in():
    with get_session() as s:
        try:
            start = BOOK - timedelta(days=364)
            client_fx.submit(s, BANK_ORG, [{"currency": "USD", "basis": "period_average", "period_start": start.isoformat(),
                                            "rate_date": "2026-06-30", "units_per_eur": 1.1662},
                                           {"currency": "USD", "rate_date": "2026-06-01", "units_per_eur": 1.13}], None)
            flow = convert_amount(s, 1000, "USD", BOOK, flow=True, org_id=BANK_ORG)
            assert flow["rate"]["source"] == "client" and flow["rate"]["units_per_eur"] == pytest.approx(1.1662)
            # the own closing rate of 1 June is 29 days before the book date: too old, the official closing applies
            assert convert_amount(s, 1000, "USD", BOOK, org_id=BANK_ORG)["rate"]["source"] == "ecb"
        finally:
            s.rollback()


def test_submissions_are_checked_and_append_only():
    with get_session() as s:
        try:
            out = client_fx.submit(s, BANK_ORG, [{"currency": "ZZZ", "rate_date": "2026-06-30", "units_per_eur": 1},
                                                 {"currency": "USD", "rate_date": "2999-01-01", "units_per_eur": 1},
                                                 {"currency": "USD", "rate_date": "2026-06-30", "units_per_eur": -2},
                                                 {"currency": "USD", "rate_date": "2026-06-30", "units_per_eur": 1.14,
                                                  "basis": "period_average"}], None)
            assert out["n_accepted"] == 0 and [r["row"] for r in out["refused"]] == [1, 2, 3, 4]
            client_fx.submit(s, BANK_ORG, [{"currency": "USD", "rate_date": "2026-06-30", "units_per_eur": 1.14}], None)
            with pytest.raises(DBAPIError, match="append-only"):
                s.execute(text("UPDATE fx_client_rates SET units_per_eur = 2 WHERE org_id = CAST(:o AS uuid)"), {"o": BANK_ORG})
        finally:
            s.rollback()

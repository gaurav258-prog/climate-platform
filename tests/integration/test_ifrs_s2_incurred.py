"""IFRS S2 ¶16(a) actual-incurred-loss disclosure — submit, retrieve, honest gap. Requires PostgreSQL."""
import pytest
from sqlalchemy import text

import services.governance.ifrs_s2_incurred as I
from core.db.session import get_session

IBERIA = "22222222-2222-4222-8222-222222222222"


def _u(s, email):
    return str(s.execute(text("SELECT user_id FROM users WHERE email=:e"), {"e": email}).scalar())


@pytest.mark.integration
def test_not_yet_supplied_when_nothing_submitted_for_a_fresh_org():
    with get_session() as s:
        # an org with no rows at all -- use a scratch org id that never gets incurred-loss rows
        summary = I.incurred_loss_summary(s, "99999999-9999-4999-8999-999999999999")
        assert summary["status"] == "not_yet_supplied"
        assert summary["by_peril"] == [] and summary["by_period"] == []
        assert "16(a)" in summary["regulation"]
        s.rollback()


@pytest.mark.integration
def test_submit_then_retrieve_and_summarize():
    with get_session() as s:
        maker = _u(s, "admin@iberia.demo")
        res = I.submit_incurred_loss(s, IBERIA, "2025-01-01", "2025-12-31", "flood",
                                      12_000_000, net_incurred_loss_eur=9_500_000,
                                      source="client", created_by=maker)
        assert res["loss_id"]

        records = I.list_incurred_losses(s, IBERIA)
        assert any(r["loss_id"] == res["loss_id"] for r in records)
        row = next(r for r in records if r["loss_id"] == res["loss_id"])
        assert row["peril"] == "flood" and row["gross_incurred_loss_eur"] == 12_000_000
        assert row["net_incurred_loss_eur"] == 9_500_000

        summary = I.incurred_loss_summary(s, IBERIA)
        assert summary["status"] == "supplied"
        assert summary["total_gross_incurred_loss_eur"] >= 12_000_000
        flood = next(p for p in summary["by_peril"] if p["peril"] == "flood")
        assert flood["gross_incurred_loss_eur"] >= 12_000_000
        s.rollback()


@pytest.mark.integration
def test_second_submission_same_period_and_peril_is_additive_not_overwrite():
    with get_session() as s:
        maker = _u(s, "admin@iberia.demo")
        before = len(I.list_incurred_losses(s, IBERIA))
        I.submit_incurred_loss(s, IBERIA, "2025-01-01", "2025-12-31", "windstorm", 1_000_000, created_by=maker)
        I.submit_incurred_loss(s, IBERIA, "2025-01-01", "2025-12-31", "windstorm", 500_000, created_by=maker)
        after = len(I.list_incurred_losses(s, IBERIA))
        assert after == before + 2       # both kept as separate records -- restated history stays visible
        summary = I.incurred_loss_summary(s, IBERIA)
        ws = next(p for p in summary["by_peril"] if p["peril"] == "windstorm")
        assert ws["gross_incurred_loss_eur"] >= 1_500_000
        s.rollback()


@pytest.mark.integration
def test_modeled_figures_shown_alongside_actual_when_passed():
    with get_session() as s:
        maker = _u(s, "admin@iberia.demo")
        I.submit_incurred_loss(s, IBERIA, "2025-01-01", "2025-12-31", "flood", 1_000_000, created_by=maker)
        modeled = {"total_expected_annual_loss_eur": 800_000, "standard_formula_natcat_scr_eur": 5_000_000}
        summary = I.incurred_loss_summary(s, IBERIA, modeled=modeled)
        assert summary["modeled"] == modeled
        assert "comparison_note" in summary
        s.rollback()


@pytest.mark.integration
def test_submit_with_region_and_modelled_round_trips():
    """SASB FN-IN-450a.2 disaggregation — end-to-end through submit_incurred_loss/list/summarize."""
    with get_session() as s:
        maker = _u(s, "admin@iberia.demo")
        res = I.submit_incurred_loss(s, IBERIA, "2025-01-01", "2025-12-31", "flood",
                                      3_000_000, source="client", created_by=maker,
                                      region="Germany", modelled=True)
        records = I.list_incurred_losses(s, IBERIA)
        row = next(r for r in records if r["loss_id"] == res["loss_id"])
        assert row["region"] == "Germany" and row["modelled"] is True

        summary = I.incurred_loss_summary(s, IBERIA)
        de = next((g for g in summary["by_region"] if g["region"] == "Germany"), None)
        assert de is not None and de["gross_incurred_loss_eur"] >= 3_000_000
        s.rollback()

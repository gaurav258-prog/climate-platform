"""Lane 2 — provided datapoints: submit → reconcile → 4-eyes attest. Requires PostgreSQL."""
import pytest
from sqlalchemy import text

from core.db.session import get_session
import services.governance.provided_data as P

BANK_ORG = "11111111-1111-4111-8111-111111111111"


def _u(s, email):
    return str(s.execute(text("SELECT user_id FROM users WHERE email=:e"), {"e": email}).scalar())


def test_only_provided_lane_keys_accepted():
    with get_session() as s:
        maker = _u(s, "admin@meridian.demo")
        # phys_risk is a 'compute'-lane datapoint → cannot be provided
        with pytest.raises(P.ProvidedError):
            P.submit(s, BANK_ORG, maker, framework="bank_tcfd", datapoint_key="phys_risk", value_num=1)
        # an unknown key is refused
        with pytest.raises(P.ProvidedError):
            P.submit(s, BANK_ORG, maker, framework="bank_tcfd", datapoint_key="nope", value_num=1)
        s.rollback()


def test_providable_lists_only_provided_lane():
    dps = P.providable("bank_tcfd")
    keys = {d["key"] for d in dps}
    assert "taxonomy_aligned" in keys        # provided lane
    assert "phys_risk" not in keys           # compute lane
    assert "tcfd_narrative" not in keys       # report lane


@pytest.mark.integration
def test_submit_reconciles_and_attests():
    with get_session() as s:
        maker = _u(s, "admin@meridian.demo")
        checker = _u(s, "approver@meridian.demo")
        # financed emissions has a Tellumen baseline → provided value reconciles with a delta
        r = P.submit(s, BANK_ORG, maker, framework="bank_tcfd", datapoint_key="financed_emissions",
                     value_num=1_700_000, source="client", provider_name="Audited PCAF", data_vintage="2025-12-31")
        assert r["status"] == "pending" and r["approval_request_id"]
        assert r["tellumen_value"] is not None and r["delta_pct"] is not None    # reconciled against our number
        # it appears in the list as pending
        lst = P.provided_list(s, BANK_ORG, "bank_tcfd")
        row = next(x for x in lst if x["datapoint_key"] == "financed_emissions")
        assert row["status"] == "pending" and row["source"] == "client"
        # attest via the same path the approvals router calls
        payload = s.execute(text("SELECT payload FROM approval_requests WHERE request_id=:r"),
                            {"r": r["approval_request_id"]}).scalar()
        applied = P.attest(s, BANK_ORG, payload, "approved", checker)
        assert applied["status"] == "attested"
        row2 = next(x for x in P.provided_list(s, BANK_ORG, "bank_tcfd") if x["datapoint_key"] == "financed_emissions")
        assert row2["status"] == "attested" and row2["decided_by"] == "approver@meridian.demo"
        s.rollback()


@pytest.mark.integration
def test_submit_without_baseline_stores_as_provided():
    with get_session() as s:
        maker = _u(s, "admin@meridian.demo")
        # GAR alignment has no Tellumen counterpart → stored as provided, no divergence
        r = P.submit(s, BANK_ORG, maker, framework="bank_tcfd", datapoint_key="taxonomy_aligned",
                     value_num=18.5, unit="%", source="client")
        assert r["status"] == "pending" and r["tellumen_value"] is None and r["delta_pct"] is None
        assert "No Tellumen counterpart" in (r["recon_note"] or "")
        s.rollback()

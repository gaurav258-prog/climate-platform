"""filings.form_view() must never crash on the 3 frameworks whose build_form() returns row/section-shaped
groups instead of datapoint-shaped ones (2026-09-24 fix, platform-wide E2E audit): insurer_solvency,
reit_taxonomy, assetmgmt_tcfd (filing_form.py's _insurer_solvency_form / _reit_taxonomy_form /
_assetmgmt_tcfd_form all return [{"section","rows"}], not [{"group","datapoints"}]). form_view()'s
override-merge loop and its dps_by_key comprehension both assumed every group had "datapoints"
unconditionally — a real KeyError -> 500 on the filing review screen for EVERY filing of these 3
frameworks, reproduced live during the audit and confirmed for 2 of the 3 against real frozen filings.

Requires PostgreSQL. Non-polluting: rolls back / uses throwaway future periods.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.governance import filings as F
from services.governance.report_snapshots import create_snapshot

INSURER_ORG = "22222222-2222-4222-8222-222222222222"    # Iberia Mutual (demo)
REIT_ORG = "33333333-3333-4333-8333-333333333333"        # Stellar Logistics REIT (demo)
AM_ORG = "44444444-4444-4444-8444-444444444444"           # Nordkap Asset Management (demo)


def _actor(s, email):
    return str(s.execute(text("SELECT user_id FROM users WHERE email=:e"), {"e": email}).scalar())


@pytest.mark.integration
def test_form_view_insurer_solvency_does_not_crash():
    with get_session() as s:
        fid = s.execute(text("""
            SELECT filing_id::text FROM regulatory_filing
            WHERE org_id = :o AND framework = 'insurer_solvency' AND snapshot_id IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
        """), {"o": INSURER_ORG}).scalar()
        assert fid, "fixture: a real frozen insurer_solvency filing must exist for this org"
        out = F.form_view(s, INSURER_ORG, fid)   # must not raise KeyError
        assert out is not None
        assert any(g.get("section", "").startswith("Nat-Cat SCR") for g in out["groups"])
        s.rollback()


@pytest.mark.integration
def test_form_view_reit_taxonomy_does_not_crash():
    with get_session() as s:
        fid = s.execute(text("""
            SELECT filing_id::text FROM regulatory_filing
            WHERE org_id = :o AND framework = 'reit_taxonomy' AND snapshot_id IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
        """), {"o": REIT_ORG}).scalar()
        assert fid, "fixture: a real frozen reit_taxonomy filing must exist for this org"
        out = F.form_view(s, REIT_ORG, fid)   # must not raise KeyError
        assert out is not None
        assert any("Turnover KPI" in g.get("section", "") for g in out["groups"])
        s.rollback()


@pytest.mark.integration
def test_form_view_assetmgmt_tcfd_does_not_crash():
    with get_session() as s:
        u = _actor(s, "admin@nordkap.demo")
        snap = create_snapshot(s, AM_ORG, "assetmgmt_tcfd", u)
        fid = s.execute(text("""
            INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, created_by)
            VALUES (:o, 'assetmgmt_tcfd', '2097-12-31', 'FY2097-formtest', 'draft', :snap, :u)
            RETURNING filing_id::text
        """), {"o": AM_ORG, "snap": snap["snapshot_id"], "u": u}).scalar()
        out = F.form_view(s, AM_ORG, fid)   # must not raise KeyError
        assert out is not None
        assert any("Portfolio climate value-at-risk" in g.get("section", "") for g in out["groups"])
        s.rollback()


@pytest.mark.integration
def test_form_view_still_merges_overrides_for_datapoint_shaped_frameworks():
    """Regression guard: the fix must not disable override-merging for the frameworks it always worked for."""
    with get_session() as s:
        u = _actor(s, "admin@meridian.demo")
        snap = create_snapshot(s, "11111111-1111-4111-8111-111111111111", "bank_tcfd", u)
        fid = s.execute(text("""
            INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, created_by)
            VALUES (:o, 'bank_tcfd', '2096-12-31', 'FY2096-formtest', 'draft', :snap, :u) RETURNING filing_id::text
        """), {"o": "11111111-1111-4111-8111-111111111111", "snap": snap["snapshot_id"], "u": u}).scalar()
        out = F.form_view(s, "11111111-1111-4111-8111-111111111111", fid)
        assert out is not None
        assert any(g.get("group") == "Headline exposure" for g in out["groups"])
        s.rollback()


@pytest.mark.integration
def test_full_http_flow_no_500_for_all_three_frameworks():
    """End-to-end through the real router — the exact symptom the audit reproduced (curl -> 500)."""
    from fastapi.testclient import TestClient
    from api.main import app
    client = TestClient(app, raise_server_exceptions=False)

    insurer_tok = client.post("/v1/auth/login", json={"email": "admin@iberia.demo", "password": "Demo!admin1"}).json()["access_token"]
    reit_tok = client.post("/v1/auth/login", json={"email": "admin@stellar.demo", "password": "Demo!admin1"}).json()["access_token"]

    with get_session() as s:
        ins_fid = s.execute(text("""
            SELECT filing_id::text FROM regulatory_filing WHERE org_id=:o AND framework='insurer_solvency'
            AND snapshot_id IS NOT NULL ORDER BY created_at DESC LIMIT 1
        """), {"o": INSURER_ORG}).scalar()
        reit_fid = s.execute(text("""
            SELECT filing_id::text FROM regulatory_filing WHERE org_id=:o AND framework='reit_taxonomy'
            AND snapshot_id IS NOT NULL ORDER BY created_at DESC LIMIT 1
        """), {"o": REIT_ORG}).scalar()

    r1 = client.get(f"/v1/filings/{ins_fid}/form", headers={"Authorization": f"Bearer {insurer_tok}"})
    assert r1.status_code == 200, r1.text

    r2 = client.get(f"/v1/filings/{reit_fid}/form", headers={"Authorization": f"Bearer {reit_tok}"})
    assert r2.status_code == 200, r2.text

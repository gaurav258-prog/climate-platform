"""Cross-report reconciliation — shared figures agree across sibling filings, and it never blocks."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.governance.filing_crosscheck import cross_report_findings, _shared_figures

BANK_ORG = "11111111-1111-4111-8111-111111111111"


def test_shared_figures_extracts_bank_headline():
    payload = {"rollup": {"total_value_eur": 1000, "value_at_risk_eur": 300},
               "financed_emissions_tco2e": {"scope1": 10, "scope2": 5, "scope3": 50}}
    figs = _shared_figures("bank_tcfd", payload)
    assert figs["total book value"] == 1000 and figs["value at risk"] == 300
    assert figs["financed emissions (tCO₂e)"] == 65


def test_shared_figures_sfdr_and_unknown():
    assert _shared_figures("sfdr_pai", {"entity": {"total_value_eur": 5000}}) == {"NAV in scope": 5000}
    assert _shared_figures("bank_tcfd", {}) == {}          # nothing to share → empty, not a crash
    assert _shared_figures("mystery", {"x": 1}) == {}


@pytest.mark.integration
def test_restatement_reconciles_with_its_same_period_predecessor():
    """The accepted Meridian filing (a restatement) must reconcile its headline with the superseded v1
    of the same period — and produce no blocking cross-report finding."""
    with get_session() as s:
        from services.governance.filings import get_filing
        fid = s.execute(text(
            "SELECT filing_id::text FROM regulatory_filing WHERE org_id=:o AND framework='bank_tcfd' "
            "AND status='accepted' ORDER BY created_at DESC LIMIT 1"), {"o": BANK_ORG}).scalar()
        if not fid:
            pytest.skip("no accepted bank filing")
        filing = get_filing(s, BANK_ORG, fid, with_payload=True)
        findings = cross_report_findings(s, BANK_ORG, filing)
        assert findings, "a filing with a same-period sibling should produce reconciliation findings"
        # cross-report is advisory only — nothing here may be a blocking severity
        assert all(f["severity"] in ("warning", "info") for f in findings)
        same = [f for f in findings if ":same:" in f["rule"]]
        assert same and all(f["passed"] for f in same), "restatement should reconcile with its predecessor"

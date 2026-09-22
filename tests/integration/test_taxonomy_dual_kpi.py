"""Dual EU Taxonomy KPI — turnover-based AND CapEx-based Taxonomy-aligned %, shown
separately per Annex III/IV of Del. Reg. (EU) 2021/2178. Requires PostgreSQL.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from ml.regulatory.sfdr_pai import _taxonomy_rollup

DEMO_ORG = "44444444-4444-4444-8444-444444444444"


def _seed(s, *, aligned_turnover=None, aligned_capex=None, dnsh_ok=None, safeguards_ok=None):
    fid = str(s.execute(text(
        "INSERT INTO funds (org_id,name,fund_type,sfdr_classification) "
        "VALUES (:o,'TEST Dual KPI Fund','fund','article_8') RETURNING fund_id"), {"o": DEMO_ORG}).scalar())
    iid = str(s.execute(text(
        "INSERT INTO issuers (name,issuer_type,country,nace_code,source) "
        "VALUES ('Dual KPI Issuer','corporate','DE','35.11','manual') RETURNING issuer_id")).scalar())
    sid = str(s.execute(text(
        "INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
        "VALUES ('DE00DUALKPI1','Dual KPI Sec',:i,'equity','manual') RETURNING security_id"), {"i": iid}).scalar())
    s.execute(text(
        "INSERT INTO issuer_esg_metrics (issuer_id,org_id,reporting_year,taxonomy_eligible_pct,"
        "taxonomy_aligned_pct,taxonomy_aligned_capex_pct,dnsh_ok,min_safeguards_ok,source) "
        "VALUES (:i,:o,2023,90,:t,:c,:d,:m,'client')"),
        {"i": iid, "o": DEMO_ORG, "t": aligned_turnover, "c": aligned_capex, "d": dnsh_ok, "m": safeguards_ok})
    s.execute(text(
        "INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
        "VALUES (:f,:s,1000000,100,'2026-07-12')"), {"f": fid, "s": sid})
    return fid, iid


def _cleanup(fid, iid):
    with get_session() as s:
        s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": fid})
        s.execute(text("DELETE FROM securities WHERE isin='DE00DUALKPI1'"))
        s.execute(text("DELETE FROM issuers WHERE issuer_id=:i"), {"i": iid})


@pytest.mark.integration
def test_turnover_and_capex_are_independent_kpis():
    """A fund can have full turnover coverage and zero CapEx coverage — the two must
    never be averaged together or let one silently stand in for the other."""
    with get_session() as s:
        fid, iid = _seed(s, aligned_turnover=60.0, aligned_capex=None)
    try:
        with get_session() as s:
            rt = _taxonomy_rollup(s, fid)
        assert rt["taxonomy_aligned_turnover_pct"] == 60.0
        assert rt["turnover_alignment_coverage_pct"] == 100.0
        assert rt["taxonomy_aligned_capex_pct"] is None
        assert rt["capex_alignment_coverage_pct"] == 0.0
        assert rt["capex_input_required"] is not None
        # Backward-compat: the deprecated ambiguous key still equals the turnover KPI.
        assert rt["taxonomy_aligned_pct"] == rt["taxonomy_aligned_turnover_pct"]
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_both_kpis_computed_when_both_reported():
    with get_session() as s:
        fid, iid = _seed(s, aligned_turnover=60.0, aligned_capex=45.0)
    try:
        with get_session() as s:
            rt = _taxonomy_rollup(s, fid)
        assert rt["taxonomy_aligned_turnover_pct"] == 60.0
        assert rt["taxonomy_aligned_capex_pct"] == 45.0
        assert rt["turnover_alignment_coverage_pct"] == 100.0
        assert rt["capex_alignment_coverage_pct"] == 100.0
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_capex_kpi_also_gated_by_dnsh():
    """The DNSH / minimum-safeguards gate applies independently to the CapEx KPI too —
    a failing attestation excludes it from CapEx alignment exactly as it does turnover."""
    with get_session() as s:
        fid, iid = _seed(s, aligned_turnover=60.0, aligned_capex=45.0, dnsh_ok=False)
    try:
        with get_session() as s:
            rt = _taxonomy_rollup(s, fid)
        assert rt["taxonomy_aligned_turnover_pct"] is None
        assert rt["taxonomy_aligned_capex_pct"] is None
        assert rt["turnover_aligned_excluded_dnsh_pct"] == 100.0
        assert rt["capex_aligned_excluded_dnsh_pct"] == 100.0
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_neither_kpi_asserted_when_nothing_reported():
    with get_session() as s:
        fid, iid = _seed(s, aligned_turnover=None, aligned_capex=None)
    try:
        with get_session() as s:
            rt = _taxonomy_rollup(s, fid)
        assert rt["taxonomy_aligned_turnover_pct"] is None
        assert rt["taxonomy_aligned_capex_pct"] is None
        assert "not asserted" in rt["turnover_alignment_note"]
        assert "not asserted" in rt["capex_alignment_note"]
    finally:
        _cleanup(fid, iid)

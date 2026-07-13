"""Taxonomy DNSH / minimum-safeguards gate.

An issuer's reported Taxonomy-aligned % is only counted when its DNSH and
minimum-safeguards attestations are not explicitly failing. Requires PostgreSQL.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from ml.regulatory.sfdr_pai import _taxonomy_rollup

DEMO_ORG = "44444444-4444-4444-8444-444444444444"


def _seed(s, dnsh_ok, safeguards_ok):
    fid = str(s.execute(text(
        "INSERT INTO funds (org_id,name,fund_type,sfdr_classification) "
        "VALUES (:o,'TEST DNSH Fund','fund','article_8') RETURNING fund_id"), {"o": DEMO_ORG}).scalar())
    iid = str(s.execute(text(
        "INSERT INTO issuers (name,issuer_type,country,nace_code,source) "
        "VALUES ('DNSH Issuer','corporate','DE','35.11','manual') RETURNING issuer_id")).scalar())
    sid = str(s.execute(text(
        "INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
        "VALUES ('DE00DNSHTST1','DNSH Sec',:i,'equity','manual') RETURNING security_id"), {"i": iid}).scalar())
    s.execute(text(
        "INSERT INTO issuer_esg_metrics (issuer_id,org_id,reporting_year,taxonomy_eligible_pct,"
        "taxonomy_aligned_pct,dnsh_ok,min_safeguards_ok,source) "
        "VALUES (:i,:o,2023,80,60,:d,:m,'client')"),
        {"i": iid, "o": DEMO_ORG, "d": dnsh_ok, "m": safeguards_ok})
    s.execute(text(
        "INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
        "VALUES (:f,:s,1000000,100,'2026-07-12')"), {"f": fid, "s": sid})
    return fid, iid


def _cleanup(fid, iid):
    with get_session() as s:
        s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": fid})
        s.execute(text("DELETE FROM securities WHERE isin='DE00DNSHTST1'"))
        s.execute(text("DELETE FROM issuers WHERE issuer_id=:i"), {"i": iid})


@pytest.mark.integration
def test_aligned_counts_when_dnsh_not_flagged():
    with get_session() as s:
        fid, iid = _seed(s, None, None)   # not separately assessed → reported stands
    try:
        with get_session() as s:
            rt = _taxonomy_rollup(s, fid)
        assert rt["taxonomy_aligned_pct"] == 60.0
        assert rt["aligned_excluded_dnsh_pct"] == 0.0
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_aligned_excluded_when_dnsh_fails():
    with get_session() as s:
        fid, iid = _seed(s, False, None)  # DNSH known to fail → excluded
    try:
        with get_session() as s:
            rt = _taxonomy_rollup(s, fid)
        assert rt["taxonomy_aligned_pct"] is None      # nothing counts
        assert rt["aligned_excluded_dnsh_pct"] == 100.0
        assert "EXCLUDED" in rt["alignment_note"]
    finally:
        _cleanup(fid, iid)

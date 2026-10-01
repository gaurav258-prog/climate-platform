"""Bidirectional data lineage — a filed number traces down to the golden source, and a cell traces back up
to every holding/filing that reuses it. Requires PostgreSQL; non-polluting (reads live data, no writes).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.data.feeds import HAZARD_FEEDS
from services.governance.filing_lineage import cell_lineage, cell_upstream, reported_hazards
from services.governance.filings import reporting_period_end
from services.governance.report_snapshots import create_snapshot
from tests.integration.money_method import state_method

BANK_ORG = "11111111-1111-4111-8111-111111111111"


def _mk_filing(session, org_id: str, framework: str, actor_email: str) -> str:
    """Freeze a real, current snapshot into a throwaway-period draft filing (rolled back by the caller) —
    same non-polluting pattern as tests/integration/test_filing_lifecycle.py's _mk_draft."""
    u = session.execute(text("SELECT user_id::text FROM users WHERE email = :e"), {"e": actor_email}).scalar()
    state_method(session, org_id, reporting_period_end(session, org_id))          # the institution's stated method (E69)
    snap = create_snapshot(session, org_id, framework, u, period_end=reporting_period_end(session, org_id))
    fid = session.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, created_by)
        VALUES (:o, :fk, '2099-12-31', 'FY2099', 'draft', :snap, :u) RETURNING filing_id
    """), {"o": org_id, "fk": framework, "snap": snap["snapshot_id"], "u": u}).scalar()
    return str(fid)


def _a_bank_filing(session):
    """A Pillar 3 ESG filing of the earlier report shape, which froze hazard cells (rolled back by the caller). Neither bank
    report prints a hazard cell any more (E95, E97); a filing frozen before still traces its cells as frozen — what this
    builds: the earlier builder's payload, on the method this test states."""
    import json

    from api.routers.bank import build_disclosure_snapshot
    from services.governance.report_snapshots import _sha256
    u = session.execute(text("SELECT user_id::text FROM users WHERE email = 'admin@meridian.demo'")).scalar()
    pe = reporting_period_end(session, BANK_ORG)
    state_method(session, BANK_ORG, pe)
    old = build_disclosure_snapshot(session, BANK_ORG, "baseline", "current", period_end=pe)
    basis = {"scenario": "baseline", "horizon": "current", "reporting_period_end": "2099-12-31"}
    sid = session.execute(text("""INSERT INTO report_snapshots (org_id, report_type, version, reporting_basis, payload, payload_sha256)
                                  VALUES (CAST(:o AS uuid), 'bank_p3esg', 9001, CAST(:b AS jsonb), CAST(:p AS jsonb), :h)
                                  RETURNING snapshot_id"""),
                          {"o": BANK_ORG, "b": json.dumps(basis), "p": json.dumps(old, default=str),
                           "h": _sha256(json.loads(json.dumps(old, default=str)))}).scalar()
    return str(session.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, created_by)
        VALUES (:o, 'bank_p3esg', '2099-12-31', 'FY2099', 'draft', :snap, :u) RETURNING filing_id
    """), {"o": BANK_ORG, "snap": sid, "u": u}).scalar())


@pytest.mark.integration
def test_a_new_pillar3_filing_says_it_prints_no_hazard_cell():
    """E97: Pillar 3 prints Template 5 rows, not a value per hazard — the trace says so instead of tracing nothing."""
    with get_session() as s:
        fid = _mk_filing(s, BANK_ORG, "bank_p3esg", "admin@meridian.demo")
        assert reported_hazards(s, BANK_ORG, fid) == []
        lin = cell_lineage(s, BANK_ORG, fid, "flood")
        assert lin["supported"] is False and "Template 5" in lin["message"]
        s.rollback()


@pytest.mark.integration
def test_hazard_feed_map_only_references_real_feeds():
    """Every hazard→feed mapping must point at a feed that actually exists in the registry — no invented source."""
    from services.data.feeds import FEEDS
    keys = {f["key"] for f in FEEDS}
    for hz, feeds in HAZARD_FEEDS.items():
        for k in feeds:
            assert k in keys, f"hazard {hz} maps to unknown feed '{k}'"


@pytest.mark.integration
def test_forward_lineage_traces_cell_to_golden_source():
    """A reported hazard cell resolves to contributing assets, each linked to a golden-source row + a feed."""
    with get_session() as s:
        fid = _a_bank_filing(s)
        hazards = reported_hazards(s, BANK_ORG, fid)
        # pick a hazard that actually has exposed contributors
        hz = next((h["hazard"] for h in hazards if (h["exposed_value_eur"] or 0) > 0), None)
        if not hz:
            pytest.skip("filing has no exposed hazard cell")
        lin = cell_lineage(s, BANK_ORG, fid, hz)
        assert lin["supported"] is True
        assert lin["contributors"], "an exposed cell must have contributing assets"
        # the contributors are exactly the ones the filed cell was computed from — their values add up to it
        cell = next(h for h in hazards if h["hazard"] == hz)["exposed_value_eur"]
        assert abs(sum(c["value_eur"] or 0 for c in lin["contributors"]) - cell) <= 1
        # the score→source hop must resolve to at least one real feed for a mapped hazard
        if hz in HAZARD_FEEDS:
            assert lin["sources"], f"{hz} should map to a source feed"
        # each contributor carries its cell + the golden-source row that backs it (or an explicit None)
        c = lin["contributors"][0]
        assert c["h3_cell"]
        assert "granular" in c and "drift" in c
        s.rollback()


@pytest.mark.integration
def test_reverse_lineage_finds_the_filing_that_reuses_a_cell():
    """A granular cell traces back to this org's holdings on it and the framework/filing that consumes them."""
    with get_session() as s:
        fid = _a_bank_filing(s)
        hz = next((h["hazard"] for h in reported_hazards(s, BANK_ORG, fid)
                   if (h["exposed_value_eur"] or 0) > 0), None)
        lin = cell_lineage(s, BANK_ORG, fid, hz)
        cell = lin["contributors"][0]["h3_cell"]
        up = cell_upstream(s, BANK_ORG, cell)
        assert up["h3_cell"] == cell
        assert up["used_by"], "the cell must be reused by at least the filing we came from"
        banking = next((g for g in up["used_by"] if g["vertical"] == "banking"), None)
        assert banking and banking["framework"] == "bank_p3esg" and banking["n"] >= 1
        s.rollback()


@pytest.mark.integration
def test_reit_taxonomy_traces_directly_not_via_sibling_workaround():
    """Fixed foundationally 2026-09-23: reit_taxonomy used to have no per-property list in its own frozen
    snapshot, so it couldn't be traced at all (an earlier pass had it point at the sibling reit_tcfd filing
    instead — a workaround, not a fix, and not even always possible). report_snapshots._reit_taxonomy now
    carries the same {h3_cell, hazards[]} list its sibling does, so it must trace directly, standalone."""
    with get_session() as s:
        org_id = s.execute(text("SELECT org_id::text FROM organizations WHERE name LIKE 'Stellar%'")).scalar()
        fid = _mk_filing(s, org_id, "reit_taxonomy", "admin@stellar.demo")
        hazards = reported_hazards(s, org_id, fid)
        hz = next((h["hazard"] for h in hazards if (h["exposed_value_eur"] or 0) > 0), None)
        assert hz, "expected at least one exposed hazard on Stellar's property book"
        lin = cell_lineage(s, org_id, fid, hz)
        assert lin["supported"] is True
        assert lin["contributors"], "reit_taxonomy must trace to real contributing properties, standalone"
        assert lin["contributors"][0]["h3_cell"]
        s.rollback()


@pytest.mark.integration
def test_insurer_solvency_traces_directly_not_via_sibling_workaround():
    """Same fix as reit_taxonomy above, for the insurer sector."""
    with get_session() as s:
        org_id = s.execute(text("SELECT org_id::text FROM organizations WHERE name LIKE 'Iberia%'")).scalar()
        fid = _mk_filing(s, org_id, "insurer_solvency", "admin@iberia.demo")
        hazards = reported_hazards(s, org_id, fid)
        hz = next((h["hazard"] for h in hazards if (h["exposed_value_eur"] or 0) > 0), None)
        assert hz, "expected at least one exposed hazard on Iberia's underwriting book"
        lin = cell_lineage(s, org_id, fid, hz)
        assert lin["supported"] is True
        assert lin["contributors"], "insurer_solvency must trace to real contributing policies, standalone"
        assert lin["contributors"][0]["h3_cell"]
        s.rollback()


@pytest.mark.integration
def test_reverse_lineage_is_tenant_scoped():
    """A cell trace only ever returns the querying org's own holdings."""
    with get_session() as s:
        cell = s.execute(text(
            "SELECT h3_cell FROM portfolio_entities WHERE org_id = :o AND h3_cell IS NOT NULL LIMIT 1"),
            {"o": BANK_ORG}).scalar()
        if not cell:
            pytest.skip("no located entity")
        up = cell_upstream(s, BANK_ORG, cell)
        ids = [e["entity_id"] for g in up["used_by"] for e in g["entities"]]
        if ids:
            owned = s.execute(text(
                "SELECT count(*) FROM portfolio_entities WHERE org_id = :o AND entity_id = ANY(CAST(:ids AS uuid[]))"),
                {"o": BANK_ORG, "ids": ids}).scalar()
            assert owned == len(ids), "reverse lineage leaked entities from another tenant"

"""Bidirectional data lineage — a filed number traces down to the golden source, and a cell traces back up
to every holding/filing that reuses it. Requires PostgreSQL; non-polluting (reads live data, no writes).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.data.feeds import HAZARD_FEEDS
from services.governance.filing_lineage import cell_lineage, cell_upstream, reported_hazards

BANK_ORG = "11111111-1111-4111-8111-111111111111"


def _a_bank_filing(session):
    return session.execute(text(
        "SELECT filing_id::text FROM regulatory_filing WHERE org_id = :o AND framework = 'bank_tcfd' "
        "AND snapshot_id IS NOT NULL ORDER BY created_at DESC LIMIT 1"), {"o": BANK_ORG}).scalar()


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
        if not fid:
            pytest.skip("no bank_tcfd filing to trace")
        hazards = reported_hazards(s, BANK_ORG, fid)
        # pick a hazard that actually has exposed contributors
        hz = next((h["hazard"] for h in hazards if (h["exposed_value_eur"] or 0) > 0), None)
        if not hz:
            pytest.skip("filing has no exposed hazard cell")
        lin = cell_lineage(s, BANK_ORG, fid, hz)
        assert lin["supported"] is True
        assert lin["contributors"], "an exposed cell must have contributing assets"
        # the score→source hop must resolve to at least one real feed for a mapped hazard
        if hz in HAZARD_FEEDS:
            assert lin["sources"], f"{hz} should map to a source feed"
        # each contributor carries its cell + the golden-source row that backs it (or an explicit None)
        c = lin["contributors"][0]
        assert c["h3_cell"]
        assert "granular" in c and "drift" in c


@pytest.mark.integration
def test_reverse_lineage_finds_the_filing_that_reuses_a_cell():
    """A granular cell traces back to this org's holdings on it and the framework/filing that consumes them."""
    with get_session() as s:
        fid = _a_bank_filing(s)
        if not fid:
            pytest.skip("no bank_tcfd filing")
        hz = next((h["hazard"] for h in reported_hazards(s, BANK_ORG, fid)
                   if (h["exposed_value_eur"] or 0) > 0), None)
        lin = cell_lineage(s, BANK_ORG, fid, hz)
        cell = lin["contributors"][0]["h3_cell"]
        up = cell_upstream(s, BANK_ORG, cell)
        assert up["h3_cell"] == cell
        assert up["used_by"], "the cell must be reused by at least the filing we came from"
        banking = next((g for g in up["used_by"] if g["vertical"] == "banking"), None)
        assert banking and banking["framework"] == "bank_tcfd" and banking["n"] >= 1


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

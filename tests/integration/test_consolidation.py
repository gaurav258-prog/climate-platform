"""Group consolidation: a filing scoped to a legal entity covers that entity's book; a filing scoped to a
group consolidates its whole subtree, with proportional lines value-weighted by ownership.

Requires PostgreSQL + the seeded reporting-entity hierarchy (scripts/seed_entity_hierarchy). Non-polluting:
runs in one uncommitted session and rolls back.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from api.routers.bank import build_disclosure_snapshot
from core.db.session import get_session
from services.governance import entities as E
from services.ingest.portfolio_ingest import ingest_bank_assets

BANK_ORG = "11111111-1111-4111-8111-111111111111"


@pytest.mark.integration
def test_group_consolidation_is_ownership_weighted():
    with get_session() as s:
        tree = E.entity_tree(s, BANK_ORG)
        groups = [e for e in tree if e["kind"] == "group"]
        prop = [e for e in tree if e["consolidation_method"] == "proportional"]
        if not groups or not prop:
            pytest.skip("hierarchy not seeded")
        grp, leasing = groups[0], prop[0]

        def total(**kw):
            return build_disclosure_snapshot(s, BANK_ORG, "baseline", "current", **kw)["rollup"]["total_value_eur"]

        whole = total()
        subtree = E.subtree_ids(s, BANK_ORG, grp["entity_id"])
        weights = E.ownership_weights(s, BANK_ORG)

        # unweighted union of the group's subtree == the whole org (every asset belongs to some leaf)
        assert total(entity_ids=subtree) == pytest.approx(whole, rel=1e-6)

        # a standalone entity filing is a strict subset
        leas_full = total(entity_ids=[leasing["entity_id"]])
        assert 0 < leas_full < whole

        # consolidated with ownership weighting drops the proportional line's un-owned share
        w = weights[leasing["entity_id"]]
        assert w < 1.0
        cons = total(entity_ids=subtree, value_weights=weights)
        assert cons == pytest.approx(whole - (1 - w) * leas_full, rel=1e-6)
        assert cons < whole

        s.rollback()


@pytest.mark.integration
def test_no_orphan_reporting_entity_for_orgs_with_a_hierarchy():
    """An asset with reporting_entity_id=NULL is invisible to every per-entity/consolidated-group filing —
    it only shows up in the org-wide unscoped view. This was a real bug (54 assets across 2 demo orgs, 499M
    + more, silently orphaned) caused by the ingest paths never assigning one. Guards against it recurring."""
    with get_session() as s:
        orphans = s.execute(text("""
            SELECT pe.org_id::text, COUNT(*) n, SUM(pe.primary_value_eur) v
            FROM portfolio_entities pe
            WHERE pe.reporting_entity_id IS NULL
              AND EXISTS (SELECT 1 FROM reporting_entities re WHERE re.org_id = pe.org_id)
            GROUP BY 1
        """)).mappings().all()
        assert not orphans, f"orgs with a reporting-entity hierarchy have orphaned book rows: {orphans}"


@pytest.mark.integration
def test_ingest_assigns_reporting_entity_when_unambiguous():
    """A single-entity org: a freshly ingested asset must be assigned that entity automatically (no reason
    to leave it orphaned when there's only one place it could belong)."""
    with get_session() as s:
        # find (or skip) an org with exactly one non-group reporting entity
        row = s.execute(text("""
            SELECT org_id::text FROM reporting_entities WHERE kind <> 'group'
            GROUP BY org_id HAVING COUNT(*) = 1 LIMIT 1
        """)).first()
        if not row:
            pytest.skip("no single-entity org seeded")
        org_id = row[0]
        expected = E.default_reporting_entity(s, org_id)
        assert expected is not None

        test_asset_name = f"consolidation-test-{uuid.uuid4()}"
        result = ingest_bank_assets(s, org_id, [{
            "asset_name": test_asset_name, "asset_type": "commercial_real_estate",
            "latitude": "52.5", "longitude": "13.4", "appraised_value_eur": "1000000",
            "sector": "real_estate", "counterparty_evic_eur": "50000000",
        }])
        assert result["n_ingested"] == 1
        assert "reporting_entity_gap" not in result
        rid = s.execute(text(
            "SELECT reporting_entity_id::text FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) "
            "AND entity_name = :n"), {"o": org_id, "n": test_asset_name}).scalar()
        assert rid == expected
        s.rollback()


@pytest.mark.integration
def test_ingest_discloses_the_gap_when_ambiguous():
    """A multi-entity org: a freshly ingested asset with no reporting_entity specified must stay honestly
    unassigned (never guessed) AND the ingest response must say so — never a silent orphan."""
    with get_session() as s:
        assert E.default_reporting_entity(s, BANK_ORG) is None  # Meridian has 3 legal entities: ambiguous

        test_asset_name = f"consolidation-test-{uuid.uuid4()}"
        result = ingest_bank_assets(s, BANK_ORG, [{
            "asset_name": test_asset_name, "asset_type": "commercial_real_estate",
            "latitude": "52.5", "longitude": "13.4", "appraised_value_eur": "1000000",
            "sector": "real_estate", "counterparty_evic_eur": "50000000",
        }])
        assert result["n_ingested"] == 1
        assert "reporting_entity_gap" in result
        rid = s.execute(text(
            "SELECT reporting_entity_id FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) "
            "AND entity_name = :n"), {"o": BANK_ORG, "n": test_asset_name}).scalar()
        assert rid is None
        s.rollback()


@pytest.mark.integration
def test_ownership_weights_multiply_along_the_chain_and_the_root_counts_in_full():
    """A 60% joint operation held through a 50% joint operation consolidates at 30% into the top; a consolidated
    filing AT the 50% sub-group takes its own book in full and the 60% line at 60%. (Both were wrong before
    2026-09-26: each entity carried only its own direct factor, and the filing root was scaled by its stake.)"""
    import uuid as _u
    with get_session() as s:
        org = s.execute(text("SELECT org_id::text FROM organizations WHERE type = 'bank' LIMIT 1")).scalar()
        top, mid, leaf = str(_u.uuid4()), str(_u.uuid4()), str(_u.uuid4())
        for eid, par, pct, meth in ((top, None, 100, "full"), (mid, top, 50, "proportional"), (leaf, mid, 60, "proportional")):
            s.execute(text("""INSERT INTO reporting_entities (entity_id, org_id, parent_entity_id, ownership_pct, name, kind,
                                                              consolidation_method)
                              VALUES (CAST(:e AS uuid), CAST(:o AS uuid), CAST(:p AS uuid), :pct, :n, 'legal_entity', :m)"""),
                      {"e": eid, "o": org, "p": par, "pct": pct, "n": f"TEST-CHAIN-{eid[:6]}", "m": meth})
        w_top = E.ownership_weights(s, org)
        assert w_top[top] == 1.0 and w_top[mid] == pytest.approx(0.5) and w_top[leaf] == pytest.approx(0.3)
        w_mid = E.ownership_weights(s, org, root_entity_id=_u.UUID(mid))       # a UUID, as it comes from the DB
        assert w_mid[mid] == 1.0 and w_mid[leaf] == pytest.approx(0.6)
        s.rollback()

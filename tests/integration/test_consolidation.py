"""Group consolidation: a filing scoped to a legal entity covers that entity's book; a filing scoped to a
group consolidates its whole subtree, with proportional lines value-weighted by ownership.

Requires PostgreSQL + the seeded reporting-entity hierarchy (scripts/seed_entity_hierarchy). Non-polluting:
runs in one uncommitted session and rolls back.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.governance import entities as E
from api.routers.bank import build_disclosure_snapshot

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

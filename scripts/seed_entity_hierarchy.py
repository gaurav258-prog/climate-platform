"""Seed a reporting-entity HIERARCHY per demo org and partition the calc-side book across the leaves.

Two idempotent steps per org:
  1. Assign portfolio_entities.reporting_entity_id round-robin across the org's (non-group) entities, so the
     calc book — which consolidation rolls up — is partitioned into non-empty subsets. (The Horizon globe
     scopes the raw asset tables separately; in the demo the two keyspaces have drifted, so we assign the
     calc book directly rather than by id.)
  2. Create a GROUP parent per org and hang the existing legal entities / funds under it, with an
     ownership_pct + consolidation_method (one leaf made proportional to exercise weighted roll-up).

    python -m scripts.seed_entity_hierarchy
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from core.db.session import get_session

# org_id -> group parent name
GROUPS = {
    "11111111-1111-4111-8111-111111111111": "Meridian Financial Group",
    "22222222-2222-4222-8222-222222222222": "Iberia Mutual Group",
    "44444444-4444-4444-8444-444444444444": "Nordkap Asset Management Group",
    "33333333-3333-4333-8333-333333333333": "Stellar Group",
    "55555555-5555-4555-8555-555555555555": "Terra Group",
}


def main():
    with get_session() as s:
        for org, group_name in GROUPS.items():
            leaves = [str(r[0]) for r in s.execute(text(
                "SELECT entity_id FROM reporting_entities WHERE org_id=:o AND kind <> 'group' ORDER BY name"
            ), {"o": org}).all()]
            if not leaves:
                print(f"{org}: no entities to hang; skip"); continue

            # 1) partition the calc book across the leaves (only rows not yet assigned)
            assigned = s.execute(text("""
                WITH ents AS (
                    SELECT entity_id, (row_number() OVER (ORDER BY name)) - 1 AS idx, count(*) OVER () AS n
                    FROM reporting_entities WHERE org_id=:o AND kind <> 'group'),
                book AS (
                    SELECT entity_id AS pe_id, (row_number() OVER (ORDER BY entity_id)) - 1 AS r
                    FROM portfolio_entities WHERE org_id=:o AND reporting_entity_id IS NULL)
                UPDATE portfolio_entities pe SET reporting_entity_id = ents.entity_id
                FROM book JOIN ents ON ents.idx = (book.r % ents.n)
                WHERE pe.entity_id = book.pe_id
            """), {"o": org}).rowcount
            print(f"{org}: assigned {assigned} book rows across {len(leaves)} entities")

            # 2) group parent (idempotent: skip if a group already exists)
            gid = s.execute(text("SELECT entity_id FROM reporting_entities WHERE org_id=:o AND kind='group' LIMIT 1"), {"o": org}).scalar()
            if gid:
                print(f"  group already present; skip hierarchy")
                continue
            gid = str(uuid.uuid4())
            s.execute(text("INSERT INTO reporting_entities (entity_id, org_id, name, kind, ownership_pct, consolidation_method) VALUES (:e,:o,:n,'group',100,'full')"),
                      {"e": gid, "o": org, "n": group_name})
            # hang each leaf under the group; make the LAST leaf a 60%-owned proportional line to exercise weighting
            for i, lid in enumerate(leaves):
                proportional = (i == len(leaves) - 1 and len(leaves) > 1)
                s.execute(text("UPDATE reporting_entities SET parent_entity_id=:g, ownership_pct=:p, consolidation_method=:m WHERE entity_id=:e"),
                          {"g": gid, "e": lid, "p": 60 if proportional else 100, "m": "proportional" if proportional else "full"})
            print(f"  created group '{group_name}' over {len(leaves)} entities (last = proportional 60%)")


if __name__ == "__main__":
    main()

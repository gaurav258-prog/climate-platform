"""Reporting-entity hierarchy — the tree a group consolidates over.

`reporting_entities` is org-scoped and self-referential (`parent_entity_id`). A filing can be scoped to one
entity (its own book) or to a parent/group, which CONSOLIDATES its whole subtree. `subtree_ids` resolves a
node to itself + all descendants (recursive), so the calc engine can read exactly that slice of the book.
Ownership weighting (for proportional/equity consolidation) is applied downstream from `ownership_pct`.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def entity_tree(session: Session, org_id: str) -> list[dict]:
    """Every reporting entity for the org (flat, with parent refs + book size), newest-kind first."""
    rows = session.execute(text("""
        SELECT e.entity_id::text AS entity_id, e.name, e.kind,
               e.parent_entity_id::text AS parent_entity_id,
               e.ownership_pct::float AS ownership_pct, e.consolidation_method,
               (SELECT count(*) FROM portfolio_entities pe WHERE pe.reporting_entity_id = e.entity_id) AS n_assets,
               (SELECT COALESCE(sum(pe.primary_value_eur), 0) FROM portfolio_entities pe WHERE pe.reporting_entity_id = e.entity_id) AS value_eur
        FROM reporting_entities e WHERE e.org_id = :o
        ORDER BY (e.kind = 'group') DESC, e.name
    """), {"o": org_id}).mappings().all()
    return [dict(r) for r in rows]


def get_entity(session: Session, org_id: str, entity_id: str) -> dict | None:
    r = session.execute(text("""
        SELECT entity_id::text AS entity_id, name, kind, parent_entity_id::text AS parent_entity_id,
               ownership_pct::float AS ownership_pct, consolidation_method
        FROM reporting_entities WHERE org_id = :o AND entity_id = :e
    """), {"o": org_id, "e": entity_id}).mappings().first()
    return dict(r) if r else None


def subtree_ids(session: Session, org_id: str, entity_id: str) -> list[str]:
    """The entity + all its descendants (recursive) — the set of reporting entities a consolidated filing
    at `entity_id` covers. Tenant-scoped."""
    rows = session.execute(text("""
        WITH RECURSIVE sub AS (
            SELECT entity_id, parent_entity_id FROM reporting_entities WHERE org_id = :o AND entity_id = :e
            UNION ALL
            SELECT c.entity_id, c.parent_entity_id FROM reporting_entities c
            JOIN sub ON c.parent_entity_id = sub.entity_id
        )
        SELECT entity_id::text FROM sub
    """), {"o": org_id, "e": entity_id}).all()
    return [r[0] for r in rows]


def ownership_weights(session: Session, org_id: str) -> dict[str, float]:
    """entity_id -> the fraction of its book that consolidates upward, from the ownership path to the root.
    Full/equity lines weight 1.0 at this level; a proportional line weights ownership_pct/100. (Equity-method
    nuances beyond scope — treated as full here, flagged in the model, not silently mis-stated.)"""
    rows = session.execute(text("""
        SELECT entity_id::text, ownership_pct::float, consolidation_method
        FROM reporting_entities WHERE org_id = :o
    """), {"o": org_id}).all()
    out: dict[str, float] = {}
    for eid, pct, method in rows:
        out[eid] = (pct / 100.0) if method == "proportional" else 1.0
    return out

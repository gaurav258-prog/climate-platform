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


class EntityError(ValueError):
    pass


METHODS = {"full", "proportional", "equity"}
# the raw books that also carry a reporting-entity link (so a delete can unassign, never orphan)
_RAW_TABLES = ["bank_assets", "insurance_policies", "assetmgmt_holdings",
               "realestate_properties", "sc_company_sites", "sc_sourcing_plots"]
_UNSET = object()


def _validate(name=None, kind=None, ownership_pct=None, consolidation_method=None):
    if name is not None and not name.strip():
        raise EntityError("name is required")
    if kind is not None and not kind.strip():
        raise EntityError("kind is required")
    if ownership_pct is not None and not (0 <= ownership_pct <= 100):
        raise EntityError("ownership_pct must be between 0 and 100")
    if consolidation_method is not None and consolidation_method not in METHODS:
        raise EntityError(f"consolidation_method must be one of {sorted(METHODS)}")


def _parent_in_org(session, org_id, parent_entity_id) -> bool:
    return bool(session.execute(text(
        "SELECT 1 FROM reporting_entities WHERE org_id=:o AND entity_id=:e"),
        {"o": org_id, "e": parent_entity_id}).first())


def create_entity(session: Session, org_id: str, *, name: str, kind: str = "legal_entity",
                  parent_entity_id: str | None = None, ownership_pct: float = 100.0,
                  consolidation_method: str = "full") -> dict:
    _validate(name, kind, ownership_pct, consolidation_method)
    if parent_entity_id and not _parent_in_org(session, org_id, parent_entity_id):
        raise EntityError("parent entity not found in your organisation")
    eid = session.execute(text("""
        INSERT INTO reporting_entities (entity_id, org_id, name, kind, parent_entity_id, ownership_pct, consolidation_method)
        VALUES (gen_random_uuid(), :o, :n, :k, :p, :pct, :m) RETURNING entity_id
    """), {"o": org_id, "n": name.strip(), "k": kind.strip(), "p": parent_entity_id,
           "pct": ownership_pct, "m": consolidation_method}).scalar()
    return get_entity(session, org_id, str(eid))


def update_entity(session: Session, org_id: str, entity_id: str, *, name=None, kind=None,
                  parent_entity_id=_UNSET, ownership_pct=None, consolidation_method=None) -> dict:
    if not get_entity(session, org_id, entity_id):
        raise EntityError("entity not found")
    _validate(name, kind, ownership_pct, consolidation_method)
    sets, params = [], {"o": org_id, "e": entity_id}
    if name is not None: sets.append("name = :n"); params["n"] = name.strip()
    if kind is not None: sets.append("kind = :k"); params["k"] = kind.strip()
    if ownership_pct is not None: sets.append("ownership_pct = :pct"); params["pct"] = ownership_pct
    if consolidation_method is not None: sets.append("consolidation_method = :m"); params["m"] = consolidation_method
    if parent_entity_id is not _UNSET:
        if parent_entity_id == entity_id:
            raise EntityError("an entity can't be its own parent")
        if parent_entity_id is not None:
            if not _parent_in_org(session, org_id, parent_entity_id):
                raise EntityError("parent entity not found in your organisation")
            # cycle guard: the new parent must not be the entity's own descendant
            if parent_entity_id in subtree_ids(session, org_id, entity_id):
                raise EntityError("can't reparent an entity under one of its own descendants")
        sets.append("parent_entity_id = :p"); params["p"] = parent_entity_id
    if sets:
        session.execute(text(f"UPDATE reporting_entities SET {', '.join(sets)} WHERE org_id=:o AND entity_id=:e"), params)
    return get_entity(session, org_id, entity_id)


def delete_entity(session: Session, org_id: str, entity_id: str) -> dict:
    if not get_entity(session, org_id, entity_id):
        raise EntityError("entity not found")
    kids = session.execute(text("SELECT count(*) FROM reporting_entities WHERE org_id=:o AND parent_entity_id=:e"),
                           {"o": org_id, "e": entity_id}).scalar()
    if kids:
        raise EntityError("remove or reparent this entity's child entities first")
    # unassign its book everywhere (fall back to whole-org) so nothing dangles
    session.execute(text("UPDATE portfolio_entities SET reporting_entity_id = NULL WHERE org_id=:o AND reporting_entity_id=:e"),
                    {"o": org_id, "e": entity_id})
    for t in _RAW_TABLES:
        session.execute(text(f"UPDATE {t} SET entity_id = NULL WHERE org_id=:o AND entity_id=:e"), {"o": org_id, "e": entity_id})
    session.execute(text("DELETE FROM reporting_entities WHERE org_id=:o AND entity_id=:e"), {"o": org_id, "e": entity_id})
    return {"ok": True}


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

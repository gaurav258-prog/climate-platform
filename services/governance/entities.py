"""Reporting-entity hierarchy — the tree a group consolidates over.

`reporting_entities` is org-scoped and self-referential (`parent_entity_id`). A filing can be scoped to one
entity (its own book) or to a parent/group, which CONSOLIDATES its whole subtree. `subtree_ids` resolves a
node to itself + all descendants (recursive), so the calc engine can read exactly that slice of the book.
Ownership weighting (for proportional/equity consolidation) is applied downstream from `ownership_pct`.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def entity_tree(session: Session, org_id: str) -> list[dict]:
    """Every reporting entity for the org (flat, with parent refs + book size), newest-kind first.
    has_children + requires_solo_filing together tell a reader whether this node's own individual-reporting
    duty (CRR Art 6, or the Solvency II solo-supervision equivalent) is live — a leaf with
    requires_solo_filing=true genuinely owes its own filing, not just a share of the group's."""
    rows = session.execute(text("""
        SELECT e.entity_id::text AS entity_id, e.name, e.kind,
               e.parent_entity_id::text AS parent_entity_id,
               e.ownership_pct::float AS ownership_pct, e.consolidation_method, e.consolidation_basis,
               e.requires_solo_filing, e.solo_waiver_reason,
               (SELECT count(*) FROM portfolio_entities pe WHERE pe.reporting_entity_id = e.entity_id) AS n_assets,
               (SELECT COALESCE(sum(pe.primary_value_eur), 0) FROM portfolio_entities pe WHERE pe.reporting_entity_id = e.entity_id) AS value_eur,
               EXISTS(SELECT 1 FROM reporting_entities c WHERE c.parent_entity_id = e.entity_id) AS has_children
        FROM reporting_entities e WHERE e.org_id = :o
        ORDER BY (e.kind = 'group') DESC, e.name
    """), {"o": org_id}).mappings().all()
    return [dict(r) for r in rows]


def get_entity(session: Session, org_id: str, entity_id: str) -> dict | None:
    r = session.execute(text("""
        SELECT e.entity_id::text AS entity_id, e.name, e.kind, e.parent_entity_id::text AS parent_entity_id,
               e.ownership_pct::float AS ownership_pct, e.consolidation_method, e.consolidation_basis,
               e.requires_solo_filing, e.solo_waiver_reason,
               EXISTS(SELECT 1 FROM reporting_entities c WHERE c.parent_entity_id = e.entity_id) AS has_children
        FROM reporting_entities e WHERE e.org_id = :o AND e.entity_id = :e
    """), {"o": org_id, "e": entity_id}).mappings().first()
    return dict(r) if r else None


def filing_role_for(session: Session, org_id: str, entity_id: str | None) -> str:
    """Derive the explicit role a filing at this scope plays, per CRR Art 6 (solo) vs Art 18 (consolidated):
    entity_id None = whole_org (today's default, whole-company scope); a leaf entity (no children) = solo,
    the entity's own individual-reporting duty; an entity WITH children = consolidated, since selecting it
    rolls up its whole subtree (entities.subtree_ids / ownership_weights)."""
    if entity_id is None:
        return "whole_org"
    has_children = session.execute(text(
        "SELECT EXISTS(SELECT 1 FROM reporting_entities WHERE org_id = :o AND parent_entity_id = :e)"),
        {"o": org_id, "e": entity_id}).scalar()
    return "consolidated" if has_children else "solo"


def default_reporting_entity(session: Session, org_id: str) -> str | None:
    """The reporting entity a NEWLY INGESTED asset should be filed under, when the ingest row doesn't say.

    A book asset with no reporting_entity_id is invisible to every entity-scoped or consolidated-group
    filing (it only shows up in the unscoped org-wide view) — an on-demand-verified real bug, not a
    theoretical one: 54 assets across two demo orgs (bank + insurer) had silently fallen into this gap
    before this function existed. Every ingest path must assign one.

    Unambiguous only when the org has exactly one non-group reporting entity — then that's obviously
    where a new asset belongs. An org with a real multi-entity hierarchy (a group over several legal
    entities/funds) has no way to infer which leaf a bare row belongs to from the row alone, so this
    returns None rather than guess; the caller must then either ask the uploader (a reporting_entity
    field on the template) or accept the row stays unscoped until an operator assigns it via the entity
    hierarchy UI. Never silently pick the "first" or "biggest" leaf — that would misattribute exposure
    to the wrong legal entity in a consolidated filing, which is worse than leaving it honestly gapped."""
    rows = session.execute(text(
        "SELECT entity_id::text FROM reporting_entities WHERE org_id = :o AND kind <> 'group'"
    ), {"o": org_id}).scalars().all()
    return rows[0] if len(rows) == 1 else None


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


def _consolidation_needs_basis(ownership_pct: float, consolidation_method: str) -> bool:
    """True when the method contradicts the ownership%-implied presumption of control: 'full' consolidation
    of a minority stake, or 'proportional'/'equity' consolidation of a majority stake. IFRS 10 control is
    genuinely principles-based, not a raw ownership% cutoff, so this never blocks the combination outright
    — it requires the customer to say why (consolidation_basis), the same pattern as solo_waiver_reason.
    Exactly 50% is left alone: a classic joint-control candidate, not a presumption either way."""
    if ownership_pct is None or consolidation_method is None:
        return False
    if consolidation_method == "full" and ownership_pct < 50:
        return True
    if consolidation_method in ("proportional", "equity") and ownership_pct > 50:
        return True
    return False


def _parent_in_org(session, org_id, parent_entity_id) -> bool:
    return bool(session.execute(text(
        "SELECT 1 FROM reporting_entities WHERE org_id=:o AND entity_id=:e"),
        {"o": org_id, "e": parent_entity_id}).first())


def create_entity(session: Session, org_id: str, *, name: str, kind: str = "legal_entity",
                  parent_entity_id: str | None = None, ownership_pct: float = 100.0,
                  consolidation_method: str = "full", requires_solo_filing: bool | None = None,
                  solo_waiver_reason: str | None = None, consolidation_basis: str | None = None) -> dict:
    """requires_solo_filing defaults to True — the CRR-safe assumption (Art 6) that an entity's own
    individual-reporting duty applies unless a customer explicitly records why it's waived (Art 7:
    parent guarantee, prudent-management sign-off, no impediment to fund transfer). Never default this to
    False just because the entity sits inside a consolidated group — that's exactly the assumption CRR
    forbids making silently.

    ONE exception, not a guess but a settled legal fact: a `branch` is the SAME legal entity as its head
    office (it has no separate legal personality), so it has no independent Art 6 solo-reporting duty of
    its own — that duty belongs to the head office, once, covering every branch worldwide. `kind='branch'`
    defaults requires_solo_filing to False unless the caller explicitly overrides (e.g. a jurisdiction that
    genuinely imposes host-country solo reporting on a branch, which does happen in some third-country
    regimes — Tellumen doesn't assume it away, it just isn't the CRR default).

    consolidation_method is checked against ownership_pct's IFRS 10 control presumption (see
    _consolidation_needs_basis) — 'full' below 50% or 'proportional'/'equity' above 50% requires an explicit
    consolidation_basis, or the create is rejected. This never overrides the method itself (control is a
    genuine judgement call, not a formula); it only refuses to let that judgement go unrecorded."""
    _validate(name, kind, ownership_pct, consolidation_method)
    if requires_solo_filing is None:
        requires_solo_filing = (kind.strip().lower() != "branch")
    if solo_waiver_reason and requires_solo_filing:
        raise EntityError("a waiver reason implies requires_solo_filing=false — set both consistently")
    if _consolidation_needs_basis(ownership_pct, consolidation_method) and not (consolidation_basis or "").strip():
        raise EntityError(
            f"consolidation_method={consolidation_method!r} at {ownership_pct}% ownership runs counter to the "
            "IFRS 10 control presumption from ownership alone — set consolidation_basis to say why (e.g. a "
            "majority voting agreement or de facto control under IFRS 10.B41-45 for 'full' below 50%; the "
            "joint-control or associate arrangement that justifies 'proportional'/'equity' despite majority "
            "ownership)")
    if parent_entity_id and not _parent_in_org(session, org_id, parent_entity_id):
        raise EntityError("parent entity not found in your organisation")
    eid = session.execute(text("""
        INSERT INTO reporting_entities (entity_id, org_id, name, kind, parent_entity_id, ownership_pct,
                                        consolidation_method, consolidation_basis, requires_solo_filing,
                                        solo_waiver_reason)
        VALUES (gen_random_uuid(), :o, :n, :k, :p, :pct, :m, :basis, :rsf, :swr) RETURNING entity_id
    """), {"o": org_id, "n": name.strip(), "k": kind.strip(), "p": parent_entity_id,
           "pct": ownership_pct, "m": consolidation_method,
           "basis": (consolidation_basis or "").strip() or None,
           "rsf": requires_solo_filing, "swr": (solo_waiver_reason or "").strip() or None}).scalar()
    return get_entity(session, org_id, str(eid))


def update_entity(session: Session, org_id: str, entity_id: str, *, name=None, kind=None,
                  parent_entity_id=_UNSET, ownership_pct=None, consolidation_method=None,
                  consolidation_basis=_UNSET, requires_solo_filing=None, solo_waiver_reason=_UNSET) -> dict:
    current = get_entity(session, org_id, entity_id)
    if not current:
        raise EntityError("entity not found")
    _validate(name, kind, ownership_pct, consolidation_method)
    if ownership_pct is not None or consolidation_method is not None:
        eff_pct = ownership_pct if ownership_pct is not None else current["ownership_pct"]
        eff_method = consolidation_method if consolidation_method is not None else current["consolidation_method"]
        eff_basis = (consolidation_basis if consolidation_basis is not _UNSET
                    else current.get("consolidation_basis"))
        if _consolidation_needs_basis(eff_pct, eff_method) and not (eff_basis or "").strip():
            raise EntityError(
                f"consolidation_method={eff_method!r} at {eff_pct}% ownership runs counter to the IFRS 10 "
                "control presumption from ownership alone — set consolidation_basis to say why")
    sets, params = [], {"o": org_id, "e": entity_id}
    if name is not None: sets.append("name = :n"); params["n"] = name.strip()
    if kind is not None: sets.append("kind = :k"); params["k"] = kind.strip()
    if ownership_pct is not None: sets.append("ownership_pct = :pct"); params["pct"] = ownership_pct
    if consolidation_method is not None: sets.append("consolidation_method = :m"); params["m"] = consolidation_method
    if consolidation_basis is not _UNSET:
        sets.append("consolidation_basis = :basis"); params["basis"] = (consolidation_basis or "").strip() or None
    if requires_solo_filing is not None:
        sets.append("requires_solo_filing = :rsf"); params["rsf"] = requires_solo_filing
    if solo_waiver_reason is not _UNSET:
        sets.append("solo_waiver_reason = :swr"); params["swr"] = (solo_waiver_reason or "").strip() or None
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


def ownership_weights(session: Session, org_id: str, root_entity_id: Optional[str] = None) -> dict[str, float]:
    """entity_id -> the fraction of its book that consolidates into `root_entity_id` (default: the top of the tree).

    Each entity's own link to its parent carries a factor by its consolidation method:
    - full consolidation (a controlled subsidiary): 1.0 — the whole book flows up.
    - proportional consolidation (a joint operation): ownership_pct/100.
    - equity method (an associate): governed by the `equity_consolidation` interpretation switch —
      'economic_share' (default) = ownership_pct/100; 'excluded' = 0.0 (strict IFRS); 'full' = 1.0.
    The weight is the PRODUCT of those factors along the path from the entity up to the root — a 60% stake held
    through a 50%-owned joint operation counts 30%, not 60% — and the root itself is 1.0: a sub-group's own
    consolidated filing takes its own book in full, whatever its parent holds of it. (Fixed 2026-09-26: each entity
    used to carry only its own direct factor, and the filing root was scaled by its stake in its parent.)"""
    from services.calc_settings import get_calc_settings
    equity_mode = get_calc_settings(session, org_id).get("equity_consolidation", "economic_share")
    rows = session.execute(text("""
        SELECT entity_id::text, parent_entity_id::text, ownership_pct::float, consolidation_method
        FROM reporting_entities WHERE org_id = :o
    """), {"o": org_id}).all()
    parent, factor = {}, {}
    for eid, par, pct, method in rows:
        share = (pct or 0.0) / 100.0
        parent[eid] = par
        if method == "proportional":
            factor[eid] = share
        elif method == "equity":
            factor[eid] = {"economic_share": share, "excluded": 0.0, "full": 1.0}.get(equity_mode, share)
        else:  # full consolidation (or unset) — the whole book
            factor[eid] = 1.0
    root = str(root_entity_id) if root_entity_id is not None else None   # a UUID from the DB must match string ids
    out: dict[str, float] = {}
    for eid in parent:
        w, cur, hops = 1.0, eid, 0
        while cur != root and parent.get(cur) is not None and hops < 64:   # 64: a guard against a cycle
            w *= factor[cur]
            cur, hops = parent[cur], hops + 1
        out[eid] = w
    return out

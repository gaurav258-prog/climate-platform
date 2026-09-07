"""Regulator / supervisor portal — Phase 1: scoped cross-entity read access + population submission dashboard.

The rest of the app is strictly org-scoped and IDOR-hardened. This router is the ONE governed exception: a
regulator organization (organizations.type = 'regulator') may read across the reporting entities it supervises
— and ONLY those, defined by supervision_scope. Every rule here is deliberate and enforced:
  • ACCESS GATE: caller's org must be type 'regulator' (require_supervisor).
  • SCOPE: every read is restricted to the caller's supervised population (supervision_scope, active rows). A
    regulator can never reach an entity outside it — entity/{org_id} 404s rather than leak existence.
  • READ-ONLY + RELEASED-ONLY: only FILED statuses are ever visible; drafts/rejected are never shown.
  • AUDITED: each per-entity access writes to that supervised entity's own audit log, so the entity sees who
    looked and when (regulator transparency, not surveillance).
Phase 2/3 (system-wide aggregation, independent EO lens) build on this foundation.
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from api.deps import CurrentUser, DbSession
from api.services.rbac import write_audit
from services.governance import filings as F

router = APIRouter(prefix="/v1/supervisor", tags=["Regulator portal"])

# A filing that actually reached the regulator: submitted or beyond. Drafts/rejected are never shown.
FILED = ("submitted", "accepted", "approved", "attested", "released")


def require_supervisor(ctx: CurrentUser) -> dict:
    """403 unless the caller's organization is a regulator/supervisor."""
    if (ctx.get("org") or {}).get("type") != "regulator":
        raise HTTPException(status_code=403,
                            detail={"error": "forbidden", "message": "Regulator/supervisor access only."})
    return ctx


Supervisor = Annotated[dict, Depends(require_supervisor)]


def _supervised(session, reg_org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT o.org_id::text AS org_id, o.name, o.type, o.country, ss.jurisdiction
        FROM supervision_scope ss
        JOIN organizations o ON o.org_id = ss.supervised_org_id
        WHERE ss.regulator_org_id = CAST(:r AS uuid) AND ss.active
        ORDER BY o.name
    """), {"r": reg_org_id}).mappings().all()
    return [dict(r) for r in rows]


def _in_scope(session, reg_org_id: str, target_org_id: str) -> bool:
    return session.execute(text("""
        SELECT 1 FROM supervision_scope
        WHERE regulator_org_id = CAST(:r AS uuid) AND supervised_org_id = CAST(:t AS uuid) AND active
    """), {"r": reg_org_id, "t": target_org_id}).first() is not None


@router.get("/population", summary="Supervised entities × frameworks — latest submission status")
def population(session: DbSession, ctx: Supervisor):
    reg = ctx["org"]["org_id"]
    entities = _supervised(session, reg)
    if not entities:
        return {"regulator": ctx["org"].get("name"), "entities": [], "summary": {"entities": 0}}

    ids = [e["org_id"] for e in entities]
    # latest filing per (entity, framework)
    latest = session.execute(text("""
        SELECT DISTINCT ON (org_id, framework)
               org_id::text AS org_id, framework, status, period_label, created_at
        FROM regulatory_filing
        WHERE org_id = ANY(CAST(:ids AS uuid[]))
        ORDER BY org_id, framework, created_at DESC
    """), {"ids": ids}).mappings().all()
    by_org: dict[str, dict[str, dict]] = {}
    for r in latest:
        by_org.setdefault(r["org_id"], {})[r["framework"]] = dict(r)

    n_filed = n_expected = 0
    out_entities = []
    for e in entities:
        frameworks = []
        for f in F.available_frameworks(e["type"]):
            fk = f["framework"]
            rec = by_org.get(e["org_id"], {}).get(fk)
            filed = bool(rec and rec["status"] in FILED)
            state = "filed" if filed else ("in_progress" if rec else "none")
            n_expected += 1
            n_filed += 1 if filed else 0
            frameworks.append({"framework": fk, "label": f.get("label", fk), "state": state,
                               "status": rec["status"] if rec else None,
                               "period_label": rec["period_label"] if rec else None})
        out_entities.append({**e, "frameworks": frameworks,
                             "filed": sum(1 for x in frameworks if x["state"] == "filed"),
                             "expected": len(frameworks)})
    return {
        "regulator": ctx["org"].get("name"),
        "entities": out_entities,
        "summary": {"entities": len(entities), "frameworks_expected": n_expected,
                    "frameworks_filed": n_filed,
                    "coverage_pct": round(100.0 * n_filed / n_expected, 1) if n_expected else None},
    }


@router.get("/entity/{org_id}", summary="One supervised entity — its released filings (read-only, audited)")
def entity(org_id: str, session: DbSession, ctx: Supervisor):
    reg = ctx["org"]["org_id"]
    if not _in_scope(session, reg, org_id):
        # do not confirm existence of an out-of-scope entity
        raise HTTPException(status_code=404, detail={"error": "not_found",
                            "message": "No such supervised entity in your population."})
    org = session.execute(text("SELECT name, type, country FROM organizations WHERE org_id = CAST(:o AS uuid)"),
                          {"o": org_id}).mappings().first() or {}
    rows = session.execute(text("""
        SELECT filing_id::text AS filing_id, framework, status, period_label, submission_ref, created_at
        FROM regulatory_filing
        WHERE org_id = CAST(:o AS uuid) AND status = ANY(:st)
        ORDER BY created_at DESC
    """), {"o": org_id, "st": list(FILED)}).mappings().all()

    # transparency: the supervised entity sees that its regulator accessed its filings
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"],
                action="supervisor.access", target_type="organization", target_id=org_id,
                detail={"regulator_org_id": reg, "regulator": ctx["org"].get("name"), "filings_seen": len(rows)})
    session.commit()

    return {"entity": {"org_id": org_id, **dict(org)},
            "filings": [dict(r) | {"created_at": r["created_at"].isoformat() if r["created_at"] else None}
                        for r in rows]}


@router.get("/summary", summary="Population rollup — one line for the regulator's dashboard header")
def summary(session: DbSession, ctx: Supervisor):
    pop = population(session, ctx)
    s = pop["summary"]
    overdue = sum(1 for e in pop["entities"] for f in e["frameworks"] if f["state"] != "filed")
    return {"regulator": pop["regulator"], **s, "gaps": overdue}


# ── Where the supervised exposure sits ────────────────────────────────────────────────────────────────────
# Two levels, matching what a supervisor is entitled to:
#   • REGIONAL heat map — always available for the whole population: exposures rolled up to NUTS-3 (the unit of
#     EBA Pillar 3 Template 5 / ESRS E1-9), H3 res-4 hexagons outside the EU. No site is identifiable.
#   • INDIVIDUAL SITES — only for an entity that has GRANTED site-level access on its scope row
#     (supervision_scope.site_access_granted_at, not revoked). Each site read is audited on the entity's log.
def _site_access(session, reg_org_id: str, target_org_id: str) -> bool:
    return session.execute(text("""
        SELECT 1 FROM supervision_scope
        WHERE regulator_org_id = CAST(:r AS uuid) AND supervised_org_id = CAST(:t AS uuid) AND active
          AND site_access_granted_at IS NOT NULL AND site_access_revoked_at IS NULL
    """), {"r": reg_org_id, "t": target_org_id}).first() is not None


@router.get("/map", summary="Regional heat map of the supervised population's exposure (NUTS-3 / H3, never sites)")
def exposure_map(session: DbSession, ctx: Supervisor, entity: Optional[str] = None,
                 scenario: str = "baseline", horizon: str = "current"):
    from services.geo.org_assets import org_asset_points
    from services.geo.regions import aggregate_by_region
    reg = ctx["org"]["org_id"]
    ents = _supervised(session, reg)
    if entity and entity != "all":
        if not _in_scope(session, reg, entity):
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervised entity in your population."})
        ents = [e for e in ents if e["org_id"] == entity]
    points: list[dict] = []
    per_entity = []
    for e in ents:
        pts = org_asset_points(session, e["org_id"], scenario, horizon)
        for p in pts:
            p["entity"] = e["name"]
        points += pts
        per_entity.append({"org_id": e["org_id"], "name": e["name"], "type": e["type"], "n_sites": len(pts),
                           "value_eur": round(sum(p["value_eur"] for p in pts)),
                           "site_access": _site_access(session, reg, e["org_id"])})
    regions = aggregate_by_region(points)
    return {"scenario": scenario, "horizon": horizon, "level": "NUTS-3 (EU, Eurostat GISCO 2021) · H3 res-4 hexagon elsewhere",
            "n_sites": len(points), "value_eur": round(sum(p["value_eur"] for p in points)),
            "n_regions": len(regions), "entities": per_entity, "regions": regions}


@router.get("/sites", summary="Individual sites of ONE supervised entity — only where that entity granted site-level access")
def entity_sites(entity: str, session: DbSession, ctx: Supervisor, scenario: str = "baseline", horizon: str = "current"):
    from services.geo.org_assets import org_asset_points
    reg = ctx["org"]["org_id"]
    if not _in_scope(session, reg, entity):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervised entity in your population."})
    if not _site_access(session, reg, entity):
        raise HTTPException(status_code=403, detail={"error": "site_access_not_granted",
                            "message": "This entity has not granted site-level access to its supervisor. Regional aggregates remain available."})
    pts = org_asset_points(session, entity, scenario, horizon)
    write_audit(session, org_id=entity, actor_user_id=ctx["user"]["id"], action="supervisor.sites.access",
                target_type="organization", target_id=entity,
                detail={"regulator_org_id": reg, "regulator": ctx["org"].get("name"), "sites_seen": len(pts),
                        "scenario": scenario, "horizon": horizon})
    session.commit()
    name = session.execute(text("SELECT name FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": entity}).scalar()
    return {"entity": {"org_id": entity, "name": name}, "scenario": scenario, "horizon": horizon, "n_sites": len(pts), "sites": pts}

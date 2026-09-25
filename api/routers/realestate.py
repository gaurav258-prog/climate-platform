"""
Real estate — public read-only endpoints for the Portfolio & NOI impact
workspace, the platform's 4th vertical.

Projects the golden source (canonical_scores) onto a REIT's property book via
the shared portfolio engine (services/portfolio_engine.py) and the unified
v_portfolio_entity_physical_risk view -- the same engine banking and asset
management use (see the b9c0d1e2f3a4 migration). Reuses, rather than
reinvents, three things already built: ml/scoring/valuation_discount.py's
haircut engine (climate-adjusted property value), ml/scoring/insurance_pricing.py
via realestate_impact.py's noi_impact() (operating-income drag), and
ml/regulatory/eu_taxonomy_classifier.py (real Annex I citation for every
property, since 68.20 real estate is already mapped eligible).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import CurrentUser, DbSession
from api.services.rbac import write_audit
from ml.regulatory.eu_taxonomy_classifier import classify_taxonomy
from ml.scoring.epc_stranding import epc_stranding, stranding_rollup
from ml.scoring.realestate_impact import noi_impact
from ml.scoring.valuation_discount import value_loss_band
from services.calc_settings import get_calc_settings
from services.ingest.templates import (  # noqa: F401 — re-exported
    CONSTRUCTION_TYPES,
    EPC_RATINGS,
    PROPERTY_TEMPLATE_FIELDS,
    SAFEGUARDS_STATUSES,
)
from services.intelligence.resilience_capex import resilience_capex_plan
from services.portfolio_engine import (
    apply_valuation_override as engine_apply_override,
)
from services.portfolio_engine import (
    clear_valuation_override as engine_clear_override,
)
from services.portfolio_engine import (
    fetch_entities_with_risk,
    get_entity_org,
    get_entity_with_risk,
)
from services.templates.workbook import build_export_workbook, build_template_workbook

EXT_REALESTATE_COLUMNS = ["CAST(x.annual_noi_eur AS FLOAT) AS annual_noi_eur", "x.epc_rating",
                          "CAST(x.annual_gross_rental_revenue_eur AS FLOAT) AS annual_gross_rental_revenue_eur"]


def _realestate_extra(row, headline, hz):
    # thread the driving peril + building attributes so the NOI drag is vulnerability-differentiated,
    # consistent with the property's collateral haircut (both now share the one damage core).
    attrs = {"construction_type": row.get("construction_type"), "year_built": row.get("year_built"),
             "number_of_stories": row.get("number_of_stories")}
    impact = noi_impact(row["headline_score"], row["primary_value_eur"], row["annual_noi_eur"],
                        hazard=headline["hazard"], attrs=attrs) if headline else None
    tax = classify_taxonomy(REALESTATE_NACE, headline_bucket=row["headline_bucket"], resilience_rating=None,
                             epc_rating=row.get("epc_rating"), minimum_safeguards_status=row.get("minimum_safeguards_status"))
    # transition risk — energy-performance stranding under a rising minimum-EPC floor (the other half of the
    # property's climate exposure; physical NOI drag is above)
    stranding = epc_stranding(row.get("epc_rating"), row["primary_value_eur"], row["annual_noi_eur"])
    return {"noi_impact": impact, "taxonomy_status": tax["status"], "taxonomy_activity_ref": tax["activity_ref"],
            "taxonomy_reasoning": tax["reasoning"], "stranding": stranding}


def _map_property_row(row):
    """Shared-engine row -> the exact shape /portfolio, /summary, /disclosure
    have always returned."""
    return {
        "property_id": row["entity_id"], "property_name": row["entity_name"], "property_type": row["entity_type"],
        "country": row["country"], "region": row["region"], "lat": row["lat"], "lon": row["lon"],
        "h3_cell": row["h3_cell"], "property_value_eur": row["primary_value_eur"],
        "annual_noi_eur": row["annual_noi_eur"],
        "annual_gross_rental_revenue_eur": row["annual_gross_rental_revenue_eur"],
        "construction_type": row["construction_type"],
        "year_built": row["year_built"], "number_of_stories": row["number_of_stories"],
        "hazards": row["hazards"], "headline_score": row["headline_score"],
        "headline_bucket": row["headline_bucket"], "headline_hazard": row["headline_hazard"],
        "valuation": row["valuation"], "noi_impact": row["noi_impact"], "stranding": row["stranding"],
        "taxonomy_status": row["taxonomy_status"], "taxonomy_activity_ref": row["taxonomy_activity_ref"],
        "taxonomy_reasoning": row["taxonomy_reasoning"], "epc_rating": row["epc_rating"],
        "borrower_entity_id": row["borrower_entity_id"], "minimum_safeguards_status": row["minimum_safeguards_status"],
    }

router = APIRouter(prefix="/v1/realestate", tags=["Real Estate"])

DEMO_ORG = "33333333-3333-4333-8333-333333333333"  # Stellar Logistics REIT (demo)
REALESTATE_NACE = "68.20"  # every property IS real estate -- same NACE code, same Annex I §7.7
_bearer = HTTPBearer(auto_error=False)


def resolve_org(
    org_id: Optional[str] = Query(None),
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
) -> str:
    """User JWT's org wins (tenant isolation); else query param; else the demo REIT."""
    token = credentials.credentials if credentials else None
    if token and not token.startswith("cp_live_"):
        from api.security import decode_access_token
        payload = decode_access_token(token)
        if payload and payload.get("org_id"):
            return payload["org_id"]
    # SECURITY: a caller without a valid user JWT can ONLY ever see the public
    # demo org — never an arbitrary org_id. Dropping the query-param fallback
    # closes the cross-tenant read (an anonymous ?org_id=<other-tenant> IDOR).
    return DEMO_ORG


OrgId = Annotated[str, Depends(resolve_org)]


def _properties_with_risk(session, org_id, scenario, horizon, severity_model="universal",
                          entity_ids=None, value_weights=None):
    """All of an org's properties (metadata) + their per-hazard projected risk.
    Thin wrapper over the shared portfolio engine (services/portfolio_engine.py)."""
    rows = fetch_entities_with_risk(session, org_id, "realestate", scenario, horizon, severity_model,
                                     ext_table="ext_realestate", ext_columns=EXT_REALESTATE_COLUMNS,
                                     extra_calc=_realestate_extra,
                                     entity_ids=entity_ids, value_weights=value_weights)
    return [_map_property_row(r) for r in rows]


def _rollup(properties, adaptation_scenario="reference"):
    total = sum(p["property_value_eur"] or 0 for p in properties)
    total_noi = sum(p["annual_noi_eur"] or 0 for p in properties)
    impacted = [p for p in properties if p["noi_impact"]]
    total_premium = sum(p["noi_impact"]["expected_insurance_premium_eur"] for p in impacted)
    total_discounted = sum(p["valuation"]["discounted_value_eur"] for p in properties)
    by_bucket = defaultdict(lambda: {"count": 0, "value_eur": 0.0})
    for p in properties:
        b = p["headline_bucket"] or "none"
        by_bucket[b]["count"] += 1
        by_bucket[b]["value_eur"] += p["property_value_eur"] or 0
    return {
        "n_properties": len(properties),
        "n_scored": sum(1 for p in properties if p["headline_bucket"]),
        "total_value_eur": round(total),
        "total_annual_noi_eur": round(total_noi),
        "total_discounted_value_eur": round(total_discounted),
        "expected_value_loss_band": value_loss_band(properties),
        "resilience_capex": resilience_capex_plan(properties, scenario=adaptation_scenario),
        "energy_stranding": stranding_rollup(properties),
        "total_expected_insurance_premium_eur": round(total_premium),
        "portfolio_noi_impact_pct": round(100 * total_premium / total_noi, 2) if total_noi else 0,
        "by_bucket": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in by_bucket.items()},
        "top_properties": sorted(
            [p for p in properties if p["headline_score"] is not None],
            key=lambda p: -p["headline_score"])[:8],
    }


@router.get("/portfolio", summary="Property book projected onto the golden source")
def portfolio(session: DbSession, org_id: OrgId,
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    _st = get_calc_settings(session, org_id)
    severity_model = _st["severity_model"]
    properties = _properties_with_risk(session, org_id, scenario, horizon, severity_model)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": _rollup(properties, _st["adaptation_scenario"]), "properties": properties}


@router.get("/forward-risk", summary="Forward-change decision signal — scenario risk migration + runway")
def forward_risk_ep(session: DbSession, org_id: OrgId, scenario: str = Query("disorderly_2c")):
    from services.intelligence.forward_risk import forward_risk
    return forward_risk(session, org_id, "realestate", scenario)


@router.get("/summary", summary="Portfolio & NOI impact rollup")
def summary(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id = :o"
    ), {"o": org_id}).mappings().first()
    _st = get_calc_settings(session, org_id)
    severity_model = _st["severity_model"]
    properties = _properties_with_risk(session, org_id, scenario, horizon, severity_model)
    return {"org_id": org_id, "org": dict(org) if org else None, "rollup": _rollup(properties, _st["adaptation_scenario"])}


def build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=None, value_weights=None):
    """The single source of truth for a REIT TCFD / EU-Taxonomy physical-risk disclosure — live callers
    (GET /disclosure) and frozen callers (filing snapshots) both go through this so the numbers can't drift.
    entity_ids / value_weights scope + consolidation-weight the book (None = whole org)."""
    _st = get_calc_settings(session, org_id)
    severity_model = _st["severity_model"]
    properties = _properties_with_risk(session, org_id, scenario, horizon, severity_model,
                                       entity_ids=entity_ids, value_weights=value_weights)
    hazards: dict = {}
    for p in properties:
        for hz in p["hazards"]:
            h = hazards.setdefault(hz["hazard"], {
                "exposed_value_eur": 0.0, "n_exposed": 0, "max_score": 0.0,
                "model_version": hz["model_version"], "scored_at": hz["scored_at"]})
            if hz["bucket"] in ("H", "VH"):
                h["exposed_value_eur"] += p["property_value_eur"] or 0
                h["n_exposed"] += 1
            h["max_score"] = max(h["max_score"], hz["score"])
    for h in hazards.values():
        h["exposed_value_eur"] = round(h["exposed_value_eur"])
        h["max_score"] = round(h["max_score"], 1)
    tax = defaultdict(lambda: {"count": 0, "value_eur": 0.0})
    for p in properties:
        tax[p["taxonomy_status"]]["count"] += 1
        tax[p["taxonomy_status"]]["value_eur"] += p["property_value_eur"] or 0
    return {
        "rollup": _rollup(properties, _st["adaptation_scenario"]), "properties": properties,
        "by_hazard": hazards,
        "taxonomy": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in tax.items()},
    }


@router.get("/disclosure", summary="Physical-risk exposure + EU Taxonomy status — the data GRESB's "
                                    "Resilience module and CSRD physical-risk disclosure ask for")
def disclosure(session: DbSession, org_id: OrgId,
               scenario: str = Query("baseline"), horizon: str = Query("current")):
    """Not a fabricated GRESB score -- GRESB's own survey criteria and scoring
    weights aren't something we've verified against a primary source, so this
    surfaces the real underlying data (exposure by hazard, taxonomy status)
    that a GRESB or CSRD submission would actually need, honestly labeled."""
    snap = build_disclosure_snapshot(session, org_id, scenario, horizon)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": snap["rollup"], "by_hazard": snap["by_hazard"], "taxonomy": snap["taxonomy"]}


# A property schedule -- ~80% the same shape as insurance's Statement of Values,
# already built (see services/templates/workbook.py). annual_noi_eur is required:
# without it, this vertical's headline NOI-impact figure can't be computed.
# PROPERTY_TEMPLATE_FIELDS lives in services/ingest/templates.py (shared with the intake pipeline)
REQUIRED_PROPERTY_COLUMNS = [f["name"] for f in PROPERTY_TEMPLATE_FIELDS if f["required"]]


@router.get("/property/{property_id}", summary="One property — full projection + provenance")
def property_detail(property_id: str, session: DbSession):
    org_id = get_entity_org(session, property_id)
    if not org_id:
        return {"error": "property not found"}
    _st = get_calc_settings(session, org_id)
    severity_model = _st["severity_model"]
    row = get_entity_with_risk(session, property_id, "baseline", "current", severity_model,
                                ext_table="ext_realestate", ext_columns=EXT_REALESTATE_COLUMNS,
                                extra_calc=_realestate_extra)
    property_ = {
        "property_id": row["entity_id"], "org_id": row["org_id"], "property_name": row["entity_name"],
        "property_type": row["entity_type"], "country": row["country"], "region": row["region"],
        "lat": row["lat"], "lon": row["lon"], "h3_cell": row["h3_cell"],
        "property_value_eur": row["primary_value_eur"], "annual_noi_eur": row["annual_noi_eur"],
        "annual_gross_rental_revenue_eur": row["annual_gross_rental_revenue_eur"],
        "construction_type": row["construction_type"], "year_built": row["year_built"],
        "number_of_stories": row["number_of_stories"],
        "taxonomy_status": row["taxonomy_status"], "taxonomy_activity_ref": row["taxonomy_activity_ref"],
        "taxonomy_reasoning": row["taxonomy_reasoning"], "epc_rating": row["epc_rating"],
        "borrower_entity_id": row["borrower_entity_id"], "minimum_safeguards_status": row["minimum_safeguards_status"],
    }
    audit = session.execute(text("""
        SELECT actor_user_id::text AS actor_user_id, action, detail, created_at
        FROM access_audit_log WHERE target_type = 'realestate_property' AND target_id = :p
        ORDER BY created_at DESC LIMIT 5
    """), {"p": property_id}).mappings().all()
    return {
        "property": property_, "risks": row["risks"], "valuation": row["valuation"],
        "noi_impact": row["noi_impact"], "valuation_audit": [dict(x) for x in audit],
    }


class PropertyValuationOverrideRequest(BaseModel):
    discount_pct: float = Field(..., ge=0, le=100)
    reason: Optional[str] = None


@router.post("/property/{property_id}/valuation-override",
             summary="Override the recommended valuation discount (audited)")
def override_property_valuation(property_id: str, body: PropertyValuationOverrideRequest,
                                 session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    org_id = get_entity_org(session, property_id)
    if not org_id:
        raise HTTPException(status_code=404, detail="property not found")
    if org_id != ctx["org"]["org_id"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Property does not belong to your organization"})

    result = engine_apply_override(session, property_id, body.discount_pct, ctx["user"]["id"], body.reason)
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="property.valuation.override", target_type="realestate_property", target_id=property_id,
                detail={"from_pct": result["from_pct"], "to_pct": body.discount_pct, "reason": body.reason})
    return {"property_id": property_id, "override_discount_pct": body.discount_pct,
            "overridden_at": result["overridden_at"].isoformat()}


@router.delete("/property/{property_id}/valuation-override",
               summary="Clear an override, revert to the recommended discount (audited)")
def clear_property_valuation_override(property_id: str, session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    prior = engine_clear_override(session, property_id)
    if not prior:
        return {"property_id": property_id, "cleared": False}
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="property.valuation.override_cleared", target_type="realestate_property", target_id=property_id,
                detail={"from_pct": prior["override_discount_pct"], "to_pct": None})
    return {"property_id": property_id, "cleared": True}


@router.get("/properties/template.xlsx", summary="Download the property schedule upload template (Excel)")
def properties_template_xlsx():
    buf = build_template_workbook(PROPERTY_TEMPLATE_FIELDS)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=tellumen_property_schedule_template.xlsx"})


@router.post("/properties/validate", summary="Check a property schedule (CSV or Excel) before importing — nothing is saved")
async def validate_properties(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                              declared_row_count: Optional[str] = Form(None), declared_totals: Optional[str] = Form(None),
                         mapping_profile_id: Optional[str] = Form(None)):
    """Dry run of every intake check (security inspection, required columns, row checks, receipt, transformation and
    the gate the import will enforce). Nothing is stored or written."""
    from api.services.intake_http import declared_from_form, preview
    return preview(session, ctx["org"]["org_id"], "realestate_properties", await file.read(), file.filename,
                   declared_from_form(declared_row_count, declared_totals), mapping_profile_id)


@router.post("/properties/upload", summary="Import properties (CSV or Excel) into your portfolio")
async def upload_properties(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                            declared_row_count: Optional[str] = Form(None), declared_totals: Optional[str] = Form(None),
                            approval_reason: Optional[str] = Form(None), mapping_profile_id: Optional[str] = Form(None)):
    """Runs the property schedule through the intake pipeline (services/intake/pipeline.py): the file is stored write-once,
    security-inspected and malware-scanned, then checked. Every check passed → imported now (200). A check failed →
    sent to a second person for approval with your reason (202; nothing lands until approved). Scanner unavailable
    where required → held (202). Nothing valid, or refused on security grounds → 422, and the attempt is recorded."""
    from api.services.intake_http import declared_from_form, submit
    return submit(session, ctx["org"]["org_id"], "realestate_properties", await file.read(), file.filename,
                  user_id=ctx["user"]["id"], declared=declared_from_form(declared_row_count, declared_totals),
                  reason=approval_reason, mapping_profile_id=mapping_profile_id)


@router.get("/portfolio.xlsx", summary="Portfolio & NOI impact book (Excel)")
def portfolio_xlsx(session: DbSession, org_id: OrgId,
                    scenario: str = Query("baseline"), horizon: str = Query("current")):
    _st = get_calc_settings(session, org_id)
    severity_model = _st["severity_model"]
    properties = _properties_with_risk(session, org_id, scenario, horizon, severity_model)
    headers = ["property_name", "property_type", "region", "country", "property_value_eur", "annual_noi_eur",
               "headline_hazard", "headline_score", "risk_bucket", "discounted_value_eur",
               "expected_insurance_premium_eur", "noi_impact_pct", "taxonomy_status"]
    rows = [[p["property_name"], p["property_type"], p["region"], p["country"], p["property_value_eur"],
             p["annual_noi_eur"], p["headline_hazard"], p["headline_score"], p["headline_bucket"] or "unscored",
             p["valuation"]["discounted_value_eur"],
             p["noi_impact"]["expected_insurance_premium_eur"] if p["noi_impact"] else None,
             p["noi_impact"]["noi_impact_pct"] if p["noi_impact"] else None,
             p["taxonomy_status"]] for p in properties]
    buf = build_export_workbook(headers, rows, sheet_name="Portfolio & NOI impact")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=stellar-portfolio-noi-impact.xlsx"})

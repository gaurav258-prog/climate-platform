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
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import CurrentUser, DbSession, own_or_404, tenant_resolver
from api.services.rbac import write_audit
from ml.regulatory.eu_taxonomy_classifier import classify_taxonomy
from ml.scoring.epc_stranding import epc_stranding, stranding_rollup
from ml.scoring.realestate_impact import noi_impact
from ml.scoring.valuation_discount import value_loss_band
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
                          "CAST(x.annual_gross_rental_revenue_eur AS FLOAT) AS annual_gross_rental_revenue_eur",
                          # EU Taxonomy activity 7.7 alignment facts (services.governance.taxonomy_buildings)
                          "x.ped_top15_evidence", "x.meets_new_building_criteria",
                          "CAST(x.heating_rated_output_kw AS FLOAT) AS heating_rated_output_kw",
                          "x.energy_performance_monitoring", "x.adaptation_plan_in_place",
                          "CAST(x.sum_insured_eur AS FLOAT) AS sum_insured_eur"]


def _realestate_extra(method):
    """The per-property calculation on the owner's stated method for the year: the insurance cost of every insured peril
    on the property's insured value (ml.scoring.realestate_impact), its Taxonomy status and EPC stranding."""
    def extra(row, headline, hz):
        return _property_extra(method, row, headline, hz)
    return extra


def _property_extra(method, row, headline, hz):
    impact = noi_impact(method, hz, row.get("sum_insured_eur"), row["annual_noi_eur"]) if headline else None
    from services.money.params import at_risk
    tax = classify_taxonomy(REALESTATE_NACE, material_physical_risk=at_risk(method, row["headline_score"]), resilience_rating=None,
                             epc_rating=row.get("epc_rating"), minimum_safeguards_status=row.get("minimum_safeguards_status"))
    # transition risk — energy-performance stranding on the owner's stated brown discount per EPC grade (the other
    # half of the property's climate exposure; the physical insurance cost is above)
    stranding = epc_stranding(method, row.get("epc_rating"), row["primary_value_eur"], row["annual_noi_eur"])
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
        "sum_insured_eur": row.get("sum_insured_eur"),
        "construction_type": row["construction_type"],
        "year_built": row["year_built"], "number_of_stories": row["number_of_stories"],
        "hazards": row["hazards"], "headline_score": row["headline_score"],
        "headline_bucket": row["headline_bucket"], "headline_hazard": row["headline_hazard"],
        "valuation": row["valuation"], "noi_impact": row["noi_impact"], "stranding": row["stranding"],
        "taxonomy_status": row["taxonomy_status"], "taxonomy_activity_ref": row["taxonomy_activity_ref"],
        "taxonomy_reasoning": row["taxonomy_reasoning"], "epc_rating": row["epc_rating"],
        "borrower_entity_id": row["borrower_entity_id"], "minimum_safeguards_status": row["minimum_safeguards_status"],
        **{k: row.get(k) for k in ("ped_top15_evidence", "meets_new_building_criteria", "heating_rated_output_kw",
                                   "energy_performance_monitoring", "adaptation_plan_in_place")},
    }

router = APIRouter(prefix="/v1/realestate", tags=["Real Estate"])

DEMO_ORG = "33333333-3333-4333-8333-333333333333"  # Stellar Logistics REIT (demo)
REALESTATE_NACE = "68.20"  # every property IS real estate -- same NACE code, same Annex I §7.7
_bearer = HTTPBearer(auto_error=False)


resolve_org = tenant_resolver(DEMO_ORG)             # one implementation for every sector API (api/deps.py)
OrgId = Annotated[str, Depends(resolve_org)]


def _properties_with_risk(session, org_id, scenario, horizon, *, method, entity_ids=None, value_weights=None,
                          translation=None):
    """All of an org's properties (metadata) + their per-hazard projected risk, on the owner's stated method for the
    year. Thin wrapper over the shared portfolio engine (services/portfolio_engine.py)."""
    rows = fetch_entities_with_risk(session, org_id, "realestate", scenario, horizon, method=method,
                                     ext_table="ext_realestate", ext_columns=EXT_REALESTATE_COLUMNS,
                                     extra_calc=_realestate_extra(method),
                                     entity_ids=entity_ids, value_weights=value_weights, translation=translation)
    return [_map_property_row(r) for r in rows]


def _rollup(properties, method):
    """The book's totals on the owner's stated method: value at risk, climate-adjusted value, value-loss band,
    resilience capex, insurance cost and its share of NOI — each a gap where an input is not stated."""
    from services.portfolio_engine import climate_adjusted_total, value_at_risk
    total = sum(p["property_value_eur"] or 0 for p in properties)
    total_noi = sum(p["annual_noi_eur"] or 0 for p in properties)
    impacted = [p for p in properties if p["noi_impact"]]
    prems = [p["noi_impact"].get("technical_premium_eur") for p in impacted]
    total_premium = None if None in prems else sum(prems)
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
        **value_at_risk(properties, "property_value_eur", method),
        **climate_adjusted_total(properties, "property_value_eur"),
        "expected_value_loss_band": value_loss_band(method, properties),
        "resilience_capex": resilience_capex_plan(method, properties),
        "energy_stranding": stranding_rollup(method, properties),
        "total_technical_premium_eur": None if total_premium is None else round(total_premium),
        "portfolio_noi_impact_pct": (None if total_premium is None else
                                     round(100 * total_premium / total_noi, 2) if total_noi else None),
        **({"gap": "; ".join(sorted({g for g in [method.gap_text(), *[p["noi_impact"].get("gap") for p in impacted]] if g}))}
           if method.gap_text() or any(p["noi_impact"].get("gap") for p in impacted) else {}),
        "by_bucket": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in by_bucket.items()},
        "top_properties": sorted(
            [p for p in properties if p["headline_score"] is not None],
            key=lambda p: -p["headline_score"])[:8],
    }


@router.get("/portfolio", summary="Property book projected onto the golden source")
def portfolio(session: DbSession, org_id: OrgId,
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    from services.money.params import for_org
    method = for_org(session, org_id)
    properties = _properties_with_risk(session, org_id, scenario, horizon, method=method)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": _rollup(properties, method), "properties": properties}


@router.get("/forward-risk", summary="Forward-change decision signal — scenario risk migration + runway")
def forward_risk_ep(session: DbSession, org_id: OrgId, scenario: str = Query("disorderly_2c")):
    from services.intelligence.forward_risk import forward_risk
    from services.money.params import for_org
    return forward_risk(session, org_id, "realestate", scenario, for_org(session, org_id))


@router.get("/summary", summary="Portfolio & NOI impact rollup")
def summary(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id = :o"
    ), {"o": org_id}).mappings().first()
    from services.money.params import for_org
    method = for_org(session, org_id)
    properties = _properties_with_risk(session, org_id, scenario, horizon, method=method)
    return {"org_id": org_id, "org": dict(org) if org else None, "rollup": _rollup(properties, method)}


def build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None,
                              period_end=None):
    """The single source of truth for a REIT TCFD / EU-Taxonomy physical-risk disclosure — live callers
    (GET /disclosure) and frozen callers (filing snapshots) both go through this so the numbers can't drift.
    entity_ids / value_weights scope + consolidation-weight the book (None = whole org). period_end: the financial year
    whose stated method is used (None = the organisation's reporting period)."""
    from services.money.params import for_org
    from services.portfolio_engine import exposure_by_hazard
    method = for_org(session, org_id, period_end)
    properties = _properties_with_risk(session, org_id, scenario, horizon, method=method,
                                       entity_ids=entity_ids, value_weights=value_weights, translation=translation)
    hazards = exposure_by_hazard(properties, "property_value_eur", method)
    tax = defaultdict(lambda: {"count": 0, "value_eur": 0.0})
    for p in properties:
        tax[p["taxonomy_status"]]["count"] += 1
        tax[p["taxonomy_status"]]["value_eur"] += p["property_value_eur"] or 0
    return {
        "rollup": _rollup(properties, method), "properties": properties,
        "by_hazard": hazards,
        "taxonomy": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in tax.items()},
        "method": method.record(),
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
def property_detail(property_id: str, session: DbSession, caller_org: OrgId):
    own_or_404(session, "portfolio_entities", "entity_id", property_id, caller_org, "Property")   # only your own org's record
    org_id = get_entity_org(session, property_id)
    from services.money.params import for_org
    method = for_org(session, org_id)
    row = get_entity_with_risk(session, property_id, "baseline", "current", method=method,
                                ext_table="ext_realestate", ext_columns=EXT_REALESTATE_COLUMNS,
                                extra_calc=_realestate_extra(method))
    property_ = {
        "property_id": row["entity_id"], "org_id": row["org_id"], "property_name": row["entity_name"],
        "property_type": row["entity_type"], "country": row["country"], "region": row["region"],
        "lat": row["lat"], "lon": row["lon"], "h3_cell": row["h3_cell"],
        "property_value_eur": row["primary_value_eur"], "annual_noi_eur": row["annual_noi_eur"],
        "annual_gross_rental_revenue_eur": row["annual_gross_rental_revenue_eur"],
        "sum_insured_eur": row.get("sum_insured_eur"),
        "construction_type": row["construction_type"], "year_built": row["year_built"],
        "number_of_stories": row["number_of_stories"],
        "taxonomy_status": row["taxonomy_status"], "taxonomy_activity_ref": row["taxonomy_activity_ref"],
        "taxonomy_reasoning": row["taxonomy_reasoning"], "epc_rating": row["epc_rating"],
        "borrower_entity_id": row["borrower_entity_id"], "minimum_safeguards_status": row["minimum_safeguards_status"],
        **{k: row.get(k) for k in ("ped_top15_evidence", "meets_new_building_criteria", "heating_rated_output_kw",
                                   "energy_performance_monitoring", "adaptation_plan_in_place")},
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
                         mapping_profile_id: Optional[str] = Form(None),
                         currency: Optional[str] = Form(None), book_date: Optional[str] = Form(None)):
    """Dry run of every intake check (security inspection, required columns, row checks, receipt, transformation and
    the gate the import will enforce). Nothing is stored or written."""
    from api.services.intake_http import declared_from_form, preview
    return preview(session, ctx["org"]["org_id"], "realestate_properties", await file.read(), file.filename,
                   declared_from_form(declared_row_count, declared_totals), mapping_profile_id,
                   currency=currency, book_date=book_date)


@router.post("/properties/upload", summary="Import properties (CSV or Excel) into your portfolio")
async def upload_properties(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                            declared_row_count: Optional[str] = Form(None), declared_totals: Optional[str] = Form(None),
                            approval_reason: Optional[str] = Form(None), mapping_profile_id: Optional[str] = Form(None),
                         currency: Optional[str] = Form(None), book_date: Optional[str] = Form(None)):
    """Runs the property schedule through the intake pipeline (services/intake/pipeline.py): the file is stored write-once,
    security-inspected and malware-scanned, then checked. Every check passed → imported now (200). A check failed →
    sent to a second person for approval with your reason (202; nothing lands until approved). Scanner unavailable
    where required → held (202). Nothing valid, or refused on security grounds → 422, and the attempt is recorded."""
    from api.services.intake_http import declared_from_form, submit
    return submit(session, ctx["org"]["org_id"], "realestate_properties", await file.read(), file.filename,
                  user_id=ctx["user"]["id"], declared=declared_from_form(declared_row_count, declared_totals),
                  reason=approval_reason, mapping_profile_id=mapping_profile_id,
                  currency=currency, book_date=book_date)


@router.get("/portfolio.xlsx", summary="Portfolio & NOI impact book (Excel)")
def portfolio_xlsx(session: DbSession, org_id: OrgId,
                    scenario: str = Query("baseline"), horizon: str = Query("current")):
    from services.money.params import for_org
    properties = _properties_with_risk(session, org_id, scenario, horizon, method=for_org(session, org_id))
    headers = ["property_name", "property_type", "region", "country", "property_value_eur", "annual_noi_eur",
               "sum_insured_eur", "headline_hazard", "headline_score", "risk_bucket", "discounted_value_eur",
               "technical_premium_eur", "noi_impact_pct", "taxonomy_status"]
    rows = [[p["property_name"], p["property_type"], p["region"], p["country"], p["property_value_eur"],
             p["annual_noi_eur"], p["sum_insured_eur"], p["headline_hazard"], p["headline_score"],
             p["headline_bucket"] or "unscored", p["valuation"]["discounted_value_eur"],
             p["noi_impact"].get("technical_premium_eur") if p["noi_impact"] else None,
             p["noi_impact"]["noi_impact_pct"] if p["noi_impact"] else None,
             p["taxonomy_status"]] for p in properties]
    buf = build_export_workbook(headers, rows, sheet_name="Portfolio & NOI impact")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=stellar-portfolio-noi-impact.xlsx"})

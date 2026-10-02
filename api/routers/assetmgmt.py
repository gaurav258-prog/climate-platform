"""
Asset Management — public read-only endpoints for the Portfolio climate VaR
& screening workspace, the platform's 5th vertical.

Projects the golden source (canonical_scores) onto an asset manager's
holdings book via the shared portfolio engine (services/portfolio_engine.py)
and the unified v_portfolio_entity_physical_risk view -- the same engine
banking and real estate use (see the b9c0d1e2f3a4 migration). Needs ZERO new
scoring code: "climate VaR%" reuses
ml/scoring/valuation_discount.py's haircut-by-bucket schedule unchanged --
the same one banking uses for collateral and real estate uses for
climate-adjusted value -- and ml/regulatory/eu_taxonomy_classifier.py is
reused unchanged too. Nothing here is a new model, only a new label on two
functions three verticals now share.
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
from ml.scoring.valuation_discount import monte_carlo_var
from services.calc_settings import get_calc_settings
from services.ingest.templates import (  # noqa: F401 — re-exported
    HOLDING_TEMPLATE_FIELDS,
    SAFEGUARDS_STATUSES,
)
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
    value_at_risk,
)
from services.scoring.combined_var import combined_climate_var
from services.scoring.portfolio_concentration import portfolio_concentration
from services.templates.workbook import build_export_workbook, build_template_workbook


def _assetmgmt_extra(method):
    """Per holding: flagged when its headline score is at or above the manager's stated at-risk level (None: not
    stated), and its Taxonomy status."""
    from services.money.params import at_risk

    def extra(row, headline, hz):
        flagged = at_risk(method, row["headline_score"])
        tax = classify_taxonomy(row["nace_code"], material_physical_risk=flagged, resilience_rating=None,
                                 minimum_safeguards_status=row.get("minimum_safeguards_status"))
        return {"flagged": flagged, "taxonomy_status": tax["status"],
                "taxonomy_activity_ref": tax["activity_ref"], "taxonomy_reasoning": tax["reasoning"]}
    return extra


def _map_holding_row(row):
    """Shared-engine row -> the exact shape /portfolio, /summary, /disclosure
    have always returned (note: this vertical calls it climate_var, not
    valuation -- same underlying valuation_block, different label)."""
    return {
        "holding_id": row["entity_id"], "holding_name": row["entity_name"], "sector": row["sector"],
        "nace_code": row["nace_code"], "country": row["country"], "region": row["region"],
        "lat": row["lat"], "lon": row["lon"], "h3_cell": row["h3_cell"],
        "position_value_eur": row["primary_value_eur"],
        "hazards": row["hazards"], "headline_score": row["headline_score"],
        "headline_bucket": row["headline_bucket"], "headline_hazard": row["headline_hazard"],
        "climate_var": row["valuation"], "flagged": row["flagged"],
        "taxonomy_status": row["taxonomy_status"], "taxonomy_activity_ref": row["taxonomy_activity_ref"],
        "taxonomy_reasoning": row["taxonomy_reasoning"],
        "borrower_entity_id": row["borrower_entity_id"], "minimum_safeguards_status": row["minimum_safeguards_status"],
    }

router = APIRouter(prefix="/v1/assetmgmt", tags=["Asset Management"])

DEMO_ORG = "44444444-4444-4444-8444-444444444444"  # Nordkap Asset Management (demo)
_bearer = HTTPBearer(auto_error=False)


resolve_org = tenant_resolver(DEMO_ORG)             # one implementation for every sector API (api/deps.py)
OrgId = Annotated[str, Depends(resolve_org)]


def _holdings_with_risk(session, org_id, scenario, horizon, *, method, entity_ids=None, value_weights=None,
                        translation=None):
    """All of an org's holdings (metadata) + their per-hazard projected risk.
    Thin wrapper over the shared portfolio engine (services/portfolio_engine.py) --
    asset management needs no extension table (sector/nace_code already live
    on the shared portfolio_entities table). entity_ids / value_weights scope +
    consolidation-weight the book for a per-entity / group filing (None = whole org)."""
    rows = fetch_entities_with_risk(session, org_id, "assetmgmt", scenario, horizon, method=method,
                                     extra_calc=_assetmgmt_extra(method), entity_ids=entity_ids, value_weights=value_weights,
                                     translation=translation)
    return [_map_holding_row(r) for r in rows]


def _rollup(holdings, method, settings: dict, org_id: str, scenario: str, horizon: str):
    """The book's climate VaR on the manager's stated method and its own settings (the VaR method and the physical ×
    transition dependence) — the same for the live view and a frozen filing. A gap where an input is not stated."""
    from ml.scoring.valuation_discount import VAR_SIMULATIONS
    var_method, dependence = settings["assetmgmt_var_method"], settings["climate_var_dependence"]
    total = sum(h["position_value_eur"] or 0 for h in holdings)
    scored = [h for h in holdings if h["headline_score"] is not None]
    disc = [h["climate_var"]["discounted_value_eur"] for h in scored]
    total_var = None if None in disc else sum((h["position_value_eur"] or 0) - d for h, d in zip(scored, disc))
    flags = [h["flagged"] for h in holdings]
    n_flagged = None if None in flags else sum(1 for f in flags if f)
    by_bucket = defaultdict(lambda: {"count": 0, "value_eur": 0.0})
    for h in holdings:
        b = h["headline_bucket"] or "none"
        by_bucket[b]["count"] += 1
        by_bucket[b]["value_eur"] += h["position_value_eur"] or 0
    rollup = {
        "n_holdings": len(holdings),
        "n_scored": sum(1 for h in holdings if h["headline_bucket"]),
        "n_flagged": n_flagged,
        **value_at_risk(holdings, "position_value_eur", method),
        "total_portfolio_value_eur": round(total),
        "total_climate_var_eur": None if total_var is None else round(total_var),
        "portfolio_climate_var_pct": None if total_var is None else (round(100 * total_var / total, 2) if total else 0),
        "by_bucket": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in by_bucket.items()},
        "top_holdings": sorted(
            [h for h in holdings if h["headline_score"] is not None],
            key=lambda h: -h["headline_score"])[:8],
        "var_method": var_method,
    }
    if var_method == "monte_carlo":
        rollup["monte_carlo_var"] = monte_carlo_var(
            method, [{"position_value_eur": h["position_value_eur"], "hazard": h["headline_hazard"],
                      "score": h["headline_score"], "valuation": h["climate_var"]} for h in scored],
            org_id, scenario, horizon, VAR_SIMULATIONS)
    # Combined physical + transition climate VaR (one distribution over both drivers, with decomposition).
    rollup["combined_climate_var"] = combined_climate_var(method, holdings, org_id, scenario, horizon, VAR_SIMULATIONS,
                                                          dependence)
    if method.gap_text():
        rollup["gap"] = method.gap_text()
    return rollup


@router.get("/portfolio", summary="Holdings book projected onto the golden source")
def portfolio(session: DbSession, org_id: OrgId,
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    from services.money.params import for_org
    method = for_org(session, org_id)
    holdings = _holdings_with_risk(session, org_id, scenario, horizon, method=method)
    rollup = _rollup(holdings, method, get_calc_settings(session, org_id), org_id, scenario, horizon)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": rollup, "holdings": holdings,
            "concentration": portfolio_concentration(holdings)}


@router.get("/forward-risk", summary="Forward-change decision signal — scenario risk migration + runway")
def forward_risk_ep(session: DbSession, org_id: OrgId, scenario: str = Query("disorderly_2c")):
    from services.intelligence.forward_risk import forward_risk
    from services.money.params import for_org
    return forward_risk(session, org_id, "assetmgmt", scenario, for_org(session, org_id))


@router.get("/summary", summary="Portfolio climate VaR rollup")
def summary(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id = :o"
    ), {"o": org_id}).mappings().first()
    from services.money.params import for_org
    method = for_org(session, org_id)
    holdings = _holdings_with_risk(session, org_id, scenario, horizon, method=method)
    rollup = _rollup(holdings, method, get_calc_settings(session, org_id), org_id, scenario, horizon)
    return {"org_id": org_id, "org": dict(org) if org else None, "rollup": rollup}


def build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None,
                              period_end=None):
    """The asset manager's holdings-book TCFD physical-risk disclosure — physical-risk exposure by hazard,
    EU-Taxonomy status, and portfolio climate-risk CONCENTRATION. Live (/disclosure) and frozen (filing
    snapshot) callers share this so a filing can't drift from the live view. This is the HOLDINGS-book
    disclosure, distinct from the fund-level SFDR PAI statement (separate data model). entity_ids /
    value_weights scope + consolidation-weight the book for a per-entity or group filing (None = whole org)."""
    from services.money.params import for_org
    from services.portfolio_engine import exposure_by_hazard
    method = for_org(session, org_id, period_end)
    holdings = _holdings_with_risk(session, org_id, scenario, horizon, method=method,
                                   entity_ids=entity_ids, value_weights=value_weights, translation=translation)
    hazards = exposure_by_hazard(holdings, "position_value_eur", method)
    tax = defaultdict(lambda: {"count": 0, "value_eur": 0.0})
    for h in holdings:
        tax[h["taxonomy_status"]]["count"] += 1
        tax[h["taxonomy_status"]]["value_eur"] += h["position_value_eur"] or 0
    return {
        "rollup": _rollup(holdings, method, get_calc_settings(session, org_id), org_id, scenario, horizon),
        "holdings": holdings,
        "by_hazard": hazards,
        "taxonomy": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in tax.items()},
        "concentration": portfolio_concentration(holdings),
        "method": method.record(),
    }


@router.get("/disclosure", summary="Physical-risk exposure + EU Taxonomy status — the portfolio-level "
                                    "metric TCFD's asset-owner/manager guidance recommends disclosing")
def disclosure(session: DbSession, org_id: OrgId,
               scenario: str = Query("baseline"), horizon: str = Query("current")):
    """TCFD's guidance for asset owners/managers recommends disclosing physical-risk
    exposure value-weighted across holdings -- this is that metric. NOT framed as
    an SFDR Principal Adverse Impact indicator: SFDR's mandatory PAI set has no
    direct physical-climate-risk metric (only fossil-fuel exposure/energy
    inefficiency for real estate holdings specifically, PAI 17/18)."""
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            **build_disclosure_snapshot(session, org_id, scenario, horizon)}


# Required fields keep an asset manager's actual holdings data recognizable
# (name, position size, sector); nace_code is optional but -- unlike banking's
# or real estate's upload today -- IS supported directly, since a manager's own
# data typically already carries a NACE classification.
# HOLDING_TEMPLATE_FIELDS lives in services/ingest/templates.py (shared with the intake pipeline)
REQUIRED_HOLDING_COLUMNS = [f["name"] for f in HOLDING_TEMPLATE_FIELDS if f["required"]]


@router.get("/holding/{holding_id}", summary="One holding — full projection + provenance")
def holding_detail(holding_id: str, session: DbSession, caller_org: OrgId):
    own_or_404(session, "portfolio_entities", "entity_id", holding_id, caller_org, "Holding")   # only your own org's record
    org_id = get_entity_org(session, holding_id)
    from services.money.params import for_org
    method = for_org(session, org_id)
    row = get_entity_with_risk(session, holding_id, "baseline", "current", method=method,
                                extra_calc=_assetmgmt_extra(method))
    holding = {
        "holding_id": row["entity_id"], "org_id": row["org_id"], "holding_name": row["entity_name"],
        "sector": row["sector"], "nace_code": row["nace_code"], "country": row["country"],
        "region": row["region"], "lat": row["lat"], "lon": row["lon"], "h3_cell": row["h3_cell"],
        "position_value_eur": row["primary_value_eur"], "flagged": row["flagged"],
        "taxonomy_status": row["taxonomy_status"], "taxonomy_activity_ref": row["taxonomy_activity_ref"],
        "taxonomy_reasoning": row["taxonomy_reasoning"],
        "borrower_entity_id": row["borrower_entity_id"], "minimum_safeguards_status": row["minimum_safeguards_status"],
    }
    audit = session.execute(text("""
        SELECT actor_user_id::text AS actor_user_id, action, detail, created_at
        FROM access_audit_log WHERE target_type = 'assetmgmt_holding' AND target_id = :h
        ORDER BY seq DESC LIMIT 5
    """), {"h": holding_id}).mappings().all()
    return {
        "holding": holding, "risks": row["risks"], "climate_var": row["valuation"],
        "valuation_audit": [dict(x) for x in audit],
    }


class HoldingValuationOverrideRequest(BaseModel):
    discount_pct: float = Field(..., ge=0, le=100)
    reason: Optional[str] = None


@router.post("/holding/{holding_id}/valuation-override",
             summary="Override the recommended climate-VaR discount (audited)")
def override_holding_valuation(holding_id: str, body: HoldingValuationOverrideRequest,
                                session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    org_id = get_entity_org(session, holding_id)
    if not org_id:
        raise HTTPException(status_code=404, detail="holding not found")
    if org_id != ctx["org"]["org_id"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Holding does not belong to your organization"})

    result = engine_apply_override(session, holding_id, body.discount_pct, ctx["user"]["id"], body.reason)
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="holding.valuation.override", target_type="assetmgmt_holding", target_id=holding_id,
                detail={"from_pct": result["from_pct"], "to_pct": body.discount_pct, "reason": body.reason})
    return {"holding_id": holding_id, "override_discount_pct": body.discount_pct,
            "overridden_at": result["overridden_at"].isoformat()}


@router.delete("/holding/{holding_id}/valuation-override",
               summary="Clear an override, revert to the recommended discount (audited)")
def clear_holding_valuation_override(holding_id: str, session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    prior = engine_clear_override(session, holding_id)
    if not prior:
        return {"holding_id": holding_id, "cleared": False}
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="holding.valuation.override_cleared", target_type="assetmgmt_holding", target_id=holding_id,
                detail={"from_pct": prior["override_discount_pct"], "to_pct": None})
    return {"holding_id": holding_id, "cleared": True}


@router.get("/holdings/template.xlsx", summary="Download the holdings book upload template (Excel)")
def holdings_template_xlsx():
    buf = build_template_workbook(HOLDING_TEMPLATE_FIELDS)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=tellumen_holdings_template.xlsx"})


@router.post("/holdings/validate", summary="Check a holdings book (CSV or Excel) before importing — nothing is saved")
async def validate_holdings(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                            declared_row_count: Optional[str] = Form(None), declared_totals: Optional[str] = Form(None),
                         mapping_profile_id: Optional[str] = Form(None),
                         currency: Optional[str] = Form(None), book_date: Optional[str] = Form(None)):
    """Dry run of every intake check (security inspection, required columns, row checks, receipt, transformation and
    the gate the import will enforce). Nothing is stored or written."""
    from api.services.intake_http import declared_from_form, preview
    return preview(session, ctx["org"]["org_id"], "assetmgmt_holdings", await file.read(), file.filename,
                   declared_from_form(declared_row_count, declared_totals), mapping_profile_id,
                   currency=currency, book_date=book_date)


@router.post("/holdings/upload", summary="Import holdings (CSV or Excel) into your portfolio")
async def upload_holdings(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                          declared_row_count: Optional[str] = Form(None), declared_totals: Optional[str] = Form(None),
                          approval_reason: Optional[str] = Form(None), mapping_profile_id: Optional[str] = Form(None),
                         currency: Optional[str] = Form(None), book_date: Optional[str] = Form(None)):
    """Runs the holdings book through the intake pipeline (services/intake/pipeline.py): the file is stored write-once,
    security-inspected and malware-scanned, then checked. Every check passed → imported now (200). A check failed →
    sent to a second person for approval with your reason (202; nothing lands until approved). Scanner unavailable
    where required → held (202). Nothing valid, or refused on security grounds → 422, and the attempt is recorded."""
    from api.services.intake_http import declared_from_form, submit
    return submit(session, ctx["org"]["org_id"], "assetmgmt_holdings", await file.read(), file.filename,
                  user_id=ctx["user"]["id"], declared=declared_from_form(declared_row_count, declared_totals),
                  reason=approval_reason, mapping_profile_id=mapping_profile_id,
                  currency=currency, book_date=book_date)


@router.get("/portfolio.xlsx", summary="Portfolio climate VaR book (Excel)")
def portfolio_xlsx(session: DbSession, org_id: OrgId,
                    scenario: str = Query("baseline"), horizon: str = Query("current")):
    from services.money.params import for_org
    holdings = _holdings_with_risk(session, org_id, scenario, horizon, method=for_org(session, org_id))
    headers = ["holding_name", "sector", "region", "country", "position_value_eur",
               "headline_hazard", "headline_score", "risk_bucket", "discounted_value_eur",
               "flagged", "taxonomy_status"]
    rows = [[h["holding_name"], h["sector"], h["region"], h["country"], h["position_value_eur"],
             h["headline_hazard"], h["headline_score"], h["headline_bucket"] or "unscored",
             h["climate_var"]["discounted_value_eur"], "yes" if h["flagged"] else "no",
             h["taxonomy_status"]] for h in holdings]
    buf = build_export_workbook(headers, rows, sheet_name="Portfolio climate VaR")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=nordkap-portfolio-climate-var.xlsx"})

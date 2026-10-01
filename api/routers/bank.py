"""
Banking flagship — public read-only endpoints for the loan-book workspace.

Projects the golden source (canonical_scores) onto a bank's assets by H3 cell,
via the shared portfolio engine (services/portfolio_engine.py) and the unified
v_portfolio_entity_physical_risk view -- the same engine real estate and asset
management use, so a fix or a new calc-settings trigger only needs writing once
(see the b9c0d1e2f3a4 migration's docstring for the duplication this replaced).
Every figure carries its model_version + vintage so the disclosure is
defensible. No auth (aggregate read), mirroring platform.py.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import CurrentUser, DbSession, own_or_404, tenant_resolver
from api.services.rbac import write_audit
from ml.scoring.valuation_discount import value_loss_band
from services.ingest.templates import ASSET_TEMPLATE_FIELDS  # noqa: F401 — re-exported
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
from services.scoring.loan_transition import collateral_stranding_overlay, loan_transition_overlay
from services.templates.workbook import build_export_workbook, build_template_workbook

EXT_BANKING_COLUMNS = [
    "CAST(x.annual_revenue_eur AS FLOAT) AS annual_revenue_eur",
    "x.taxonomy_status", "x.taxonomy_activity", "x.dnsh_assessment",
    "x.expected_lifespan_years", "x.gics_code",
    "CAST(x.ghg_emissions_scope1_tco2e AS FLOAT) AS ghg_emissions_scope1_tco2e",
    "CAST(x.ghg_emissions_scope2_tco2e AS FLOAT) AS ghg_emissions_scope2_tco2e",
    "CAST(x.ghg_emissions_scope3_tco2e AS FLOAT) AS ghg_emissions_scope3_tco2e",
    "CAST(x.outstanding_loan_balance_eur AS FLOAT) AS outstanding_loan_balance_eur",
    "x.loan_origination_date",
    "CAST(x.counterparty_evic_eur AS FLOAT) AS counterparty_evic_eur",   # PCAF attribution denominator
    # per-loan attributes the customer provides (Data → provide by Excel): feed the Pillar 3 integrated cells
    "CAST(x.residual_maturity_years AS FLOAT) AS residual_maturity_years",
    "x.epc_label", "x.ifrs9_stage",
    "CAST(x.emission_intensity AS FLOAT) AS emission_intensity",   # IEA-unit physical intensity → Template 3 / EU CRFR4 (pending adoption) alignment
    "x.counterparty_govt_level",   # central/regional/local — scopes the GAR Art. 7(1) government exclusion
    "x.no_stated_maturity",   # EBA Q&A 2022_6515 — equity/perpetual instruments route to the >20yr bucket
    # Pillar 3 Templates 1 and 5 (spec its_2024_3172): row population and the institution-supplied columns
    "x.counterparty_sector", "x.immovable_collateral",
    "CAST(x.accumulated_impairment_eur AS FLOAT) AS accumulated_impairment_eur",
    "x.pab_excluded", "x.ccm_sustainable", "x.emissions_company_reported",
    # Pillar 3 Templates 2, 7, 8, 9 (GAR / BTAR / energy efficiency of collateral)
    "x.instrument_type", "x.counterparty_subsector", "x.nfrd_subject", "x.loan_purpose", "x.trading_book",
    "x.taxonomy_objective", "x.taxonomy_contribution", "x.specialised_lending",
    "CAST(x.ep_score_kwh_m2 AS FLOAT) AS ep_score_kwh_m2", "x.ep_score_estimated",
    # EU Taxonomy Art. 8 (Annex V/VI of Del. Reg. 2021/2178): CSRD scope of the counterparty (2026/73 templates), the
    # counterparty in the issuer reference, and its own KPIs — the latest year stated, per basis:objective — frozen
    # with the filing (services.governance.taxonomy_gar values general-purpose exposures by them)
    "x.csrd_subject", "x.counterparty_issuer_id::text AS counterparty_issuer_id",
    # the one store of an issuer's KPIs (services.issuer_taxonomy): the latest year stated; the organisation's own figure
    # over a shared vendor one; 'all' is a total whose split by objective is not stated
    """(SELECT jsonb_object_agg(k.basis || ':' || k.objective, jsonb_build_object(
            'eligible', k.eligible_pct, 'aligned', k.aligned_pct, 'transitional', k.transitional_pct,
            'enabling', k.enabling_pct, 'year', k.reporting_year))
        FROM (SELECT DISTINCT ON (k1.basis, k1.objective) k1.* FROM issuer_taxonomy_kpi k1
              WHERE k1.issuer_id = x.counterparty_issuer_id AND (k1.org_id = e.org_id OR k1.org_id IS NULL)
                AND k1.reporting_year = (SELECT max(k2.reporting_year) FROM issuer_taxonomy_kpi k2
                                         WHERE k2.issuer_id = x.counterparty_issuer_id
                                           AND (k2.org_id = e.org_id OR k2.org_id IS NULL))
              ORDER BY k1.basis, k1.objective, (k1.org_id IS NULL)) k
       ) AS counterparty_taxonomy_kpi""",
]


_P3_ATTRS = ("counterparty_sector", "immovable_collateral", "accumulated_impairment_eur", "pab_excluded", "ccm_sustainable",
             "emissions_company_reported", "instrument_type", "counterparty_subsector", "nfrd_subject", "loan_purpose",
             "trading_book", "taxonomy_objective", "taxonomy_contribution", "specialised_lending", "ep_score_kwh_m2",
             "ep_score_estimated",
             # EU Taxonomy Art. 8 (services.governance.taxonomy_gar): CSRD scope and the counterparty's own KPIs
             "csrd_subject", "counterparty_issuer_id", "counterparty_taxonomy_kpi")


def _ltv_kwargs(row):
    return {"outstanding_balance_eur": row.get("outstanding_loan_balance_eur")}


def _map_asset_list_row(row):
    """Shared-engine row -> the exact shape /portfolio, /summary, /disclosure
    have always returned (frontend + frozen submission snapshots rely on
    these exact field names, so this rename is the ENTIRE cost of sharing
    the fetch/join/headline/valuation layer with the other 3 verticals)."""
    return {
        "asset_id": row["entity_id"], "asset_name": row["entity_name"], "asset_type": row["entity_type"],
        "sector": row["sector"], "country": row["country"], "region": row["region"],
        "lat": row["lat"], "lon": row["lon"], "h3_cell": row["h3_cell"],
        "value_eur": row["primary_value_eur"],
        "revenue_eur": row["annual_revenue_eur"], "taxonomy_status": row["taxonomy_status"],
        "construction_year": row["year_built"], "nace_code": row["nace_code"],
        "ghg1": row["ghg_emissions_scope1_tco2e"], "ghg2": row["ghg_emissions_scope2_tco2e"],
        "ghg3": row["ghg_emissions_scope3_tco2e"],
        "outstanding_loan_balance_eur": row["outstanding_loan_balance_eur"],
        "loan_origination_date": row["loan_origination_date"],
        "evic_eur": row.get("counterparty_evic_eur"),
        "residual_maturity_years": row.get("residual_maturity_years"),
        "epc_label": row.get("epc_label"), "ifrs9_stage": row.get("ifrs9_stage"),
        "emission_intensity": row.get("emission_intensity"),   # feeds transition_alignment Template 3 / EU CRFR4 (pending adoption) (IEA)
        "counterparty_govt_level": row.get("counterparty_govt_level"),   # feeds GAR Art. 7(1) exclusion scoping
        "no_stated_maturity": row.get("no_stated_maturity"),   # EBA Q&A 2022_6515 — routes to the >20yr bucket
        **{k: row.get(k) for k in _P3_ATTRS},   # Pillar 3 Templates 1 and 5 (row population + supplied columns)
        "hazards": row["hazards"], "headline_score": row["headline_score"],
        "headline_bucket": row["headline_bucket"], "headline_hazard": row["headline_hazard"],
        "valuation": row["valuation"],
    }

router = APIRouter(prefix="/v1/bank", tags=["Banking"])

DEMO_ORG = "11111111-1111-4111-8111-111111111111"
BUCKET_RANK = {"VH": 4, "H": 3, "M": 2, "L": 1}

_bearer = HTTPBearer(auto_error=False)


resolve_org = tenant_resolver(DEMO_ORG)             # one implementation for every sector API (api/deps.py)
OrgId = Annotated[str, Depends(resolve_org)]


def _assets_with_risk(session, org_id, scenario, horizon, *, method, entity_ids=None, value_weights=None, translation=None):
    """All of an org's assets (metadata) + their per-hazard projected risk, valued on the bank's stated method for the
    year (services.money.params.Method). Thin wrapper over the shared portfolio engine (services/portfolio_engine.py).
    entity_ids / value_weights scope + consolidation-weight the book for per-entity / group filings."""
    rows = fetch_entities_with_risk(session, org_id, "banking", scenario, horizon, method=method,
                                     ext_table="ext_banking", ext_columns=EXT_BANKING_COLUMNS,
                                     valuation_kwargs=_ltv_kwargs,
                                     entity_ids=entity_ids, value_weights=value_weights, translation=translation)
    return [_map_asset_list_row(r) for r in rows]


def _rollup(assets, method):
    """The book's totals: 'at material physical risk' is the bank's stated level (method.at_risk_level); the
    climate-adjusted value is that of the scored assets (services.portfolio_engine)."""
    from services.portfolio_engine import climate_adjusted_total, value_at_risk
    by_bucket = defaultdict(lambda: {"count": 0, "value": 0.0})
    for a in assets:
        b = a["headline_bucket"] or "none"
        by_bucket[b]["count"] += 1
        by_bucket[b]["value"] += a["value_eur"] or 0
    var = value_at_risk(assets, "value_eur", method)
    return {
        "n_assets": len(assets),
        "n_scored": sum(1 for a in assets if a["headline_bucket"]),
        "total_value_eur": round(sum(a["value_eur"] or 0 for a in assets)),
        **var, "n_high": var["n_at_risk"],
        **climate_adjusted_total(assets, "value_eur"),
        "expected_value_loss_band": value_loss_band(method, assets),
        **({"gap": method.gap_text()} if method.gap_text() else {}),
        "n_overridden": sum(1 for a in assets if a["valuation"]["is_overridden"]),
        "by_bucket": {k: {"count": v["count"], "value_eur": round(v["value"])} for k, v in by_bucket.items()},
        "top_assets": sorted(
            [a for a in assets if a["headline_score"] is not None],
            key=lambda a: -a["headline_score"])[:8],
    }


@router.get("/portfolio", summary="Loan book projected onto the golden source")
def portfolio(session: DbSession, org_id: OrgId,
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    from services.money.params import for_org
    method = for_org(session, org_id)
    assets = _assets_with_risk(session, org_id, scenario, horizon, method=method)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": _rollup(assets, method), "assets": assets,
            "transition": loan_transition_overlay(method, assets, scenario, horizon),
            "collateral_stranding": collateral_stranding_overlay(method, assets)}


@router.get("/forward-risk", summary="Forward-change decision signal — scenario risk migration + runway")
def forward_risk_ep(session: DbSession, org_id: OrgId, scenario: str = Query("disorderly_2c")):
    from services.intelligence.forward_risk import forward_risk
    from services.money.params import for_org
    return forward_risk(session, org_id, "banking", scenario, for_org(session, org_id))


@router.get("/expected-loss", summary="Climate expected loss (€) — annual + lifetime, maturity-matched")
def expected_loss_ep(session: DbSession, org_id: OrgId, scenario: str = Query("disorderly_2c")):
    from services.intelligence.expected_loss import bank_expected_loss
    from services.money.params import for_org
    return bank_expected_loss(session, org_id, scenario, method=for_org(session, org_id))


@router.get("/summary", summary="Command-center rollup")
def summary(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id = :o"
    ), {"o": org_id}).mappings().first()
    from services.money.params import for_org
    method = for_org(session, org_id)
    assets = _assets_with_risk(session, org_id, scenario, horizon, method=method)
    return {"org_id": org_id, "org": dict(org) if org else None, "rollup": _rollup(assets, method)}


def _hazard_rollup(assets, method):
    """Physical risk by hazard, EU-Taxonomy alignment and financed emissions —
    the three blocks the TCFD/EU-Taxonomy disclosure pack adds on top of _rollup()."""
    from services.portfolio_engine import exposure_by_hazard
    hazards = exposure_by_hazard(assets, "value_eur", method)
    # EU-Taxonomy alignment, value-weighted
    tax = defaultdict(lambda: {"count": 0, "value_eur": 0.0})
    for a in assets:
        t = a.get("taxonomy_status") or "unknown"
        tax[t]["count"] += 1
        tax[t]["value_eur"] += a["value_eur"] or 0
    # financed emissions — REAL PCAF attribution (attribution factor = outstanding / counterparty EVIC, capped
    # at 1.0) for every counterparty that carries EVIC; disclosed separately for the rest, never silently
    # summed in as if attributed. See services/scoring/pcaf.py (the one formula every vertical shares).
    from services.scoring.pcaf import attributed_financed_emissions
    pcaf = attributed_financed_emissions(assets, exposure_key="outstanding_loan_balance_eur", evic_key="evic_eur",
                                         scope_keys=("ghg1", "ghg2", "ghg3"))
    ghg = pcaf["attributed"]   # kept as the existing key/shape (scope1/scope2/scope3) so nothing downstream breaks
    return {
        "by_hazard": hazards,
        "taxonomy": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in tax.items()},
        "financed_emissions_tco2e": ghg,
        "financed_emissions_pcaf": pcaf,
    }


def loan_book(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None, period_end=None):
    """(the loan book per exposure, the bank's stated method for the year) — scoped / weighted / translated like the
    disclosure snapshot. The EU Taxonomy Art. 8 report freezes this book (services.governance.bank_taxonomy_report)."""
    from services.money.params import for_org
    method = for_org(session, org_id, period_end)
    return _assets_with_risk(session, org_id, scenario, horizon, method=method, entity_ids=entity_ids,
                             value_weights=value_weights, translation=translation), method


def build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None,
                              period_end=None):
    """The single source of truth for the book's live analytics and the Pillar 3 ESG filing: live callers
    (GET /disclosure) and frozen callers (submission snapshots) both go through
    this, so a submission's numbers can never drift from what the live view shows
    at the moment it's taken. entity_ids / value_weights scope + consolidation-weight
    the book for a per-entity or consolidated-group filing (None = whole org). period_end: the financial year the
    figures are for — its stated method is used (None = the organisation's reporting period, the live views)."""
    from services.money.params import for_org
    method = for_org(session, org_id, period_end)
    assets = _assets_with_risk(session, org_id, scenario, horizon, method=method,
                               entity_ids=entity_ids, value_weights=value_weights, translation=translation)
    # Climate expected loss (€ annual + lifetime, maturity-matched) — the IFRS-9/ECL-relevant number. Physical
    # EL is scenario-driven; under 'baseline' it uses the warming pathway the calc-settings default, so freeze it
    # under a forward scenario. Whole-org only for now (EL is not yet entity-scoped) — omitted on scoped filings.
    # It is computed from the stored EUR book, so it is also omitted when the filing presents another currency or
    # removed group-internal exposures (it would no longer describe the same book).
    ccy = translation.presentation if translation is not None else "EUR"
    units_per_eur = 1.0
    if ccy != "EUR":
        from services.governance.translation import from_eur
        units_per_eur = from_eur(session, translation, 1.0)
    el = None
    if entity_ids is None and (translation is None or (translation.identity() and not translation.eliminations)):
        from services.intelligence.expected_loss import bank_expected_loss
        el_scenario = scenario if scenario and scenario != "baseline" else "disorderly_2c"
        el = bank_expected_loss(session, org_id, el_scenario, method=method)
    return {
        "rollup": _rollup(assets, method),
        "assets": assets,
        "transition": loan_transition_overlay(method, assets, scenario, horizon, eur_per_unit=1.0 / units_per_eur),
        "collateral_stranding": collateral_stranding_overlay(method, assets),
        "expected_loss": el,
        **_hazard_rollup(assets, method),
        "method": method.record(),
    }


@router.get("/disclosure", summary="Live analytics of the projected book (physical risk, financed emissions, credit-risk overlays)")
def disclosure(session: DbSession, org_id: OrgId,
               scenario: str = Query("baseline"), horizon: str = Query("current"),
               slim: bool = Query(False, description="omit the per-asset array (aggregates only) — for the "
                                                     "Analytics scenario grid, which needs only the totals")):
    snapshot = build_disclosure_snapshot(session, org_id, scenario, horizon)
    if slim:
        snapshot.pop("assets", None)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon, **snapshot}


@router.get("/asset/{asset_id}", summary="One asset — full projection + provenance")
def asset_detail(asset_id: str, session: DbSession, caller_org: OrgId):
    own_or_404(session, "portfolio_entities", "entity_id", asset_id, caller_org, "Asset")   # only your own org's record
    org_id = get_entity_org(session, asset_id)
    from services.money.params import for_org
    # Pre-existing quirk, preserved exactly: this endpoint has no scenario/horizon
    # params, so its headline is picked across EVERY scenario/horizon this asset
    # has ever been scored under (scope_headline_to_query=False) -- can disagree
    # with the portfolio list's scenario-scoped headline for the same asset.
    row = get_entity_with_risk(session, asset_id, "baseline", "current", method=for_org(session, org_id),
                                ext_table="ext_banking", ext_columns=EXT_BANKING_COLUMNS,
                                valuation_kwargs=_ltv_kwargs, scope_headline_to_query=False)
    asset = {
        "asset_id": row["entity_id"], "org_id": row["org_id"], "asset_name": row["entity_name"],
        "asset_type": row["entity_type"], "sector": row["sector"], "country": row["country"],
        "region": row["region"], "lat": row["lat"], "lon": row["lon"], "h3_cell": row["h3_cell"],
        "value_eur": row["primary_value_eur"], "revenue_eur": row["annual_revenue_eur"],
        "taxonomy_status": row["taxonomy_status"], "taxonomy_activity": row["taxonomy_activity"],
        "dnsh_assessment": row["dnsh_assessment"], "construction_year": row["year_built"],
        "expected_lifespan_years": row["expected_lifespan_years"], "nace_code": row["nace_code"],
        "gics_code": row["gics_code"],
        "ghg_scope1": row["ghg_emissions_scope1_tco2e"], "ghg_scope2": row["ghg_emissions_scope2_tco2e"],
        "ghg_scope3": row["ghg_emissions_scope3_tco2e"],
        "outstanding_loan_balance_eur": row["outstanding_loan_balance_eur"],
        "loan_origination_date": row["loan_origination_date"],
        "evic_eur": row.get("counterparty_evic_eur"),
        "borrower_entity_id": row["borrower_entity_id"], "minimum_safeguards_status": row["minimum_safeguards_status"],
    }
    audit = session.execute(text("""
        SELECT actor_user_id::text AS actor_user_id, action, detail, created_at
        FROM access_audit_log WHERE target_type = 'bank_asset' AND target_id = :a
        ORDER BY created_at DESC LIMIT 5
    """), {"a": asset_id}).mappings().all()
    return {
        "asset": asset, "risks": row["risks"], "valuation": row["valuation"],
        "valuation_audit": [dict(x) for x in audit],
    }


class ValuationOverrideRequest(BaseModel):
    discount_pct: float = Field(..., ge=0, le=100)
    reason: Optional[str] = None


@router.post("/asset/{asset_id}/valuation-override", summary="Override the recommended valuation discount (audited)")
def override_valuation(asset_id: str, body: ValuationOverrideRequest, session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    org_id = get_entity_org(session, asset_id)
    if not org_id:
        raise HTTPException(status_code=404, detail="Asset not found.")
    if org_id != ctx["org"]["org_id"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Asset does not belong to your organization"})

    result = engine_apply_override(session, asset_id, body.discount_pct, ctx["user"]["id"], body.reason)
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="asset.valuation.override", target_type="bank_asset", target_id=asset_id,
                detail={"from_pct": result["from_pct"], "to_pct": body.discount_pct, "reason": body.reason})
    return {"asset_id": asset_id, "override_discount_pct": body.discount_pct,
            "overridden_at": result["overridden_at"].isoformat()}


@router.delete("/asset/{asset_id}/valuation-override", summary="Clear an override, revert to the recommended discount (audited)")
def clear_asset_valuation_override(asset_id: str, session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    prior = engine_clear_override(session, asset_id)
    if not prior:
        return {"asset_id": asset_id, "cleared": False}
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="asset.valuation.override_cleared", target_type="bank_asset", target_id=asset_id,
                detail={"from_pct": prior["override_discount_pct"], "to_pct": None})
    return {"asset_id": asset_id, "cleared": True}


# A real "loan tape" -- see ml/scoring/valuation_discount.py's LTV functions and
# services/templates/workbook.py's template. appraised_value_eur is the CSV/
# template-facing name (industry-recognizable); it maps onto the existing
# asset_value_eur DB column (a disclosed rename, not a churny migration).
# ASSET_TEMPLATE_FIELDS lives in services/ingest/templates.py (shared with the intake pipeline)
REQUIRED_ASSET_COLUMNS = [f["name"] for f in ASSET_TEMPLATE_FIELDS if f["required"]]
SAFEGUARDS_STATUSES = {"compliant", "non_compliant"}


@router.get("/assets/template.xlsx", summary="Download the loan-tape upload template (Excel)")
def assets_template_xlsx():
    buf = build_template_workbook(ASSET_TEMPLATE_FIELDS)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=tellumen_loan_tape_template.xlsx"})


@router.post("/assets/validate", summary="Check a loan tape (CSV or Excel) before importing — nothing is saved")
async def validate_assets(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                          declared_row_count: Optional[str] = Form(None), declared_totals: Optional[str] = Form(None),
                         mapping_profile_id: Optional[str] = Form(None),
                         currency: Optional[str] = Form(None), book_date: Optional[str] = Form(None)):
    """Dry run of every intake check (security inspection, required columns, row checks, receipt, transformation and
    the gate the import will enforce). Nothing is stored or written."""
    from api.services.intake_http import declared_from_form, preview
    return preview(session, ctx["org"]["org_id"], "bank_assets", await file.read(), file.filename,
                   declared_from_form(declared_row_count, declared_totals), mapping_profile_id,
                   currency=currency, book_date=book_date)


@router.post("/assets/upload", summary="Import a loan tape (CSV or Excel) into your loan book")
async def upload_assets(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                        declared_row_count: Optional[str] = Form(None), declared_totals: Optional[str] = Form(None),
                        approval_reason: Optional[str] = Form(None), mapping_profile_id: Optional[str] = Form(None),
                         currency: Optional[str] = Form(None), book_date: Optional[str] = Form(None)):
    """Runs the loan tape through the intake pipeline (services/intake/pipeline.py): the file is stored write-once,
    security-inspected and malware-scanned, then checked. Every check passed → imported now (200). A check failed →
    sent to a second person for approval with your reason (202; nothing lands until approved). Scanner unavailable
    where required → held (202). Nothing valid, or refused on security grounds → 422, and the attempt is recorded."""
    from api.services.intake_http import declared_from_form, submit
    return submit(session, ctx["org"]["org_id"], "bank_assets", await file.read(), file.filename,
                  user_id=ctx["user"]["id"], declared=declared_from_form(declared_row_count, declared_totals),
                  reason=approval_reason, mapping_profile_id=mapping_profile_id,
                  currency=currency, book_date=book_date)


# ── Per-loan regulatory attributes the engine can't derive from location — provided in bulk by Excel, matched to
#    the book by asset name, and written to the loan's record (feeds Pillar 3 maturity/EPC/staging + expected loss).
ATTR_TEMPLATE_FIELDS = [
    {"name": "external_ref", "required": False, "label": "Your asset ID", "kind": "text", "description": "Your own loan id, as sent with the loan tape — matched first.", "example": "REF-000123"},
    {"name": "asset_name", "required": False, "label": "Asset name", "kind": "text", "description": "Used when there is no asset ID; must match exactly ONE asset in your book (an ambiguous name is refused).", "example": "Frankfurt Tower 1"},
    {"name": "residual_maturity_years", "required": False, "label": "Residual maturity (years)", "kind": "number", "range": [0, 100], "description": "Remaining life of the loan, in years.", "example": "7"},
    {"name": "epc_label", "required": False, "label": "EPC label", "kind": "enum", "allowed": ["A", "B", "C", "D", "E", "F", "G"], "description": "Energy Performance Certificate grade of the collateral.", "example": "C"},
    {"name": "ifrs9_stage", "required": False, "label": "IFRS-9 stage", "kind": "enum", "allowed": ["1", "2", "3"], "description": "IFRS-9 credit-risk stage.", "example": "1"},
    {"name": "emission_intensity", "required": False, "label": "Emission intensity (IEA unit)", "kind": "money", "description": "Counterparty PHYSICAL carbon intensity in the IEA sector metric's own unit (gCO₂/kWh power, tCO₂/t steel/cement, …) — feeds the Pillar 3 Template 3 / EU CRFR4 (pending adoption) IEA-alignment distance. NOT the financial tCO₂e/€M intensity.", "example": "310"},
    {"name": "counterparty_evic_eur", "required": False, "label": "Counterparty EVIC", "kind": "money",
     "description": "Backfill EVIC on a loan already in your book, so it counts toward PCAF-attributed financed emissions without re-uploading the whole tape. In the currency you declare (or the row's currency).", "example": "185000000"},
    {"name": "currency", "required": False, "label": "Currency", "kind": "text", "description": "ISO 4217 code of this row's EVIC; overrides the currency declared for the upload.", "example": "USD"},
    {"name": "book_date", "required": False, "label": "Book date", "kind": "date", "description": "YYYY-MM-DD the EVIC describes (converted at that day's rate); overrides the declared book date.", "example": "2026-06-30"},
    {"name": "counterparty_govt_level", "required": False, "label": "Counterparty government level", "kind": "enum", "allowed": ["central", "regional", "local"],
     "description": "Required to correctly scope EU Taxonomy Art. 7(1)'s central-government exclusion — leave blank for non-government counterparties.", "example": "central"},
    {"name": "no_stated_maturity", "required": False, "label": "No stated maturity", "kind": "boolean",
     "description": "True for an exposure with no stated maturity BY ITS NATURE (equity, perpetual instrument, "
     "etc.) — per EBA Q&A 2022_6515, routes it to the '>20 years' Pillar 3 maturity bucket.", "example": "true"},
    {"name": "counterparty_sector", "required": False, "label": "Counterparty sector (FINREP)", "kind": "enum",
     "allowed": ["central_bank", "general_government", "credit_institution", "other_financial_corporation", "non_financial_corporation", "household"],
     "description": "The counterparty's FINREP sector (Annex V, Part 1). Pillar 3 Templates 1 and 5 show exposures to non-financial corporations by NACE sector.", "example": "non_financial_corporation"},
    {"name": "immovable_collateral", "required": False, "label": "Immovable-property collateral", "kind": "enum",
     "allowed": ["residential", "commercial", "repossessed", "none"],
     "description": "Collateral by predominant use (FINREP Annex V, Part 1), or 'repossessed' for collateral obtained by taking possession — Pillar 3 Template 5 rows 10–12.", "example": "residential"},
    {"name": "accumulated_impairment_eur", "required": False, "label": "Accumulated impairment", "kind": "money",
     "description": "Accumulated impairment, accumulated negative changes in fair value due to credit risk and provisions, as a positive amount — Pillar 3 Template 1 (f–h) and Template 5 (m–o). In the currency you declare (or the row's currency).", "example": "125000"},
    {"name": "pab_excluded", "required": False, "label": "Excluded from EU Paris-aligned Benchmarks", "kind": "boolean",
     "description": "True if the counterparty is excluded from EU Paris-aligned Benchmarks under Art 12(1)(d)–(g) and 12(2) of Regulation (EU) 2020/1818 — Pillar 3 Template 1 (b).", "example": "false"},
    {"name": "ccm_sustainable", "required": False, "label": "Environmentally sustainable (CCM)", "kind": "boolean",
     "description": "True if the exposure is environmentally sustainable for climate change mitigation under the EU Taxonomy — Pillar 3 Template 1 (c).", "example": "false"},
    {"name": "emissions_company_reported", "required": False, "label": "Emissions reported by the company", "kind": "boolean",
     "description": "True if the counterparty's emissions figures come from its own reporting (not estimated) — Pillar 3 Template 1 (k).", "example": "true"},
    {"name": "instrument_type", "required": False, "label": "Instrument type (FINREP)", "kind": "enum",
     "allowed": ["loans_and_advances", "debt_securities", "equity_instruments", "derivatives", "on_demand_interbank", "cash", "other_assets"],
     "description": "The asset's FINREP instrument — Pillar 3 Template 7 / 9.1 rows by instrument and the assets excluded from the GAR numerator.", "example": "loans_and_advances"},
    {"name": "counterparty_subsector", "required": False, "label": "Other financial corporation type", "kind": "enum",
     "allowed": ["investment_firm", "management_company", "insurance_undertaking"],
     "description": "For an other financial corporation: investment firm, management company or insurance undertaking — Pillar 3 Template 7 rows 8-19.", "example": "investment_firm"},
    {"name": "nfrd_subject", "required": False, "label": "Counterparty subject to NFRD / CSRD disclosure", "kind": "boolean",
     "description": "True if the counterparty is subject to the non-financial reporting disclosure obligations — decides GAR (Template 7) versus BTAR (Template 9).", "example": "true"},
    {"name": "loan_purpose", "required": False, "label": "Loan purpose", "kind": "enum",
     "allowed": ["building_renovation", "motor_vehicle", "housing", "other"],
     "description": "Building renovation / motor vehicle (household rows) or housing (local-government rows) — Pillar 3 Templates 7 and 9.1.", "example": "building_renovation"},
    {"name": "trading_book", "required": False, "label": "Held for trading", "kind": "boolean",
     "description": "True for a trading-book asset — excluded from both the GAR numerator and denominator (Template 7 row 48).", "example": "false"},
    {"name": "taxonomy_objective", "required": False, "label": "Taxonomy objective", "kind": "enum", "allowed": ["ccm", "cca"],
     "description": "Climate change mitigation (ccm) or adaptation (cca): the objective a Taxonomy-eligible or aligned exposure contributes to — Template 7 columns b-k.", "example": "ccm"},
    {"name": "taxonomy_contribution", "required": False, "label": "Taxonomy contribution type", "kind": "enum",
     "allowed": ["transitional", "enabling", "adaptation", "none"],
     "description": "For an aligned exposure: transitional, enabling or adaptation activity — Template 7 'of which' columns.", "example": "enabling"},
    {"name": "specialised_lending", "required": False, "label": "Specialised lending", "kind": "boolean",
     "description": "True for specialised lending — Template 7 'of which specialised lending' columns.", "example": "false"},
    {"name": "ep_score_kwh_m2", "required": False, "label": "EP score of the collateral (kWh/m²)", "kind": "number", "range": [0, 5000],
     "description": "Specific energy consumption of the immovable-property collateral — Pillar 3 Template 2 columns b-g.", "example": "145"},
    {"name": "ep_score_estimated", "required": False, "label": "EP score estimated", "kind": "boolean",
     "description": "True if the EP score is your estimate rather than from the EPC — Template 2 column p and rows 5 and 10.", "example": "false"},
]
_ATTR_COLS = {"residual_maturity_years", "epc_label", "ifrs9_stage", "emission_intensity", "counterparty_evic_eur",
              "counterparty_govt_level", "no_stated_maturity", "counterparty_sector", "immovable_collateral",
              "accumulated_impairment_eur", "pab_excluded", "ccm_sustainable", "emissions_company_reported",
              "instrument_type", "counterparty_subsector", "nfrd_subject", "loan_purpose", "trading_book",
              "taxonomy_objective", "taxonomy_contribution", "specialised_lending", "ep_score_kwh_m2", "ep_score_estimated"}


@router.get("/assets/attributes/template.xlsx", summary="Download the per-loan attributes template (Excel)")
def attributes_template_xlsx():
    buf = build_template_workbook(ATTR_TEMPLATE_FIELDS)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=tellumen_loan_attributes_template.xlsx"})


@router.post("/assets/attributes/validate", summary="Check a per-loan attributes file (CSV or Excel) before saving")
async def validate_attributes(ctx: CurrentUser, file: UploadFile = File(...)):
    from services.ingest.upload_validation import parse_and_validate
    try:
        rep = parse_and_validate(await file.read(), file.filename, ATTR_TEMPLATE_FIELDS)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="The file could not be read. Please upload a valid CSV or Excel file that matches the template.") from e
    if not rep["ok"]:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing_columns": rep["missing_columns"]})
    return {"filename": file.filename, "n_total": rep["n_total"], "n_valid": rep["n_valid"],
            "n_error": rep["n_error"], "errors": rep["errors"][:200]}


@router.post("/assets/attributes/upload", summary="Save per-loan attributes, matched to your book by asset ID (or a unique name)")
async def upload_attributes(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                            currency: Optional[str] = Form(None), book_date: Optional[str] = Form(None)):
    """Matches each row to an existing loan — by your asset ID first, else by a name that identifies exactly one
    loan (names are not unique in real books, so an ambiguous name is refused, never guessed) — and writes the
    provided attributes. EVIC is converted to EUR at the closing rate of the row's book date, in the row's currency
    or the one declared for the upload (never assumed); what was sent and the rate are kept (money_source)."""
    from services.ingest.upload_validation import parse_and_validate
    try:
        rep = parse_and_validate(await file.read(), file.filename, ATTR_TEMPLATE_FIELDS)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="The file could not be read. Please upload a valid CSV or Excel file that matches the template.") from e
    if not rep["ok"]:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing_columns": rep["missing_columns"]})
    if rep["n_valid"] == 0:
        raise HTTPException(status_code=400, detail="None of the rows are ready yet — please fix the flagged rows and try again.")

    org_id = ctx["org"]["org_id"]
    by_ref, by_name = {}, {}
    for nm, ref, eid in session.execute(text(
            "SELECT entity_name, external_ref, entity_id FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) "
            "AND vertical = 'banking' AND source = 'own'"), {"o": org_id}).fetchall():
        if ref:
            by_ref[str(ref).strip()] = eid
        by_name.setdefault((nm or "").strip().lower(), []).append(eid)

    from services.intake.money import (
        MoneyError,
        convert_amount,
        money_source_merge_sql,
        source_record,
    )
    matched, unmatched, updated, ambiguous, refused = 0, [], 0, [], []
    for row in rep["valid_rows"]:
        name = str(row.get("asset_name") or "").strip()
        ref = str(row.get("external_ref") or "").strip()
        cands = [by_ref[ref]] if ref and ref in by_ref else ([] if ref else by_name.get(name.lower(), []))
        if len(cands) > 1:
            ambiguous.append(name)
            continue
        if not cands:
            unmatched.append(ref or name)
            continue
        eid = cands[0]
        matched += 1
        sets, params = [], {"e": eid}
        mat = row.get("residual_maturity_years")
        if mat not in (None, ""):
            sets.append("residual_maturity_years = :mat"); params["mat"] = float(str(mat).replace(",", ""))
        epc = row.get("epc_label")
        if epc not in (None, ""):
            sets.append("epc_label = :epc"); params["epc"] = str(epc).strip().upper()
        stg = row.get("ifrs9_stage")
        if stg not in (None, ""):
            sets.append("ifrs9_stage = :stg"); params["stg"] = str(stg).strip()
        ei = row.get("emission_intensity")
        if ei not in (None, ""):
            sets.append("emission_intensity = :ei"); params["ei"] = float(str(ei).replace(",", ""))
        evic = row.get("counterparty_evic_eur")
        if evic not in (None, ""):
            ccy = (str(row.get("currency") or "").strip() or currency or "").upper()
            bdate = str(row.get("book_date") or "").strip() or book_date
            try:
                c = convert_amount(session, evic, ccy, bdate, label="counterparty EVIC", org_id=org_id)
            except MoneyError as e:
                refused.append({"asset": ref or name, "reason": str(e)})
                continue
            sets.append("counterparty_evic_eur = :evic"); params["evic"] = c["eur"]
            sets.append(f"money_source = {money_source_merge_sql()}")   # other fields' origins are kept
            params["ms"] = json.dumps(source_record(ccy, bdate, {"counterparty_evic_eur": c}, origin="attributes_upload"), default=str)
        gl = row.get("counterparty_govt_level")
        if gl not in (None, ""):
            sets.append("counterparty_govt_level = :gl"); params["gl"] = str(gl).strip().lower()
        nsm = row.get("no_stated_maturity")
        if nsm not in (None, ""):
            sets.append("no_stated_maturity = :nsm")
            params["nsm"] = str(nsm).strip().lower() in ("true", "1", "yes", "y")
        for k in ("counterparty_sector", "immovable_collateral", "instrument_type", "counterparty_subsector", "loan_purpose",
                  "taxonomy_objective", "taxonomy_contribution"):
            v = row.get(k)
            if v not in (None, ""):
                sets.append(f"{k} = :{k}"); params[k] = str(v).strip().lower()
        for k in ("pab_excluded", "ccm_sustainable", "emissions_company_reported", "nfrd_subject", "trading_book",
                  "specialised_lending", "ep_score_estimated"):
            v = row.get(k)
            if v not in (None, ""):
                sets.append(f"{k} = :{k}"); params[k] = str(v).strip().lower() in ("true", "1", "yes", "y")
        ep = row.get("ep_score_kwh_m2")
        if ep not in (None, ""):
            sets.append("ep_score_kwh_m2 = :ep"); params["ep"] = float(str(ep).replace(",", ""))
        imp = row.get("accumulated_impairment_eur")
        if imp not in (None, ""):
            ccy = (str(row.get("currency") or "").strip() or currency or "").upper()
            bdate = str(row.get("book_date") or "").strip() or book_date
            try:
                c = convert_amount(session, imp, ccy, bdate, label="accumulated impairment", org_id=org_id)
            except MoneyError as e:
                refused.append({"asset": ref or name, "reason": str(e)})
                continue
            sets.append("accumulated_impairment_eur = :imp"); params["imp"] = c["eur"]
            rec = source_record(ccy, bdate, {"accumulated_impairment_eur": c}, origin="attributes_upload")
            if "ms" in params:                                   # EVIC on the same row: one merged record
                merged = json.loads(params["ms"]); merged["fields"].update(rec["fields"]); params["ms"] = json.dumps(merged, default=str)
            else:
                sets.append(f"money_source = {money_source_merge_sql()}"); params["ms"] = json.dumps(rec, default=str)
        if sets:
            session.execute(text(f"UPDATE ext_banking SET {', '.join(sets)} WHERE entity_id = :e"), params)
            updated += 1
    session.commit()
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="assets.attributes.upload",
                target_type="ext_banking", target_id=None,
                detail={"matched": matched, "updated": updated, "unmatched": len(unmatched), "ambiguous": len(ambiguous),
                        "refused": len(refused), "filename": file.filename})
    return {"n_matched": matched, "n_updated": updated, "n_unmatched": len(unmatched), "unmatched": unmatched[:50],
            "n_ambiguous": len(ambiguous), "ambiguous": ambiguous[:50], "n_refused": len(refused), "refused": refused[:50],
            "n_invalid": rep["n_error"], "errors": rep["errors"][:200]}


@router.get("/disclosure.xlsx", summary="TCFD / EU-Taxonomy disclosure pack (Excel)")
def disclosure_xlsx(session: DbSession, org_id: OrgId,
                     scenario: str = Query("baseline"), horizon: str = Query("current")):
    from services.money.params import for_org
    assets = _assets_with_risk(session, org_id, scenario, horizon, method=for_org(session, org_id))
    headers = ["asset_name", "sector", "country", "value_eur", "headline_score", "risk_bucket",
               "taxonomy_status", "h3_cell", "recommended_discount_pct", "effective_discount_pct",
               "discounted_value_eur", "overridden", "outstanding_loan_balance_eur",
               "original_ltv_pct", "climate_adjusted_ltv_pct"]
    rows = [[a["asset_name"], a["sector"], a["country"], a["value_eur"], a["headline_score"],
             a["headline_bucket"] or "unscored", a["taxonomy_status"], a["h3_cell"],
             a["valuation"]["recommended_discount_pct"], a["valuation"]["effective_discount_pct"],
             a["valuation"]["discounted_value_eur"], "yes" if a["valuation"]["is_overridden"] else "no",
             a["valuation"]["outstanding_loan_balance_eur"], a["valuation"]["original_ltv_pct"],
             a["valuation"]["climate_adjusted_ltv_pct"]] for a in assets]
    buf = build_export_workbook(headers, rows, sheet_name="Physical risk disclosure")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=meridian-physical-risk-disclosure.xlsx"})

"""
Insurance underwriting — public read-only endpoints for the Loss-curve pricing
workspace.

Projects the golden source (canonical_scores) onto an insurer's property book
by H3 cell (v_insurance_policy_physical_risk), then runs each policy through
ml/scoring/insurance_pricing.py's score -> scenario loss -> expected annual
loss -> premium chain. Mirrors bank.py/supply.py exactly: tenant-scoped via
JWT org_id, DEMO_ORG fallback, provenance kept. Policies whose cell is
unscored return status='no_canonical_score', premium withheld -- same
governance rule as every other hazard-projected book here.
"""
from __future__ import annotations

import io
import uuid
from collections import defaultdict
from typing import Annotated, Optional

import h3
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from api.deps import CurrentUser, DbSession
from api.services.rbac import write_audit
from ml.scoring.insurance_pricing import price_policy
from services.scoring.on_demand import process_new_cells
from services.templates.workbook import build_export_workbook, build_template_workbook

router = APIRouter(prefix="/v1/insurance", tags=["Insurance"])

DEMO_ORG = "22222222-2222-4222-8222-222222222222"  # Iberia Mutual (demo)
_bearer = HTTPBearer(auto_error=False)


def resolve_org(
    org_id: Optional[str] = Query(None),
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
) -> str:
    """User JWT's org wins (tenant isolation); else query param; else the demo insurer."""
    token = credentials.credentials if credentials else None
    if token and not token.startswith("cp_live_"):
        from api.security import decode_access_token
        payload = decode_access_token(token)
        if payload and payload.get("org_id"):
            return payload["org_id"]
    return org_id or DEMO_ORG


OrgId = Annotated[str, Depends(resolve_org)]


def _policies_with_risk(session, org_id, scenario, horizon):
    """All of an org's policies (metadata) + their per-hazard projected risk."""
    policies = session.execute(text("""
        SELECT policy_id::text AS policy_id, policy_name, policy_type, country, region,
               CAST(latitude AS FLOAT) AS lat, CAST(longitude AS FLOAT) AS lon, h3_cell,
               CAST(sum_insured_eur AS FLOAT) AS sum_insured_eur,
               CAST(deductible_pct AS FLOAT) AS deductible_pct,
               CAST(building_value_eur AS FLOAT) AS building_value_eur,
               CAST(contents_value_eur AS FLOAT) AS contents_value_eur,
               CAST(business_interruption_value_eur AS FLOAT) AS business_interruption_value_eur,
               construction_type, year_built, number_of_stories
        FROM insurance_policies WHERE org_id = :o ORDER BY sum_insured_eur DESC
    """), {"o": org_id}).mappings().all()

    risks = session.execute(text("""
        SELECT policy_id::text AS policy_id, hazard_type,
               physical_risk_score AS score, risk_bucket, model_version, scored_at
        FROM v_insurance_policy_physical_risk
        WHERE org_id = :o AND scenario = :s AND time_horizon = :h
    """), {"o": org_id, "s": scenario, "h": horizon}).mappings().all()

    by_policy = defaultdict(list)
    for r in risks:
        by_policy[r["policy_id"]].append({
            "hazard": r["hazard_type"], "score": round(r["score"], 1),
            "bucket": r["risk_bucket"], "model_version": r["model_version"],
            "scored_at": r["scored_at"],
        })

    out = []
    for p in policies:
        hz = sorted(by_policy.get(p["policy_id"], []), key=lambda x: -x["score"])
        headline = hz[0] if hz else None
        pricing = price_policy(headline["score"], p["sum_insured_eur"]) if headline else None
        out.append({
            **{k: p[k] for k in p.keys()},
            "hazards": hz,
            "headline_score": headline["score"] if headline else None,
            "headline_bucket": headline["bucket"] if headline else None,
            "headline_hazard": headline["hazard"] if headline else None,
            "pricing": pricing,
        })
    return out


def _rollup(policies):
    total = sum(p["sum_insured_eur"] or 0 for p in policies)
    priced = [p for p in policies if p["pricing"]]
    total_eal = sum(p["pricing"]["expected_annual_loss_eur"] for p in priced)
    total_premium = sum(p["pricing"]["gross_premium_eur"] for p in priced)
    by_bucket = defaultdict(lambda: {"count": 0, "sum_insured_eur": 0.0, "eal_eur": 0.0})
    for p in policies:
        b = p["headline_bucket"] or "none"
        by_bucket[b]["count"] += 1
        by_bucket[b]["sum_insured_eur"] += p["sum_insured_eur"] or 0
        if p["pricing"]:
            by_bucket[b]["eal_eur"] += p["pricing"]["expected_annual_loss_eur"]
    return {
        "n_policies": len(policies),
        "n_priced": len(priced),
        "total_sum_insured_eur": round(total),
        "total_expected_annual_loss_eur": round(total_eal),
        "total_gross_premium_eur": round(total_premium),
        "portfolio_loss_ratio_pct": round(100 * total_eal / total_premium, 1) if total_premium else 0,
        "by_bucket": {k: {"count": v["count"], "sum_insured_eur": round(v["sum_insured_eur"]),
                           "eal_eur": round(v["eal_eur"])} for k, v in by_bucket.items()},
        "top_policies": sorted(
            [p for p in policies if p["headline_score"] is not None],
            key=lambda p: -p["headline_score"])[:8],
    }


@router.get("/portfolio", summary="Property book projected onto the golden source")
def portfolio(session: DbSession, org_id: OrgId,
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    policies = _policies_with_risk(session, org_id, scenario, horizon)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": _rollup(policies), "policies": policies}


@router.get("/summary", summary="Loss-curve pricing rollup")
def summary(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id = :o"
    ), {"o": org_id}).mappings().first()
    policies = _policies_with_risk(session, org_id, scenario, horizon)
    return {"org_id": org_id, "org": dict(org) if org else None, "rollup": _rollup(policies)}


# A real Statement of Values (SOV, the ACORD 140-style format insurers/reinsurers
# already exchange property schedules in) -- see services/templates/workbook.py's
# template. TIV (Total Insured Value) is properly building + contents + business
# interruption; a bare sum_insured_eur is still accepted as a fallback for a
# counterparty that only has one lump figure.
POLICY_TEMPLATE_FIELDS = [
    {"name": "policy_name", "required": True, "description": "Free-text location/policy name.", "example": "Valencia Warehouse 12"},
    {"name": "latitude", "required": True, "description": "Decimal degrees.", "example": "39.4699"},
    {"name": "longitude", "required": True, "description": "Decimal degrees.", "example": "-0.3763"},
    {"name": "building_value_eur", "required": False, "description": "TIV component. Provide this + contents + BI, OR sum_insured_eur directly.", "example": "3000000"},
    {"name": "contents_value_eur", "required": False, "description": "TIV component (business personal property).", "example": "500000"},
    {"name": "business_interruption_value_eur", "required": False, "description": "TIV component (business income).", "example": "200000"},
    {"name": "sum_insured_eur", "required": False, "description": "Total Insured Value, if not broken into components above.", "example": "3700000"},
    {"name": "construction_type", "required": False, "description": "ISO Construction Class: frame / joisted_masonry / non_combustible / masonry_non_combustible / fire_resistive.", "example": "masonry_non_combustible"},
    {"name": "year_built", "required": False, "description": "Year of construction.", "example": "1998"},
    {"name": "number_of_stories", "required": False, "description": "Number of stories.", "example": "3"},
    {"name": "deductible_pct", "required": False, "description": "Policy deductible, as a fraction (0.02 = 2%).", "example": "0.02"},
    {"name": "region", "required": False, "description": "Free-text region.", "example": "Valencia"},
    {"name": "country", "required": False, "description": "ISO-2 country code.", "example": "ES"},
]
REQUIRED_POLICY_COLUMNS = [f["name"] for f in POLICY_TEMPLATE_FIELDS if f["required"]]
CONSTRUCTION_TYPES = {"frame", "joisted_masonry", "non_combustible", "masonry_non_combustible", "fire_resistive"}


@router.get("/policies/template.xlsx", summary="Download the Statement of Values upload template (Excel)")
def policies_template_xlsx():
    buf = build_template_workbook(POLICY_TEMPLATE_FIELDS)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=tellumen_sov_template.xlsx"})


@router.post("/policies/upload", summary="Bulk-upload policies from a CSV into your property book")
async def upload_policies(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...)):
    """Same shape as bank.py's assets/upload and supply.py's plots/upload: lands
    in the uploader's OWN org, resolves an H3 cell per row, then processes new
    cells against the golden source via the shared
    services.scoring.on_demand.process_new_cells."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    missing = [c for c in REQUIRED_POLICY_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing": missing})
    tiv_components = {"building_value_eur", "contents_value_eur", "business_interruption_value_eur"}
    if "sum_insured_eur" not in df.columns and not (tiv_components & set(df.columns)):
        raise HTTPException(status_code=400, detail={
            "error": "missing_valuation",
            "message": "Provide either sum_insured_eur, or at least one of building_value_eur/contents_value_eur/business_interruption_value_eur",
        })

    org_id = ctx["org"]["org_id"]
    records, cell_coords = [], {}
    for _, row in df.iterrows():
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (TypeError, ValueError):
            continue
        building = float(row["building_value_eur"]) if "building_value_eur" in df.columns and pd.notna(row.get("building_value_eur")) else None
        contents = float(row["contents_value_eur"]) if "contents_value_eur" in df.columns and pd.notna(row.get("contents_value_eur")) else None
        bi = float(row["business_interruption_value_eur"]) if "business_interruption_value_eur" in df.columns and pd.notna(row.get("business_interruption_value_eur")) else None
        if building is not None or contents is not None or bi is not None:
            sum_insured = (building or 0) + (contents or 0) + (bi or 0)
        elif "sum_insured_eur" in df.columns and pd.notna(row.get("sum_insured_eur")):
            sum_insured = float(row["sum_insured_eur"])
        else:
            continue  # no valuation data for this row -- skip, don't fabricate a TIV
        construction = str(row["construction_type"]).strip().lower() if "construction_type" in df.columns and pd.notna(row.get("construction_type")) else None
        if construction and construction not in CONSTRUCTION_TYPES:
            construction = None  # unrecognized value -- omit rather than violate the DB CHECK constraint
        cell = h3.latlng_to_cell(lat, lon, 8)
        cell_coords[cell] = (lat, lon)
        records.append({
            "policy_id": str(uuid.uuid4()), "org_id": org_id,
            "policy_name": str(row["policy_name"]),
            "policy_type": str(row["policy_type"]) if "policy_type" in df.columns and pd.notna(row.get("policy_type")) else "property",
            "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": str(row["region"]) if "region" in df.columns and pd.notna(row.get("region")) else None,
            "country": str(row["country"]) if "country" in df.columns and pd.notna(row.get("country")) else None,
            "sum_insured_eur": sum_insured,
            "building_value_eur": building, "contents_value_eur": contents, "business_interruption_value_eur": bi,
            "construction_type": construction,
            "year_built": int(row["year_built"]) if "year_built" in df.columns and pd.notna(row.get("year_built")) else None,
            "number_of_stories": int(row["number_of_stories"]) if "number_of_stories" in df.columns and pd.notna(row.get("number_of_stories")) else None,
            "deductible_pct": float(row["deductible_pct"]) if "deductible_pct" in df.columns and pd.notna(row.get("deductible_pct")) else 0.02,
        })
    if not records:
        raise HTTPException(status_code=400, detail="No valid rows found in the uploaded CSV")

    session.execute(text("""
        INSERT INTO insurance_policies (policy_id, org_id, policy_name, policy_type, latitude, longitude,
                                         h3_cell, region, country, sum_insured_eur, building_value_eur,
                                         contents_value_eur, business_interruption_value_eur,
                                         construction_type, year_built, number_of_stories, deductible_pct)
        VALUES (:policy_id, :org_id, :policy_name, :policy_type, :latitude, :longitude,
                :h3_cell, :region, :country, :sum_insured_eur, :building_value_eur,
                :contents_value_eur, :business_interruption_value_eur,
                :construction_type, :year_built, :number_of_stories, :deductible_pct)
    """), records)
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="policies.upload",
                target_type="insurance_policies", target_id=None,
                detail={"n_rows": len(records), "filename": file.filename})

    processing = process_new_cells(cell_coords)
    return {"n_uploaded": len(records), **processing}


@router.get("/portfolio.xlsx", summary="Loss-curve pricing book (Excel)")
def portfolio_xlsx(session: DbSession, org_id: OrgId,
                    scenario: str = Query("baseline"), horizon: str = Query("current")):
    policies = _policies_with_risk(session, org_id, scenario, horizon)
    headers = ["policy_name", "region", "country", "sum_insured_eur", "construction_type", "year_built",
               "headline_hazard", "headline_score", "risk_bucket", "mdr", "scenario_loss_eur",
               "expected_annual_loss_eur", "gross_premium_eur", "rate_on_line_pct"]
    rows = [[p["policy_name"], p["region"], p["country"], p["sum_insured_eur"], p.get("construction_type"),
             p.get("year_built"), p["headline_hazard"], p["headline_score"], p["headline_bucket"] or "unscored",
             p["pricing"]["mdr"] if p["pricing"] else None, p["pricing"]["scenario_loss_eur"] if p["pricing"] else None,
             p["pricing"]["expected_annual_loss_eur"] if p["pricing"] else None,
             p["pricing"]["gross_premium_eur"] if p["pricing"] else None,
             p["pricing"]["rate_on_line_pct"] if p["pricing"] else None] for p in policies]
    buf = build_export_workbook(headers, rows, sheet_name="Loss-curve pricing")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=iberia-loss-curve-pricing.xlsx"})

"""
Banking flagship — public read-only endpoints for the loan-book workspace.

Projects the golden source (canonical_scores) onto a bank's assets by H3 cell,
the same projection as services/intelligence/asset_risk_projection and the
v_bank_asset_physical_risk view. Every figure carries its model_version + vintage
so the disclosure is defensible. No auth (aggregate read), mirroring platform.py.
"""
from __future__ import annotations

import io
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from typing import Annotated, Optional

import h3
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import CurrentUser, DbSession
from api.services.rbac import write_audit
from ml.scoring.valuation_discount import valuation_block
from services.scoring.on_demand import process_new_cells

router = APIRouter(prefix="/v1/bank", tags=["Banking"])

DEMO_ORG = "11111111-1111-4111-8111-111111111111"
BUCKET_RANK = {"VH": 4, "H": 3, "M": 2, "L": 1}

_bearer = HTTPBearer(auto_error=False)


def resolve_org(
    org_id: Optional[str] = Query(None),
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
) -> str:
    """
    Tenant scoping: a user JWT's org wins (real isolation); otherwise fall back to
    the org_id query param, and finally to DEMO_ORG so the public marketing/demo
    path keeps working without a token.
    """
    token = credentials.credentials if credentials else None
    if token and not token.startswith("cp_live_"):
        from api.security import decode_access_token
        payload = decode_access_token(token)
        if payload and payload.get("org_id"):
            return payload["org_id"]
    return org_id or DEMO_ORG


OrgId = Annotated[str, Depends(resolve_org)]


def _assets_with_risk(session, org_id, scenario, horizon):
    """All of an org's assets (metadata) + their per-hazard projected risk."""
    assets = session.execute(text("""
        SELECT asset_id::text AS asset_id, asset_name, asset_type, sector, country, region,
               CAST(latitude AS FLOAT) AS lat, CAST(longitude AS FLOAT) AS lon, h3_cell,
               CAST(asset_value_eur AS FLOAT) AS value_eur,
               CAST(annual_revenue_eur AS FLOAT) AS revenue_eur, taxonomy_status,
               construction_year, nace_code,
               CAST(ghg_emissions_scope1_tco2e AS FLOAT) AS ghg1,
               CAST(ghg_emissions_scope2_tco2e AS FLOAT) AS ghg2,
               CAST(ghg_emissions_scope3_tco2e AS FLOAT) AS ghg3
        FROM bank_assets WHERE org_id = :o ORDER BY asset_value_eur DESC
    """), {"o": org_id}).mappings().all()

    risks = session.execute(text("""
        SELECT asset_id::text AS asset_id, hazard_type,
               CAST(physical_risk_score AS FLOAT) AS score, risk_bucket,
               model_version, scored_at
        FROM v_bank_asset_physical_risk
        WHERE org_id = :o AND scenario = :s AND time_horizon = :h
    """), {"o": org_id, "s": scenario, "h": horizon}).mappings().all()

    by_asset = defaultdict(list)
    for r in risks:
        by_asset[r["asset_id"]].append({
            "hazard": r["hazard_type"], "score": round(r["score"], 1),
            "bucket": r["risk_bucket"], "model_version": r["model_version"],
            "scored_at": r["scored_at"],
        })

    valuations = session.execute(text("""
        SELECT asset_id::text AS asset_id, CAST(override_discount_pct AS FLOAT) AS override_discount_pct,
               overridden_by::text AS overridden_by, overridden_at, reason
        FROM bank_asset_valuations WHERE asset_id IN (
            SELECT asset_id FROM bank_assets WHERE org_id = :o
        )
    """), {"o": org_id}).mappings().all()
    val_by_asset = {v["asset_id"]: dict(v) for v in valuations}

    out = []
    for a in assets:
        hz = sorted(by_asset.get(a["asset_id"], []), key=lambda x: -x["score"])
        headline = hz[0] if hz else None
        out.append({
            **{k: a[k] for k in a.keys()},
            "hazards": hz,
            "headline_score": headline["score"] if headline else None,
            "headline_bucket": headline["bucket"] if headline else None,
            "headline_hazard": headline["hazard"] if headline else None,
            "valuation": valuation_block(
                headline["bucket"] if headline else None, a["value_eur"], val_by_asset.get(a["asset_id"])),
        })
    return out


def _rollup(assets):
    total = sum(a["value_eur"] or 0 for a in assets)
    at_risk = [a for a in assets if a["headline_bucket"] in ("H", "VH")]
    var = sum(a["value_eur"] or 0 for a in at_risk)
    total_discounted = sum(a["valuation"]["discounted_value_eur"] for a in assets)
    by_bucket = defaultdict(lambda: {"count": 0, "value": 0.0})
    for a in assets:
        b = a["headline_bucket"] or "none"
        by_bucket[b]["count"] += 1
        by_bucket[b]["value"] += a["value_eur"] or 0
    return {
        "n_assets": len(assets),
        "n_scored": sum(1 for a in assets if a["headline_bucket"]),
        "total_value_eur": round(total),
        "value_at_risk_eur": round(var),
        "pct_value_at_risk": round(100 * var / total, 1) if total else 0,
        "n_high": len(at_risk),
        "total_discounted_value_eur": round(total_discounted),
        "n_overridden": sum(1 for a in assets if a["valuation"]["is_overridden"]),
        "by_bucket": {k: {"count": v["count"], "value_eur": round(v["value"])} for k, v in by_bucket.items()},
        "top_assets": sorted(
            [a for a in assets if a["headline_score"] is not None],
            key=lambda a: -a["headline_score"])[:8],
    }


@router.get("/portfolio", summary="Loan book projected onto the golden source")
def portfolio(session: DbSession, org_id: OrgId,
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    assets = _assets_with_risk(session, org_id, scenario, horizon)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": _rollup(assets), "assets": assets}


@router.get("/summary", summary="Command-center rollup")
def summary(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id = :o"
    ), {"o": org_id}).mappings().first()
    assets = _assets_with_risk(session, org_id, scenario, horizon)
    return {"org_id": org_id, "org": dict(org) if org else None, "rollup": _rollup(assets)}


@router.get("/disclosure", summary="TCFD / EU-Taxonomy disclosure pack from the projected book")
def disclosure(session: DbSession, org_id: OrgId,
               scenario: str = Query("baseline"), horizon: str = Query("current")):
    assets = _assets_with_risk(session, org_id, scenario, horizon)
    # physical risk by hazard — value of the book exposed at High+ per hazard
    hazards: dict = {}
    for a in assets:
        for hz in a["hazards"]:
            h = hazards.setdefault(hz["hazard"], {
                "exposed_value_eur": 0.0, "n_exposed": 0, "max_score": 0.0,
                "model_version": hz["model_version"], "scored_at": hz["scored_at"]})
            if hz["bucket"] in ("H", "VH"):
                h["exposed_value_eur"] += a["value_eur"] or 0
                h["n_exposed"] += 1
            h["max_score"] = max(h["max_score"], hz["score"])
    for h in hazards.values():
        h["exposed_value_eur"] = round(h["exposed_value_eur"])
        h["max_score"] = round(h["max_score"], 1)
    # EU-Taxonomy alignment, value-weighted
    tax = defaultdict(lambda: {"count": 0, "value_eur": 0.0})
    for a in assets:
        t = a.get("taxonomy_status") or "unknown"
        tax[t]["count"] += 1
        tax[t]["value_eur"] += a["value_eur"] or 0
    # financed emissions (GHG totals across the book)
    ghg = {f"scope{i}": round(sum((a.get(f"ghg{i}") or 0) for a in assets))
           for i in (1, 2, 3)}
    return {
        "org_id": org_id, "scenario": scenario, "horizon": horizon,
        "rollup": _rollup(assets),
        "by_hazard": hazards,
        "taxonomy": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in tax.items()},
        "financed_emissions_tco2e": ghg,
    }


def _valuation_row(session, asset_id):
    return session.execute(text("""
        SELECT CAST(override_discount_pct AS FLOAT) AS override_discount_pct,
               overridden_by::text AS overridden_by, overridden_at, reason
        FROM bank_asset_valuations WHERE asset_id = :a
    """), {"a": asset_id}).mappings().first()


@router.get("/asset/{asset_id}", summary="One asset — full projection + provenance")
def asset_detail(asset_id: str, session: DbSession):
    a = session.execute(text("""
        SELECT asset_id::text AS asset_id, org_id::text AS org_id, asset_name, asset_type,
               sector, country, region, CAST(latitude AS FLOAT) AS lat,
               CAST(longitude AS FLOAT) AS lon, h3_cell,
               CAST(asset_value_eur AS FLOAT) AS value_eur,
               CAST(annual_revenue_eur AS FLOAT) AS revenue_eur, taxonomy_status,
               taxonomy_activity, construction_year, expected_lifespan_years, nace_code, gics_code,
               CAST(ghg_emissions_scope1_tco2e AS FLOAT) AS ghg_scope1,
               CAST(ghg_emissions_scope2_tco2e AS FLOAT) AS ghg_scope2,
               CAST(ghg_emissions_scope3_tco2e AS FLOAT) AS ghg_scope3
        FROM bank_assets WHERE asset_id = :a
    """), {"a": asset_id}).mappings().first()
    if not a:
        return {"error": "asset not found"}
    risks = session.execute(text("""
        SELECT hazard_type, scenario, time_horizon,
               CAST(physical_risk_score AS FLOAT) AS score, risk_bucket,
               model_version, scored_at, risk_source
        FROM v_bank_asset_physical_risk WHERE asset_id = :a
        ORDER BY hazard_type, scenario, time_horizon
    """), {"a": asset_id}).mappings().all()
    headline = sorted(risks, key=lambda r: -r["score"])[0] if risks else None
    val_row = _valuation_row(session, asset_id)
    audit = session.execute(text("""
        SELECT actor_user_id::text AS actor_user_id, action, detail, created_at
        FROM access_audit_log WHERE target_type = 'bank_asset' AND target_id = :a
        ORDER BY created_at DESC LIMIT 5
    """), {"a": asset_id}).mappings().all()
    return {
        "asset": dict(a), "risks": [dict(r) for r in risks],
        "valuation": valuation_block(headline["risk_bucket"] if headline else None, a["value_eur"], val_row),
        "valuation_audit": [dict(x) for x in audit],
    }


class ValuationOverrideRequest(BaseModel):
    discount_pct: float = Field(..., ge=0, le=100)
    reason: Optional[str] = None


@router.post("/asset/{asset_id}/valuation-override", summary="Override the recommended valuation discount (audited)")
def override_valuation(asset_id: str, body: ValuationOverrideRequest, session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    asset = session.execute(text("SELECT org_id::text AS org_id FROM bank_assets WHERE asset_id = :a"), {"a": asset_id}).mappings().first()
    if not asset:
        raise HTTPException(status_code=404, detail="asset not found")
    if asset["org_id"] != ctx["org"]["org_id"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Asset does not belong to your organization"})

    prior = _valuation_row(session, asset_id)
    from_pct = prior["override_discount_pct"] if prior else None
    now = datetime.now(timezone.utc)
    session.execute(text("""
        INSERT INTO bank_asset_valuations (asset_id, override_discount_pct, overridden_by, overridden_at, reason)
        VALUES (:a, :pct, :u, :now, :reason)
        ON CONFLICT (asset_id) DO UPDATE
            SET override_discount_pct = EXCLUDED.override_discount_pct,
                overridden_by = EXCLUDED.overridden_by,
                overridden_at = EXCLUDED.overridden_at,
                reason = EXCLUDED.reason
    """), {"a": asset_id, "pct": body.discount_pct, "u": ctx["user"]["id"], "now": now, "reason": body.reason})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="asset.valuation.override", target_type="bank_asset", target_id=asset_id,
                detail={"from_pct": from_pct, "to_pct": body.discount_pct, "reason": body.reason})
    return {"asset_id": asset_id, "override_discount_pct": body.discount_pct, "overridden_at": now.isoformat()}


@router.delete("/asset/{asset_id}/valuation-override", summary="Clear an override, revert to the recommended discount (audited)")
def clear_valuation_override(asset_id: str, session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    prior = _valuation_row(session, asset_id)
    if not prior:
        return {"asset_id": asset_id, "cleared": False}
    session.execute(text("DELETE FROM bank_asset_valuations WHERE asset_id = :a"), {"a": asset_id})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="asset.valuation.override_cleared", target_type="bank_asset", target_id=asset_id,
                detail={"from_pct": prior["override_discount_pct"], "to_pct": None})
    return {"asset_id": asset_id, "cleared": True}


REQUIRED_ASSET_COLUMNS = ["asset_name", "asset_type", "latitude", "longitude", "asset_value_eur", "sector"]


@router.post("/assets/upload", summary="Bulk-upload assets from a CSV into your loan book")
async def upload_assets(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...)):
    """Real self-service data entry: a CSV of assets lands in the uploader's OWN
    org (never DEMO_ORG — this always requires a real login), gets an H3 cell per
    row, and is immediately processed against the golden source (see
    services.scoring.on_demand.process_new_cells) exactly the way an any-address
    lookup query would be -- no separate ingestion pipeline to keep in sync."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    missing = [c for c in REQUIRED_ASSET_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing": missing})

    org_id = ctx["org"]["org_id"]
    records, cell_coords = [], {}
    for _, row in df.iterrows():
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            value_eur = float(row["asset_value_eur"])
        except (TypeError, ValueError):
            continue  # a row with an unparsable required field is skipped, not fatal to the whole upload
        cell = h3.latlng_to_cell(lat, lon, 8)
        cell_coords[cell] = (lat, lon)
        records.append({
            "asset_id": str(uuid.uuid4()), "org_id": org_id,
            "asset_name": str(row["asset_name"]), "asset_type": str(row["asset_type"]),
            "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": str(row["region"]) if "region" in df.columns and pd.notna(row.get("region")) else None,
            "country": str(row["country"]) if "country" in df.columns and pd.notna(row.get("country")) else None,
            "asset_value_eur": value_eur, "sector": str(row["sector"]),
        })
    if not records:
        raise HTTPException(status_code=400, detail="No valid rows found in the uploaded CSV")

    session.execute(text("""
        INSERT INTO bank_assets (asset_id, org_id, asset_name, asset_type, latitude, longitude,
                                  h3_cell, region, country, asset_value_eur, sector)
        VALUES (:asset_id, :org_id, :asset_name, :asset_type, :latitude, :longitude,
                :h3_cell, :region, :country, :asset_value_eur, :sector)
    """), records)
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="assets.upload",
                target_type="bank_assets", target_id=None,
                detail={"n_rows": len(records), "filename": file.filename})

    processing = process_new_cells(cell_coords)
    return {"n_uploaded": len(records), **processing}

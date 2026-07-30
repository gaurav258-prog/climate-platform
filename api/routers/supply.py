"""
Agriculture / supply-chain — public read-only endpoints for the COGS-at-risk workspace.

Projects the golden source (canonical_scores) onto a buyer's sourcing plots by H3 cell
(v_sc_plot_physical_risk), then runs the impact-function layer
(services/intelligence/supply_cogs) to roll a per-location hazard up the bill of materials
into a euro "COGS-at-risk". Mirrors bank.py: tenant-scoped, DEMO_ORG fallback, provenance kept.
Governance: unscored commodities (e.g. cocoa) return status='pending', € withheld.
"""
from __future__ import annotations

import io
import uuid
from dataclasses import asdict
from typing import Annotated, Optional

import h3
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import CurrentUser, DbSession, require_permission
from api.services.rbac import write_audit
from services.intelligence.supply_cogs import (
    apply_commodity_override, clear_commodity_override, project_org_supply, IMPACT_VERSION,
)
from services.scoring.on_demand import schedule_scoring
from services.intelligence.geometry import validate_plot_geometry
from services.intelligence.eudr import determine_plot
from services.intelligence.eudr_dds import assemble_dds
from services.intelligence.company_sites import add_site, list_sites_with_risk, site_hazards, SiteLocationError, SITE_TYPES
from services.templates.workbook import build_export_workbook, build_template_workbook
from services.intelligence.csrd_e1 import build_e1_report

router = APIRouter(prefix="/v1/supply", tags=["Agriculture / Supply chain"])

DEMO_ORG = "33333333-3333-4333-8333-333333333333"   # Terra Foods (demo)
_bearer = HTTPBearer(auto_error=False)


def resolve_org(
    org_id: Optional[str] = Query(None),
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
) -> str:
    """User JWT's org wins (tenant isolation); else query param; else the demo CPG."""
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


def _eudr_summary(session, org_id):
    rows = session.execute(text("""
        SELECT eudr_status, count(*) n FROM sc_sourcing_plots WHERE org_id=:o GROUP BY eudr_status
    """), {"o": org_id}).mappings().all()
    d = {r["eudr_status"]: r["n"] for r in rows}
    covered = session.execute(text("""
        SELECT DISTINCT co.name FROM sc_sourcing_plots p
        JOIN sc_commodities co ON co.commodity_id=p.commodity_id
        WHERE p.org_id=:o AND co.eudr_covered=true
    """), {"o": org_id}).scalars().all()
    return {"by_status": d, "covered_commodities": list(covered)}


@router.get("/summary", summary="Procurement book → COGS-at-risk rollup")
def summary(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id=:o"
    ), {"o": org_id}).mappings().first()
    r = project_org_supply(session, org_id, scenario=scenario, time_horizon=horizon)
    return {
        "org_id": org_id, "org": dict(org) if org else None,
        "scenario": scenario, "horizon": horizon, "impact_version": IMPACT_VERSION,
        "rollup": {
            "ingredient_spend_eur": r.ingredient_spend_eur, "total_cogs_eur": r.total_cogs_eur,
            "cogs_at_risk_p50_eur": r.cogs_at_risk_p50,
            # The physical half — yield_shock x spend, no price forecast in it. This is the
            # headline; a P90 used to sit here that was just p50 x 1.8 (a decoration).
            "volume_at_risk_eur": r.volume_at_risk_eur,
            "pct_cogs_at_risk": r.pct_cogs_at_risk, "n_commodities": r.n_commodities,
            "n_pending": r.n_pending,
            # Publish gate: commodities scored but not event-backtested. Their exposure is
            # reported as SPEND; their € is withheld and never in the headline above.
            "n_held": r.n_held, "held_spend_eur": r.held_spend_eur,
            "covered_spend_eur": r.covered_spend_eur,
        },
        "commodities": [asdict(c) for c in r.commodities],
        # name → commodity_id, so the UI can deep-link each commodity to its analytics detail
        "commodity_ids": {row["name"]: row["commodity_id"] for row in session.execute(text("""
            SELECT DISTINCT co.commodity_id::text AS commodity_id, co.name
            FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
            WHERE p.org_id = :o
        """), {"o": org_id}).mappings().all()},
        "eudr": _eudr_summary(session, org_id),
    }


@router.get("/portfolio", summary="Commodities + SKUs + plots")
def portfolio(session: DbSession, org_id: OrgId,
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    r = project_org_supply(session, org_id, scenario=scenario, time_horizon=horizon)
    products = session.execute(text("""
        SELECT product_id::text AS product_id, name, category, annual_units,
               CAST(annual_revenue_eur AS FLOAT) AS revenue_eur,
               CAST(annual_cogs_eur AS FLOAT) AS cogs_eur
        FROM sc_products WHERE org_id=:o ORDER BY annual_cogs_eur DESC
    """), {"o": org_id}).mappings().all()
    bom = session.execute(text("""
        SELECT pr.product_id::text AS product_id, co.name AS commodity,
               CAST(b.cost_share_pct AS FLOAT) AS cost_share_pct,
               CAST(b.annual_spend_eur AS FLOAT) AS spend_eur
        FROM sc_bom_lines b JOIN sc_products pr ON pr.product_id=b.product_id
        JOIN sc_commodities co ON co.commodity_id=b.commodity_id
        WHERE pr.org_id=:o
    """), {"o": org_id}).mappings().all()
    # plots enriched with the worst projected hazard + bucket (for the map / sourcing book)
    from core.types import score_to_bucket
    plots = []
    for p in _plots_with_hazard(session, org_id, scenario, horizon):
        hs = p["hazard_score"]
        plots.append({**dict(p), "bucket": score_to_bucket(hs).value if hs is not None else None,
                      "hazard_score": round(hs, 1) if hs is not None else None})
    return {
        "org_id": org_id, "scenario": scenario, "horizon": horizon,
        "impact_version": IMPACT_VERSION,
        "commodities": [asdict(c) for c in r.commodities],
        "products": [dict(p) for p in products],
        "bom": [dict(b) for b in bom],
        "plots": plots,
    }


@router.get("/hex-hazard", summary="H3 hexagons around the sourcing plots, each with its own per-cell hazard lookup")
def hex_hazard(session: DbSession, org_id: OrgId, res: int = Query(4, ge=2, le=9)):
    """The Earth as the platform actually indexes it — H3 cells around the procurement book, each
    carrying a REAL hazard lookup from the golden source (canonical_scores), not the plot's own
    score copied onto its cell. A cell with no reading yet returns status='no_data' (the on-demand
    grid extends there but hasn't been scored). That honesty is the point of the hex view.

    `res` is the H3 resolution to draw at (the UI raises it as you zoom in). Cells are the plots'
    own cells at that resolution plus their 1-ring of neighbours, so the grid reads as a patch
    around the book rather than a full-planet tiling."""
    from api.routers.lookup import _compute_overall  # local import: dodge a circular import at module load

    plots = session.execute(text("""
        SELECT p.h3_cell, CAST(p.latitude AS FLOAT) lat, CAST(p.longitude AS FLOAT) lon,
               p.plot_name, p.country, co.name AS commodity
        FROM sc_sourcing_plots p
        JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = :o AND p.latitude IS NOT NULL AND p.longitude IS NOT NULL
    """), {"o": org_id}).mappings().all()
    if not plots:
        return {"resolution": res, "hexes": []}

    # Each plot's data cell is the res-8 unit the golden source stores; look its hazard up FOR REAL
    # (canonical_scores, not the plot's own COGS score) and roll it up to the display hex it sits in.
    agg: dict[str, dict] = {}
    for p in plots:
        r8 = p["h3_cell"] or h3.latlng_to_cell(p["lat"], p["lon"], 8)
        # exclude heat_acute so a hex shows the standing climate profile, not today's live temperature —
        # the same rule lookup_score() uses for its baseline figure.
        ov = _compute_overall(session, r8, exclude_hazards=frozenset({"heat_acute"}))
        hx = h3.cell_to_parent(r8, res)
        plot_label = {"name": p["plot_name"], "commodity": p["commodity"], "country": p["country"]}
        cur = agg.get(hx)
        if cur is None:
            agg[hx] = {"score": ov.score, "bucket": ov.bucket, "driver": ov.driver_hazard,
                       "n_plots": 1, "n_scored": 1 if ov.score is not None else 0, "plots": [plot_label]}
        else:
            cur["n_plots"] += 1
            cur["plots"].append(plot_label)
            if ov.score is not None:
                cur["n_scored"] += 1
                if cur["score"] is None or ov.score > cur["score"]:  # MAX = the region's worst scored cell
                    cur["score"], cur["bucket"], cur["driver"] = ov.score, ov.bucket, ov.driver_hazard

    plot_hexes = set(agg)
    ring: set[str] = set()
    for hx in plot_hexes:
        ring |= set(h3.grid_disk(hx, 1))   # the grid extends around the book — context cells, not yet scored
    ring -= plot_hexes

    # Clip each hexagon to the land of the country under its centre, so the grid never spills into the
    # sea or across a border — cells whose centre isn't on land are dropped.
    from services.reference.country_boundaries import clip_hex

    def _clipped(cell: str):
        boundary = [[lon, lat] for (lat, lon) in h3.cell_to_boundary(cell)]  # GeoJSON order: [lon, lat]
        center_lat, center_lon = h3.cell_to_latlng(cell)
        return clip_hex(boundary, (center_lon, center_lat))

    hexes = []
    for hx in plot_hexes:
        rings = _clipped(hx)
        if not rings:
            continue
        a = agg[hx]
        hexes.append({"cell": hx, "rings": rings, "score": a["score"], "bucket": a["bucket"],
                      "driver_hazard": a["driver"], "n_plots": a["n_plots"], "plots": a["plots"],
                      "is_plot_cell": True, "status": "scored" if a["score"] is not None else "no_data"})
    for hx in ring:
        rings = _clipped(hx)
        if not rings:
            continue
        hexes.append({"cell": hx, "rings": rings, "score": None, "bucket": None,
                      "driver_hazard": None, "n_plots": 0, "is_plot_cell": False, "status": "no_data"})
    hexes.sort(key=lambda h: (not h["is_plot_cell"], h["score"] is None, -(h["score"] or 0)))
    return {"resolution": res, "hexes": hexes, "n_plot_cells": len(plot_hexes)}


# ── Company operational sites (own footprint: HQ / plants / warehouses / DCs) ──────────────────
class SiteCreate(BaseModel):
    name: str = Field(..., min_length=1)
    site_type: str = "other"
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    country: Optional[str] = None
    annual_value_eur: Optional[float] = None          # asset value (PP&E + inventory) → value-at-risk
    annual_throughput_eur: Optional[float] = None      # revenue/goods through the site → business-interruption


SITE_TEMPLATE_FIELDS = ["name", "site_type", "address", "latitude", "longitude", "country",
                        "annual_value_eur", "annual_throughput_eur"]


@router.get("/sites", summary="The company's own operational sites + each site's worst climate hazard")
def sites(session: DbSession, org_id: OrgId):
    rows = list_sites_with_risk(session, org_id)
    from core.types import score_to_bucket
    for r in rows:
        hs = r.get("hazard_score")
        r["bucket"] = score_to_bucket(hs).value if hs is not None else None
        r["hazard_score"] = round(hs, 1) if hs is not None else None
    totals = {
        "asset_value_eur": sum(r.get("value_eur") or 0 for r in rows),
        "throughput_eur": sum(r.get("throughput_eur") or 0 for r in rows),
        "bi_at_risk_eur": sum(r.get("bi_at_risk_eur") or 0 for r in rows),  # v0 illustrative
        "n_elevated": sum(1 for r in rows if (r.get("hazard_score") or 0) >= 40),
    }
    return {"org_id": org_id, "sites": rows, "site_types": sorted(SITE_TYPES),
            "totals": totals, "bi_note": "Business-interruption is a v0 illustrative estimate (throughput × expected downtime by hazard band); downtime factors are not yet calibrated."}


@router.get("/site/{site_id}", summary="One operational site — record + all hazards + adaptation actions")
def site_detail(site_id: str, session: DbSession):
    from services.intelligence.adaptation import actions_for
    from services.intelligence.company_sites import bi_downtime_fraction
    row = session.execute(text("""
        SELECT s.site_id::text, s.name, s.site_type, CAST(s.latitude AS FLOAT) lat, CAST(s.longitude AS FLOAT) lon,
               s.country, s.address, s.h3_cell, CAST(s.annual_value_eur AS FLOAT) value_eur,
               CAST(s.annual_throughput_eur AS FLOAT) throughput_eur, s.geocode_precision
        FROM sc_company_sites s WHERE s.site_id = :id
    """), {"id": site_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="site not found")
    hazards = site_hazards(session, site_id)
    worst = max((h["score"] for h in hazards if h["score"] is not None), default=None)
    bi = round((row["throughput_eur"] or 0) * bi_downtime_fraction(worst), 0) or None
    return {"kind": "site", "site": dict(row), "hazards": hazards,
            "bi_at_risk_eur": bi, "adaptation": actions_for([h["hazard_type"] for h in hazards if (h["score"] or 0) >= 40])}


@router.post("/sites", summary="Add one operational site (by address or coordinates) → geocode + score")
def create_site(body: SiteCreate, session: DbSession, ctx: CurrentUser):
    org_id = ctx["org"]["org_id"]
    try:
        site = add_site(session, org_id, body.name, body.site_type, address=body.address,
                        lat=body.latitude, lon=body.longitude, country=body.country,
                        annual_value_eur=body.annual_value_eur, annual_throughput_eur=body.annual_throughput_eur,
                        source="user_entry")
    except SiteLocationError as e:
        raise HTTPException(status_code=422, detail={"error": "unlocatable", "message": str(e)})
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="supply.site.add",
                target_type="company_site", target_id=site["site_id"], detail={"name": body.name, "type": site["site_type"]})
    return {"ok": True, "site": site}


@router.get("/commodities", summary="The commodities a plot can be tagged to (for the add-plot picker)")
def commodities(session: DbSession):
    rows = session.execute(text(
        "SELECT commodity_id::text AS id, name, eudr_covered FROM sc_commodities ORDER BY name"
    )).mappings().all()
    return {"commodities": [dict(r) for r in rows]}


class PlotCreate(BaseModel):
    plot_name: str = Field(..., min_length=1)
    commodity: str = Field(..., min_length=1)      # commodity NAME (mapped to id server-side)
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    region: Optional[str] = None
    country: Optional[str] = None
    annual_spend_eur: float = Field(..., gt=0)
    plot_area_ha: Optional[float] = None


@router.post("/plots", summary="Add one sourcing plot (by address or coordinates) → geocode + score")
def create_plot(body: PlotCreate, session: DbSession, ctx: CurrentUser):
    from services.intelligence.company_sites import resolve_location, SiteLocationError as LocErr
    org_id = ctx["org"]["org_id"]
    commodity_id = session.execute(text("SELECT commodity_id::text FROM sc_commodities WHERE name=:n"),
                                   {"n": body.commodity}).scalar()
    if not commodity_id:
        raise HTTPException(status_code=422, detail={"error": "unknown_commodity", "message": f"'{body.commodity}' is not a known commodity."})
    try:
        loc = resolve_location(body.address, body.latitude, body.longitude)
    except LocErr as e:
        raise HTTPException(status_code=422, detail={"error": "unlocatable", "message": str(e)})
    # a >4ha plot given only as a point is EUDR-insufficient — flag it honestly (don't block the add)
    needs_polygon = bool(body.plot_area_ha and body.plot_area_ha > 4.0)
    cell = h3.latlng_to_cell(loc["lat"], loc["lon"], 8)
    plot_id = str(uuid.uuid4())
    session.execute(text("""
        INSERT INTO sc_sourcing_plots (plot_id, org_id, commodity_id, plot_name, latitude, longitude,
                                        h3_cell, region, country, annual_spend_eur, plot_area_ha)
        VALUES (:plot_id, :org_id, :commodity_id, :plot_name, :lat, :lon, :cell, :region, :country, :spend, :area)
    """), {"plot_id": plot_id, "org_id": org_id, "commodity_id": commodity_id, "plot_name": body.plot_name,
           "lat": loc["lat"], "lon": loc["lon"], "cell": cell, "region": body.region,
           "country": body.country or (loc.get("resolved_name") or "").split(", ")[-1] or None,
           "spend": body.annual_spend_eur, "area": body.plot_area_ha})
    session.commit()
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="plots.add",
                target_type="sc_sourcing_plots", target_id=plot_id,
                detail={"plot_name": body.plot_name, "commodity": body.commodity})
    schedule_scoring({cell: (loc["lat"], loc["lon"])})  # background — a fresh cell shouldn't block the add
    return {"ok": True, "plot": {"plot_id": plot_id, "plot_name": body.plot_name, "commodity": body.commodity,
            "lat": loc["lat"], "lon": loc["lon"], "resolved_name": loc.get("resolved_name"),
            "geocode_precision": loc["precision"], "needs_polygon": needs_polygon}}


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    site_type: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    annual_value_eur: Optional[float] = None
    annual_throughput_eur: Optional[float] = None
    country: Optional[str] = None
    region: Optional[str] = None


class PlotUpdate(BaseModel):
    plot_name: Optional[str] = None
    commodity: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    annual_spend_eur: Optional[float] = None
    plot_area_ha: Optional[float] = None
    region: Optional[str] = None
    country: Optional[str] = None


def _own_or_404(session, table, id_col, target_id, org_id, label):
    row = session.execute(text(f"SELECT 1 FROM {table} WHERE {id_col}=:i AND org_id=:o"),
                          {"i": target_id, "o": org_id}).first()
    if not row:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"{label} not found."})


@router.patch("/site/{site_id}", summary="Edit an operational site (material edits need 4-eyes approval)")
def update_site(site_id: str, body: SiteUpdate, session: DbSession,
                ctx: dict = Depends(require_permission("supply.locations.write"))):
    from services.governance.location_governance import submit_or_apply
    org_id = ctx["org"]["org_id"]
    _own_or_404(session, "sc_company_sites", "site_id", site_id, org_id, "Site")
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    changes.pop("commodity", None)  # not a site field
    if not changes:
        raise HTTPException(status_code=400, detail={"error": "no_changes", "message": "No fields to update."})
    return submit_or_apply(session, org_id=org_id, actor_user_id=ctx["user"]["id"],
                           request_type="supply.site.update", target_id=site_id, changes=changes,
                           title=f"Edit site {site_id[:8]}")


@router.delete("/site/{site_id}", summary="Delete an operational site (needs 4-eyes approval)")
def delete_site(site_id: str, session: DbSession,
                ctx: dict = Depends(require_permission("supply.locations.write"))):
    from services.governance.location_governance import submit_or_apply
    org_id = ctx["org"]["org_id"]
    _own_or_404(session, "sc_company_sites", "site_id", site_id, org_id, "Site")
    return submit_or_apply(session, org_id=org_id, actor_user_id=ctx["user"]["id"],
                           request_type="supply.site.delete", target_id=site_id, title=f"Delete site {site_id[:8]}")


@router.patch("/plot/{plot_id}", summary="Edit a sourcing plot (material edits need 4-eyes approval)")
def update_plot(plot_id: str, body: PlotUpdate, session: DbSession,
                ctx: dict = Depends(require_permission("supply.locations.write"))):
    from services.governance.location_governance import submit_or_apply
    org_id = ctx["org"]["org_id"]
    _own_or_404(session, "sc_sourcing_plots", "plot_id", plot_id, org_id, "Plot")
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    commodity = data.pop("commodity", None)
    if not data and not commodity:
        raise HTTPException(status_code=400, detail={"error": "no_changes", "message": "No fields to update."})
    return submit_or_apply(session, org_id=org_id, actor_user_id=ctx["user"]["id"],
                           request_type="supply.plot.update", target_id=plot_id, changes=data,
                           commodity=commodity, title=f"Edit plot {plot_id[:8]}")


@router.delete("/plot/{plot_id}", summary="Delete a sourcing plot (needs 4-eyes approval)")
def delete_plot(plot_id: str, session: DbSession,
                ctx: dict = Depends(require_permission("supply.locations.write"))):
    from services.governance.location_governance import submit_or_apply
    org_id = ctx["org"]["org_id"]
    _own_or_404(session, "sc_sourcing_plots", "plot_id", plot_id, org_id, "Plot")
    return submit_or_apply(session, org_id=org_id, actor_user_id=ctx["user"]["id"],
                           request_type="supply.plot.delete", target_id=plot_id, title=f"Delete plot {plot_id[:8]}")


@router.get("/geocode", summary="Address autocomplete — ranked place candidates (preview, no write)")
def geocode_preview(q: str = Query(..., min_length=2), limit: int = Query(5, ge=1, le=10)):
    """Live address lookup returning ranked candidates so the UI can offer a pick-list
    (the user selects the right place instead of trusting a single best-match)."""
    from services.geocoding.nominatim import geocode_candidates
    return {"results": geocode_candidates(q.strip(), limit=limit)}


@router.get("/sites/template.xlsx", summary="Download the operational-sites upload template (Excel)")
def sites_template_xlsx():
    buf = build_template_workbook(SITE_TEMPLATE_FIELDS)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=company_sites_template.xlsx"})


@router.post("/sites/upload", summary="Bulk-upload operational sites from a CSV")
async def upload_sites(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...)):
    org_id = ctx["org"]["org_id"]
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")
    if "name" not in df.columns:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing": ["name"]})

    added, skipped = [], []
    for _, r in df.iterrows():
        name = str(r.get("name") or "").strip()
        if not name:
            continue
        def _num(v):
            try: return float(v)
            except Exception: return None
        try:
            site = add_site(session, org_id, name, str(r.get("site_type") or "other"),
                            address=(str(r["address"]).strip() if r.get("address") is not None and str(r.get("address")) != "nan" else None),
                            lat=_num(r.get("latitude")), lon=_num(r.get("longitude")),
                            country=(str(r["country"]) if r.get("country") is not None and str(r.get("country")) != "nan" else None),
                            annual_value_eur=_num(r.get("annual_value_eur")),
                            annual_throughput_eur=_num(r.get("annual_throughput_eur")), source="user_upload")
            added.append(site["name"])
        except SiteLocationError:
            skipped.append({"name": name, "reason": "unlocatable — no coordinates or geocodable address"})
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="supply.sites.upload",
                target_type="company_site", target_id=None, detail={"added": len(added), "skipped": len(skipped)})
    return {"ok": True, "added": len(added), "skipped": skipped}


@router.get("/plot/{plot_id}", summary="One sourcing plot — projection + provenance")
def plot_detail(plot_id: str, session: DbSession):
    p = session.execute(text("""
        SELECT p.plot_id::text AS plot_id, p.org_id::text AS org_id, p.plot_name,
               co.name AS commodity, co.eudr_covered, s.name AS supplier, p.country, p.region,
               CAST(p.latitude AS FLOAT) AS lat, CAST(p.longitude AS FLOAT) AS lon, p.h3_cell,
               CAST(p.annual_spend_eur AS FLOAT) AS spend_eur,
               CAST(p.volume_share AS FLOAT) AS volume_share, p.eudr_status, p.eudr_geolocated_at
        FROM sc_sourcing_plots p
        JOIN sc_commodities co ON co.commodity_id=p.commodity_id
        LEFT JOIN sc_suppliers s ON s.supplier_id=p.supplier_id
        WHERE p.plot_id=:id
    """), {"id": plot_id}).mappings().first()
    if not p:
        return {"error": "plot not found"}
    risks = session.execute(text("""
        SELECT hazard_type, scenario, time_horizon,
               CAST(physical_risk_score AS FLOAT) AS score, model_version, scored_at
        FROM v_sc_plot_physical_risk WHERE plot_id=:id
        ORDER BY hazard_type, scenario, time_horizon
    """), {"id": plot_id}).mappings().all()
    from services.intelligence.adaptation import actions_for
    elevated = [r["hazard_type"] for r in risks
                if r["scenario"] == "baseline" and r["time_horizon"] == "current" and (r["score"] or 0) >= 40]
    return {"kind": "plot", "plot": dict(p), "impact_version": IMPACT_VERSION,
            "risks": [dict(r) for r in risks], "adaptation": actions_for(elevated),
            "note": "€ impact is v0 (uncalibrated); see docs/SUPPLY_CHAIN_IMPACT_FUNCTION_METHODOLOGY.md"}


@router.get("/commodity/{commodity_id}", summary="One commodity — analytics: exposure, plots, calibration/validation, projections, adaptation")
def commodity_detail(commodity_id: str, session: DbSession, org_id: OrgId):
    co = session.execute(text("SELECT name, eudr_covered FROM sc_commodities WHERE commodity_id=:id"),
                         {"id": commodity_id}).mappings().first()
    if not co:
        raise HTTPException(status_code=404, detail="commodity not found")
    name = co["name"]

    r = project_org_supply(session, org_id)
    match = next((c for c in r.commodities if getattr(c, "commodity", None) == name), None)
    summary = asdict(match) if match else {"commodity": name}
    driver = summary.get("top_hazard")

    plots = [dict(p) for p in _plots_with_hazard(session, org_id, "baseline", "current") if p["commodity"] == name]

    # projections: the driver hazard across scenarios / time-horizons for this crop's plots
    projections = []
    if driver:
        projections = [dict(x) for x in session.execute(text("""
            SELECT v.scenario, v.time_horizon, ROUND(AVG(v.physical_risk_score)::numeric, 1) AS avg_score, COUNT(*) AS n
            FROM v_sc_plot_physical_risk v JOIN sc_sourcing_plots p ON p.plot_id = v.plot_id
            WHERE p.org_id = :o AND p.commodity_id = :c AND v.hazard_type = :h
            GROUP BY v.scenario, v.time_horizon ORDER BY v.time_horizon
        """), {"o": org_id, "c": commodity_id, "h": driver}).mappings().all()]

    # the calibration / validation record for this crop (every regression we ran, published or held)
    from services.intelligence.supply_cogs import RANGED_PUBLISH_FLOOR
    from ml.confidence_grade import grade as _grade
    from services.intelligence.adaptation import actions_for
    fits = []
    for f in session.execute(text("""
        SELECT f.origin, f.hazard_driver, CAST(f.r2 AS FLOAT) r2, CAST(f.r2_oos AS FLOAT) r2_oos,
               CAST(f.band_cov68 AS FLOAT) band_cov68, f.n_years, f.spei_scale, f.season_months,
               f.baseline_from, f.baseline_to, f.source_note
        FROM sc_commodity_fit f WHERE f.commodity_id = :c ORDER BY f.r2_oos DESC NULLS LAST, f.r2 DESC
    """), {"c": commodity_id}).mappings().all():
        publishes = (f["r2"] or 0) >= RANGED_PUBLISH_FLOOR
        g = _grade(tier="ranged", r2_oos=f["r2_oos"], n_years=f["n_years"], band_cov68=f["band_cov68"]) if publishes else None
        fits.append({**dict(f), "publishes": publishes, "confidence_grade": g.grade if g else None})

    return {"kind": "commodity", "commodity_id": commodity_id, "commodity": name, "eudr_covered": co["eudr_covered"],
            "summary": summary, "plots": plots, "projections": projections, "fits": fits,
            "adaptation": actions_for([driver]) if driver else [],
            "impact_version": IMPACT_VERSION}


def _plots_with_hazard(session, org_id, scenario, horizon):
    """Each plot + its worst projected hazard + EUDR status (for map / disclosure / signals).
    Single DISTINCT ON pass (keeps the highest-scoring hazard per plot) — no per-plot subqueries."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (p.plot_id)
               p.plot_id::text AS plot_id, co.name AS commodity, co.eudr_covered,
               p.plot_name, p.region, p.country, CAST(p.latitude AS FLOAT) AS lat,
               CAST(p.longitude AS FLOAT) AS lon, CAST(p.annual_spend_eur AS FLOAT) AS spend_eur,
               p.eudr_status, p.eudr_determination, p.eudr_first_loss_year,
               CAST(p.eudr_loss_ha AS FLOAT) AS eudr_loss_ha, p.eudr_forest_source,
               p.eudr_determined_at, v.hazard_type AS top_hazard,
               CAST(v.physical_risk_score AS FLOAT) AS hazard_score
        FROM sc_sourcing_plots p
        JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        LEFT JOIN v_sc_plot_physical_risk v
             ON v.plot_id = p.plot_id AND v.scenario = :s AND v.time_horizon = :h
        WHERE p.org_id = :o
        ORDER BY p.plot_id, v.physical_risk_score DESC NULLS LAST
    """), {"o": org_id, "s": scenario, "h": horizon}).mappings().all()
    return sorted(rows, key=lambda r: -(r["spend_eur"] or 0))


@router.get("/signals", summary="Early warning — commodities under elevated hazard now")
def signals(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    r = project_org_supply(session, org_id, scenario=scenario, time_horizon=horizon)
    def level(h):
        return "VH" if h >= 75 else "H" if h >= 55 else "M" if h >= 35 else "L"
    alerts = [{
        "commodity": c.commodity, "hazard": c.top_hazard, "avg_hazard": c.avg_hazard,
        "level": level(c.avg_hazard or 0), "spend_eur": c.annual_spend_eur,
        "cogs_at_risk_p50": c.cogs_at_risk_p50, "calibration": c.calibration,
    } for c in r.commodities if c.status == "scored" and (c.avg_hazard or 0) >= 55]
    alerts.sort(key=lambda a: -(a["avg_hazard"] or 0))
    pending = [{"commodity": c.commodity, "spend_eur": c.annual_spend_eur}
               for c in r.commodities if c.status == "pending"]
    # name → commodity_id so the UI can open each alert's commodity detail page
    commodity_ids = {row["name"]: str(row["commodity_id"]) for row in
                     session.execute(text("SELECT commodity_id, name FROM sc_commodities")).mappings().all()}
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "n_alerts": len(alerts), "alerts": alerts, "pending": pending, "commodity_ids": commodity_ids}


@router.get("/disclosure", summary="EUDR overlay + CSRD physical-risk pack from the book")
def disclosure(session: DbSession, org_id: OrgId,
               scenario: str = Query("baseline"), horizon: str = Query("current")):
    r = project_org_supply(session, org_id, scenario=scenario, time_horizon=horizon)
    plots = _plots_with_hazard(session, org_id, scenario, horizon)
    # EUDR overlay: deforestation-free AND climate-viable (hazard < 60)?
    eudr = []
    for p in plots:
        hs = p["hazard_score"]
        eudr.append({
            "plot_id": p["plot_id"], "commodity": p["commodity"], "plot": p["plot_name"], "region": p["region"],
            "country": p["country"], "eudr_covered": p["eudr_covered"],
            # declared = the customer's self-reported flag; determination = OUR satellite computation.
            "eudr_declared": p["eudr_status"], "eudr_determination": p["eudr_determination"],
            "first_loss_year": p["eudr_first_loss_year"], "loss_ha": p["eudr_loss_ha"],
            "forest_source": p["eudr_forest_source"],
            "determined_at": p["eudr_determined_at"].isoformat() if p["eudr_determined_at"] else None,
            "hazard_score": round(hs, 1) if hs is not None else None,
            "climate_viable": (hs is not None and hs < 60), "scored": hs is not None,
        })
    covered = [e for e in eudr if e["eudr_covered"]]
    det = lambda status: sum(1 for e in covered if e["eudr_determination"] == status)
    eudr_summary = {
        "covered_plots": len(covered),
        # Computed by us from Hansen forest-loss (None until /eudr/determine has been run).
        "determined": sum(1 for e in covered if e["eudr_determination"]),
        "deforestation_free": det("deforestation_free"),
        "non_compliant": det("non_compliant"),
        "geolocation_incomplete": det("geolocation_incomplete"),
        "insufficient": det("insufficient"),
        "climate_at_risk": sum(1 for e in covered if e["scored"] and not e["climate_viable"]),
        "unscored": sum(1 for e in covered if not e["scored"]),
    }
    # CSRD physical-risk: COGS-at-risk by commodity × top hazard
    csrd = [{
        "commodity": c.commodity, "hazard": c.top_hazard, "avg_hazard": c.avg_hazard,
        "spend_eur": c.annual_spend_eur, "cogs_at_risk_p50": c.cogs_at_risk_p50,
        "volume_at_risk_eur": c.volume_at_risk_eur, "calibration": c.calibration, "status": c.status,
        "measured_basis": c.measured_basis,
        # ranged tier: the € is a band with a stated r² (None for a backtested point crop)
        "volume_at_risk_low_eur": c.volume_at_risk_low_eur,
        "volume_at_risk_high_eur": c.volume_at_risk_high_eur, "fit_r2": c.fit_r2,
    } for c in r.commodities]
    return {
        "org_id": org_id, "scenario": scenario, "horizon": horizon, "impact_version": IMPACT_VERSION,
        "rollup": {"ingredient_spend_eur": r.ingredient_spend_eur, "total_cogs_eur": r.total_cogs_eur,
                   "cogs_at_risk_p50_eur": r.cogs_at_risk_p50, "volume_at_risk_eur": r.volume_at_risk_eur,
                   "pct_cogs_at_risk": r.pct_cogs_at_risk},
        "csrd": csrd, "eudr": {"summary": eudr_summary, "plots": eudr},
    }


@router.get("/disclosure.xlsx", summary="EUDR overlay + CSRD physical-risk pack (Excel)")
def disclosure_xlsx(session: DbSession, org_id: OrgId,
                     scenario: str = Query("baseline"), horizon: str = Query("current")):
    r = project_org_supply(session, org_id, scenario=scenario, time_horizon=horizon)
    headers = ["commodity", "hazard", "avg_hazard", "spend_eur", "volume_at_risk_eur",
               "volume_at_risk_low_eur", "volume_at_risk_high_eur", "fit_r2",
               "cogs_at_risk_p50", "calibration", "status"]
    # volume_at_risk and p50 are equal only while no price view is supplied; reading p50 into
    # both columns (as this did) mislabels the export the moment a buyer supplies one. The
    # low/high/r2 columns carry a ranged crop's band + fit strength into the downloaded pack —
    # a held crop leaves €-columns blank (status='held' says why); a backtested crop leaves
    # low/high/r2 blank (it is a point).
    rows = [[c.commodity, c.top_hazard or "", c.avg_hazard, c.annual_spend_eur,
             c.volume_at_risk_eur, c.volume_at_risk_low_eur, c.volume_at_risk_high_eur, c.fit_r2,
             c.cogs_at_risk_p50, c.calibration, c.status]
            for c in r.commodities]
    buf = build_export_workbook(headers, rows, sheet_name="CSRD physical risk")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": f"attachment; filename=tellumen-csrd-supply-{scenario}-{horizon}.xlsx"})


@router.get("/csrd-e1", summary="CSRD / ESRS E1 physical-risk report (own operations + sourcing)")
def csrd_e1(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    return build_e1_report(session, org_id, scenario=scenario, horizon=horizon)


@router.get("/csrd-e1.xlsx", summary="CSRD / ESRS E1 physical-risk report (Excel)")
def csrd_e1_xlsx(session: DbSession, org_id: OrgId,
                 scenario: str = Query("baseline"), horizon: str = Query("current")):
    rep = build_e1_report(session, org_id, scenario=scenario, horizon=horizon)
    headers = ["section", "hazard", "class", "assets_exposed", "value_or_spend_eur",
               "financial_effect_eur", "basis", "max_score"]
    rows: list[list] = []
    for h in rep["material_hazards"]:
        op, up = h.get("own_operations"), h.get("upstream")
        if op:
            rows.append(["Own operations", h["label"], h["class"], f'{op["n_sites"]} sites',
                         round(op["asset_value_eur"]), round(op["bi_at_risk_eur"]),
                         "asset value / business interruption", op["max_score"]])
        if up:
            rows.append(["Upstream sourcing", h["label"], h["class"], f'{up["n_commodities"]} commodities',
                         round(up["spend_eur"]), round(up["cogs_at_risk_eur"]),
                         "spend / COGS-at-risk (published)", up["max_score"]])
    fe = rep["financial_effects"]
    rows.append([])
    rows.append(["FINANCIAL EFFECT — asset value at risk", "", "", "", "", round(fe["asset_value_at_risk_eur"]), "", ""])
    rows.append(["FINANCIAL EFFECT — business interruption (v0)", "", "", "", "", round(fe["business_interruption_eur"]), "", ""])
    rows.append(["FINANCIAL EFFECT — COGS at risk (published)", "", "", "", "", round(fe["cogs_at_risk_published_eur"]), "", ""])
    rows.append(["EXPOSURE MAPPED — € withheld (chain not validated)", "", "", "", round(fe["exposure_mapped_but_withheld_eur"]), "", "", ""])
    buf = build_export_workbook(headers, rows, sheet_name="ESRS E1 physical risk")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": f"attachment; filename=tellumen-csrd-e1-{scenario}-{horizon}.xlsx"})


@router.get("/validation", summary="Impact-function backtests (the credibility record)")
def validation(session: DbSession):
    # `origin` is part of the key: one event validates a crop PER ORIGIN (cocoa 2023/24 is
    # separately validated on CI and on GH). Omitting it rendered the same event twice with no
    # way to tell the two rows apart, so the record read like a duplicate instead of coverage.
    #
    # The VOLUME columns lead, because the volume claim is the claim the product makes. The
    # price columns are the audit trail of a claim we retired — across 440 crop-years a supply
    # shock explains r^2=0.018 of the contemporaneous price move — and ship flagged as such.
    rows = session.execute(text("""
        SELECT event, commodity, origin, hazard, passed,
               CAST(model_prod_shock_pct AS FLOAT) AS model_prod_shock_pct,
               CAST(observed_prod_shock_pct AS FLOAT) AS observed_prod_shock_pct,
               CAST(model_price_move_pct AS FLOAT) AS model_price_move_pct,
               CAST(observed_price_move_pct AS FLOAT) AS observed_price_move_pct,
               price_claim_retired, skill_note, source, run_at
        FROM sc_model_validation ORDER BY event, origin
    """)).mappings().all()
    # attach the crop's Confidence Grade to its passed events (a backtested crop's grade comes
    # from event-reproduction accuracy + how many events back it), so the credibility record
    # carries the same A–E letter the command screen shows.
    from ml.confidence_grade import grade as _grade
    by_commodity: dict = {}
    for r in rows:
        if r["passed"] and r["model_prod_shock_pct"] is not None and r["observed_prod_shock_pct"] is not None:
            by_commodity.setdefault(r["commodity"], []).append(
                abs(r["model_prod_shock_pct"] - r["observed_prod_shock_pct"]) / abs(r["observed_prod_shock_pct"]) * 100)
    grades = {c: _grade(tier="backtested", reproduction_err_pct=min(errs), n_events=len(errs))
              for c, errs in by_commodity.items()}
    out = []
    for r in rows:
        g = grades.get(r["commodity"]) if r["passed"] else None
        out.append({**dict(r), "confidence_grade": g.grade if g else None,
                    "confidence_checks": g.checks if g else None})
    return {"impact_version": IMPACT_VERSION, "events": out}


@router.get("/models", summary="Agriculture hazard models + impact-fn + per-commodity calibration")
def models(session: DbSession, org_id: OrgId):
    from services.intelligence.supply_cogs import COMMODITY_PARAMS, BACKTESTED, CROP_SENSITIVITY
    # ag hazard models (climatology-based) from the registry
    hz = session.execute(text("""
        SELECT hazard_type, model_version, algorithm, training_data_vintage, validation_note, is_active
        FROM model_registry
        WHERE hazard_type IN ('heat_acute','drought','frost','soil_water') AND is_active = true
        ORDER BY hazard_type
    """)).mappings().all()
    # per-commodity calibration status for this org's book
    coms = session.execute(text("""
        SELECT DISTINCT co.commodity_id::text AS commodity_id, co.name FROM sc_sourcing_plots p
        JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = :o ORDER BY co.name
    """), {"o": org_id}).mappings().all()
    # override's {model_p50_eur, override_p50_eur, ...} shape is computed inside compute() --
    # reuse project_org_supply (baseline/current) rather than re-deriving it here from the raw
    # override row, which carries a differently-named field (override_cogs_at_risk_p50_eur) and
    # no model figure to compare against.
    risk_by_commodity = {c.commodity: c for c in project_org_supply(session, org_id).commodities}
    commodities = [{
        "commodity_id": c["commodity_id"], "commodity": c["name"],
        "calibration": "backtested" if c["name"] in BACKTESTED else "indicative",
        "params": COMMODITY_PARAMS.get(c["name"]) or {"sensitivity": CROP_SENSITIVITY.get(c["name"]), "global_share": 1.0, "stock_to_use": None},
        "override": (risk_by_commodity[c["name"]].override if c["name"] in risk_by_commodity else None),
    } for c in coms]
    frost_active = any(r["hazard_type"] == "frost" for r in hz)
    # The RANGED credibility record: every multi-year regression we ran, published or not. A fit
    # at/above the floor publishes a band ('ranged'); a weaker one is shown as tested-but-held.
    # This is the honest counterpart to the single-event backtests on /validation — it says
    # exactly what we tried and how well it worked, including the crops we withhold.
    from services.intelligence.supply_cogs import RANGED_PUBLISH_FLOOR
    from ml.confidence_grade import grade as _grade
    fits = session.execute(text("""
        SELECT co.name AS commodity, f.origin, f.hazard_driver,
               CAST(f.r2 AS FLOAT) AS r2, CAST(f.r2_oos AS FLOAT) AS r2_oos,
               CAST(f.band_cov68 AS FLOAT) AS band_cov68,
               f.n_years, f.spei_scale, f.season_months,
               CAST(f.rmse AS FLOAT) AS rmse, f.baseline_from, f.baseline_to, f.source_note
        FROM sc_commodity_fit f JOIN sc_commodities co ON co.commodity_id = f.commodity_id
        ORDER BY f.r2_oos DESC NULLS LAST, f.r2 DESC
    """)).mappings().all()
    fit_rows = []
    for r in fits:
        publishes = r["r2"] >= RANGED_PUBLISH_FLOOR
        # a published fit carries its Confidence Grade on the credibility record; a below-floor
        # (tested-held) fit is shown WITHOUT a grade — it does not publish a euro.
        g = (_grade(tier="ranged", r2_oos=r["r2_oos"], n_years=r["n_years"], band_cov68=r["band_cov68"])
             if publishes else None)
        fit_rows.append({**dict(r), "publishes": publishes,
                         "confidence_grade": g.grade if g else None,
                         "confidence_checks": g.checks if g else None})
    return {
        "impact_version": IMPACT_VERSION,
        "hazard_models": [dict(r) for r in hz],
        "commodities": commodities,
        "ranged_fits": fit_rows,
        "ranged_publish_floor": RANGED_PUBLISH_FLOOR,
        "frost_note": None if frost_active else
            "Frost hazard is built but not yet scored — CDS's own daily-minimum-temperature "
            "statistic is ECMWF-flagged unusable; pending fix.",
    }


class CogsOverrideRequest(BaseModel):
    override_cogs_at_risk_p50_eur: float = Field(..., ge=0)
    reason: Optional[str] = None


@router.post("/commodity/{commodity_id}/override", summary="Override a commodity's modelled COGS-at-risk (audited)")
def override_commodity_cogs(commodity_id: str, body: CogsOverrideRequest, session: DbSession, ctx: CurrentUser):
    """Same discipline as banking/insurance/real-estate/asset-management's valuation
    overrides: a pricing.approve user can correct a v0/uncalibrated model figure with a
    mandatory reason, fully audited. Scoped to (org, commodity) since sc_commodities is a
    small shared reference table, not per-org."""
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    commodity = session.execute(text("SELECT name FROM sc_commodities WHERE commodity_id = :c"), {"c": commodity_id}).scalar()
    if not commodity:
        raise HTTPException(status_code=404, detail="commodity not found")
    org_id = ctx["org"]["org_id"]
    result = apply_commodity_override(session, org_id, commodity_id, body.override_cogs_at_risk_p50_eur,
                                       ctx["user"]["id"], body.reason)
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"],
                action="commodity.cogs_at_risk.override", target_type="sc_commodity", target_id=commodity_id,
                detail={"commodity": commodity, "override_cogs_at_risk_p50_eur": body.override_cogs_at_risk_p50_eur,
                        "reason": body.reason})
    return {"commodity_id": commodity_id, "commodity": commodity,
            "override_cogs_at_risk_p50_eur": body.override_cogs_at_risk_p50_eur,
            "overridden_at": result["overridden_at"].isoformat()}


@router.delete("/commodity/{commodity_id}/override", summary="Clear a commodity's COGS-at-risk override, revert to the model figure (audited)")
def clear_commodity_cogs_override(commodity_id: str, session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    org_id = ctx["org"]["org_id"]
    cleared = clear_commodity_override(session, org_id, commodity_id)
    if cleared:
        write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"],
                    action="commodity.cogs_at_risk.override_cleared", target_type="sc_commodity", target_id=commodity_id,
                    detail={})
    return {"commodity_id": commodity_id, "cleared": cleared}


# EUDR due-diligence-informed fields: geolocation + commodity are the regulation's own
# core requirement; plot_area_ha matters because EUDR itself splits at >4ha (a full
# polygon is required) vs <=4ha (a single point suffices) -- see services/templates/workbook.py.
PLOT_TEMPLATE_FIELDS = [
    {"name": "plot_name", "required": True, "description": "Free-text plot/farm name.", "example": "Ashanti Plot 4"},
    {"name": "latitude", "required": True, "description": "Decimal degrees, 6 d.p. (EUDR point geolocation). Leave blank if you supply plot_geojson — we take the centroid.", "example": "6.694400"},
    {"name": "longitude", "required": True, "description": "Decimal degrees, 6 d.p. Leave blank if you supply plot_geojson.", "example": "-1.605500"},
    {"name": "commodity", "required": True, "description": "Must match a commodity already on this platform (e.g. Cocoa, Coffee, Citrus).", "example": "Cocoa"},
    {"name": "annual_spend_eur", "required": True, "description": "Annual procurement spend sourced from this plot.", "example": "150000"},
    {"name": "plot_geojson", "required": False, "description": "EUDR plot BOUNDARY as a GeoJSON Polygon — REQUIRED for any plot over 4 ha (a point is only valid at/below 4 ha). Area is computed from it.", "example": '{"type":"Polygon","coordinates":[[[-1.606,6.694],[-1.604,6.694],[-1.604,6.696],[-1.606,6.696],[-1.606,6.694]]]}'},
    {"name": "plot_area_ha", "required": False, "description": "Plot area in hectares. Auto-computed (geodesic) when plot_geojson is given; only needed for a point-only plot.", "example": "2.3"},
    {"name": "region", "required": False, "description": "Free-text region.", "example": "Ashanti"},
    {"name": "country", "required": False, "description": "ISO-2 country code.", "example": "GH"},
]
REQUIRED_PLOT_COLUMNS = [f["name"] for f in PLOT_TEMPLATE_FIELDS if f["required"]]


@router.get("/plots/template.xlsx", summary="Download the EUDR-informed sourcing-plot upload template (Excel)")
def plots_template_xlsx():
    buf = build_template_workbook(PLOT_TEMPLATE_FIELDS)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=tellumen_sourcing_plot_template.xlsx"})


@router.post("/plots/upload", summary="Bulk-upload sourcing plots from a CSV into your procurement book")
async def upload_plots(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...)):
    """Same shape as bank.py's assets/upload: lands in the uploader's OWN org,
    resolves an H3 cell per row, then processes new cells against the golden
    source via the shared services.scoring.on_demand.process_new_cells."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    # latitude/longitude are required only when no plot_geojson column is supplied — a boundary-only
    # upload derives the point from the polygon centroid.
    required_cols = REQUIRED_PLOT_COLUMNS
    if "plot_geojson" in df.columns:
        required_cols = [c for c in REQUIRED_PLOT_COLUMNS if c not in ("latitude", "longitude")]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing": missing})

    commodity_ids = {row["name"]: str(row["commodity_id"]) for row in
                     session.execute(text("SELECT commodity_id, name FROM sc_commodities")).mappings().all()}

    org_id = ctx["org"]["org_id"]
    import json as _json
    has_geo = "plot_geojson" in df.columns
    records, cell_coords, unknown_commodities = [], {}, set()
    geometry_errors, needs_polygon = [], []
    for _, row in df.iterrows():
        try:
            spend = float(row["annual_spend_eur"])
        except (TypeError, ValueError):
            continue
        commodity = str(row["commodity"])
        commodity_id = commodity_ids.get(commodity)
        if not commodity_id:
            unknown_commodities.add(commodity)
            continue
        name = str(row["plot_name"])

        # Geolocation: a GeoJSON boundary (preferred, EUDR-grade) wins; else the lat/lon point.
        geojson = None
        area_ha = float(row["plot_area_ha"]) if "plot_area_ha" in df.columns and pd.notna(row.get("plot_area_ha")) else None
        lat = lon = None
        if has_geo and pd.notna(row.get("plot_geojson")) and str(row.get("plot_geojson")).strip():
            v = validate_plot_geometry(row["plot_geojson"], declared_area_ha=area_ha)
            if not v["ok"]:
                geometry_errors.append({"plot": name, "error": v["error"]})
                continue
            geojson, lat, lon = _json.dumps(v["geojson"]), v["lat"], v["lon"]
            if v["kind"] == "polygon":
                area_ha = v["area_ha"]
            if v["needs_polygon"]:
                needs_polygon.append(name)  # a >4ha plot still sent as a point — flagged, not blocked
        else:
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
            except (TypeError, ValueError):
                continue
            # A >4ha plot with only a point is EUDR-insufficient — flag it honestly.
            if area_ha is not None and area_ha > 4.0:
                needs_polygon.append(name)

        cell = h3.latlng_to_cell(lat, lon, 8)
        cell_coords[cell] = (lat, lon)
        records.append({
            "plot_id": str(uuid.uuid4()), "org_id": org_id, "commodity_id": commodity_id,
            "plot_name": name, "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": str(row["region"]) if "region" in df.columns and pd.notna(row.get("region")) else None,
            "country": str(row["country"]) if "country" in df.columns and pd.notna(row.get("country")) else None,
            "annual_spend_eur": spend, "plot_area_ha": area_ha, "plot_geometry": geojson,
        })
    if not records:
        raise HTTPException(status_code=400, detail={"error": "no_valid_rows",
            "unknown_commodities": list(unknown_commodities), "geometry_errors": geometry_errors})

    session.execute(text("""
        INSERT INTO sc_sourcing_plots (plot_id, org_id, commodity_id, plot_name, latitude, longitude,
                                        h3_cell, region, country, annual_spend_eur, plot_area_ha, plot_geometry)
        VALUES (:plot_id, :org_id, :commodity_id, :plot_name, :latitude, :longitude,
                :h3_cell, :region, :country, :annual_spend_eur, :plot_area_ha, CAST(:plot_geometry AS jsonb))
    """), records)
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="plots.upload",
                target_type="sc_sourcing_plots", target_id=None,
                detail={"n_rows": len(records), "filename": file.filename,
                        "unknown_commodities": list(unknown_commodities),
                        "geometry_errors": geometry_errors, "needs_polygon": needs_polygon})

    schedule_scoring(cell_coords)  # background — a bulk upload spanning fresh cells shouldn't block the response
    return {"n_uploaded": len(records), "unknown_commodities": list(unknown_commodities),
            "geometry_errors": geometry_errors, "needs_polygon": needs_polygon, "scoring": "queued"}


@router.post("/eudr/determine", summary="Run the satellite deforestation-free determination across the book")
def eudr_determine(session: DbSession, ctx: CurrentUser):
    """Compute each plot's EUDR status from the forest layer (not the customer's declared flag) and
    persist it. EUDR-covered plots are checked against Hansen forest-loss; non-covered plots are
    marked not_covered without a forest read. Idempotent — re-run to refresh."""
    import json as _json
    from datetime import datetime, timezone
    org_id = ctx["org"]["org_id"]
    rows = session.execute(text("""
        SELECT p.plot_id::text AS plot_id, p.plot_geometry, p.latitude, p.longitude,
               p.plot_area_ha, co.eudr_covered
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = :o
    """), {"o": org_id}).mappings().all()

    summary: dict = {}
    now = datetime.now(timezone.utc)
    for r in rows:
        det = determine_plot(
            eudr_covered=bool(r["eudr_covered"]), plot_geometry=r["plot_geometry"],
            latitude=r["latitude"], longitude=r["longitude"],
            area_ha=float(r["plot_area_ha"]) if r["plot_area_ha"] is not None else None)
        summary[det.status] = summary.get(det.status, 0) + 1
        session.execute(text("""
            UPDATE sc_sourcing_plots
            SET eudr_determination=:s, eudr_loss_ha=:lh, eudr_first_loss_year=:fy,
                eudr_forest_source=:src, eudr_determined_at=:ts, eudr_evidence=CAST(:ev AS jsonb)
            WHERE plot_id=:pid
        """), {"s": det.status, "lh": det.loss_ha, "fy": det.first_loss_year,
               "src": det.forest_source, "ts": now, "ev": _json.dumps(det.evidence),
               "pid": r["plot_id"]})

    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="eudr.determine",
                target_type="sc_sourcing_plots", target_id=None,
                detail={"n_plots": len(rows), "summary": summary})
    session.commit()
    return {"n_plots": len(rows), "summary": summary, "determined_at": now.isoformat()}


class DdsReference(BaseModel):
    reference_number: str = Field(min_length=1)
    verification_number: Optional[str] = None


@router.post("/eudr/dds", summary="Assemble a submission-ready EUDR Due Diligence Statement")
def eudr_dds_assemble(session: DbSession, ctx: CurrentUser):
    """Build a DDS from the deforestation-free plots + operator identity, persist it as a draft,
    and report readiness (which plots block a filing, what the operator still completes in TRACES)."""
    import json as _json
    org_id = ctx["org"]["org_id"]
    dds = assemble_dds(session, org_id)
    status = "ready" if dds["ready"] else "draft"
    dds_id = session.execute(text("""
        INSERT INTO sc_eudr_dds (org_id, status, payload, blockers, plot_count, covered_count, created_by)
        VALUES (:o, :st, CAST(:p AS jsonb), CAST(:b AS jsonb), :fc, :cc, :u)
        RETURNING dds_id::text
    """), {"o": org_id, "st": status, "p": _json.dumps(dds), "b": _json.dumps(dds["blockers"]),
           "fc": dds["fileable_plots"], "cc": dds["covered_plots"], "u": ctx["user"]["id"]}).scalar()
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="eudr.dds.assemble",
                target_type="sc_eudr_dds", target_id=dds_id,
                detail={"ready": dds["ready"], "fileable": dds["fileable_plots"], "blocked": len(dds["blockers"])})
    session.commit()
    return {"dds_id": dds_id, "status": status, **dds}


@router.get("/eudr/dds/{dds_id}", summary="Fetch an assembled DDS (the frozen payload + status)")
def eudr_dds_get(dds_id: str, session: DbSession, ctx: CurrentUser):
    r = session.execute(text("""
        SELECT dds_id::text, status, reference_number, verification_number, payload, blockers,
               plot_count, covered_count, created_at, filed_at
        FROM sc_eudr_dds WHERE dds_id = :d AND org_id = :o
    """), {"d": dds_id, "o": ctx["org"]["org_id"]}).mappings().first()
    if not r:
        raise HTTPException(status_code=404, detail="DDS not found")
    return dict(r)


@router.put("/eudr/dds/{dds_id}/reference", summary="Capture the TRACES reference number after filing")
def eudr_dds_reference(dds_id: str, body: DdsReference, session: DbSession, ctx: CurrentUser):
    """Record the reference (and optional verification) number the operator receives from TRACES on
    submission — marks the DDS 'filed'. A DDS can only be filed once it was assembled 'ready'."""
    from datetime import datetime, timezone
    org_id = ctx["org"]["org_id"]
    cur = session.execute(text("SELECT status FROM sc_eudr_dds WHERE dds_id=:d AND org_id=:o"),
                          {"d": dds_id, "o": org_id}).mappings().first()
    if not cur:
        raise HTTPException(status_code=404, detail="DDS not found")
    if cur["status"] == "draft":
        raise HTTPException(status_code=409, detail="DDS is not ready to file — resolve blockers and re-assemble")
    now = datetime.now(timezone.utc)
    session.execute(text("""
        UPDATE sc_eudr_dds SET reference_number=:r, verification_number=:v, status='filed',
               filed_at=COALESCE(filed_at, :ts), reference_captured_at=:ts
        WHERE dds_id=:d AND org_id=:o
    """), {"r": body.reference_number, "v": body.verification_number, "ts": now, "d": dds_id, "o": org_id})
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="eudr.dds.filed",
                target_type="sc_eudr_dds", target_id=dds_id,
                detail={"reference_number": body.reference_number})
    session.commit()
    return {"dds_id": dds_id, "status": "filed", "reference_number": body.reference_number,
            "reference_captured_at": now.isoformat()}

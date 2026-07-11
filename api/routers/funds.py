"""Fund & issuer endpoints — the asset-manager product's read API.

Exposes the securities-book model (funds -> positions -> securities -> issuers ->
facilities) and its two risk surfaces (physical footprint + transition), plus
the fund-level SFDR PAI output. Distinct from /v1/assetmgmt (the old flat
located-holding vertical); this is the new issuer/footprint/fund model.

Tenant scoping mirrors the other verticals: a user JWT's org wins; an anonymous
caller only ever sees the demo asset-manager org (never an arbitrary org_id).
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession
from services.asset_manager_engine import (
    fund_descendant_ids, issuer_physical_scores, issuer_transition_scores,
    fund_positions_with_risk,
)
from services.fund_disclosure import fund_climate_summary
from services.reference import gleif
from services.reference.footprint import seed_hq_footprint
from services.reference.resolver import resolve_isin

router = APIRouter(prefix="/v1", tags=["Asset Management — Funds"])

DEMO_ORG = "44444444-4444-4444-8444-444444444444"  # Nordkap Asset Management (demo)
_bearer = HTTPBearer(auto_error=False)


def resolve_org(
    org_id: Optional[str] = Query(None),
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
) -> str:
    """User JWT's org wins (tenant isolation). SECURITY: a caller without a valid
    user JWT can ONLY ever see the demo org — never an arbitrary org_id."""
    token = credentials.credentials if credentials else None
    if token and not token.startswith("cp_live_"):
        from api.security import decode_access_token
        payload = decode_access_token(token)
        if payload and payload.get("org_id"):
            return payload["org_id"]
    return DEMO_ORG


OrgId = Annotated[str, Depends(resolve_org)]


@router.get("/funds", summary="List the org's funds with a headline risk summary")
def list_funds(session: DbSession, org_id: OrgId,
               scenario: str = Query("baseline"), horizon: str = Query("current")):
    funds = session.execute(text("""
        SELECT f.fund_id::text AS fund_id, f.name, f.fund_type, f.sfdr_classification,
               f.parent_fund_id::text AS parent_fund_id
        FROM funds f WHERE f.org_id = :o AND f.parent_fund_id IS NULL
        ORDER BY f.name
    """), {"o": org_id}).mappings().all()
    out = []
    for f in funds:
        summ = fund_climate_summary(session, f["fund_id"], scenario, horizon)
        out.append({
            **dict(f),
            "total_value_eur": summ.get("total_value_eur", 0),
            "positions": summ.get("positions", 0),
            "physical_score": summ.get("physical", {}).get("value_weighted_score"),
            "transition_score": summ.get("transition", {}).get("value_weighted_score"),
            "waci": summ.get("pai", {}).get("pai", {}).get("pai_3_waci_tco2e_per_meur"),
        })
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon, "funds": out}


@router.get("/funds/{fund_id}", summary="Fund climate report — physical + transition + SFDR PAI")
def fund_detail(fund_id: str, session: DbSession, org_id: OrgId,
                scenario: str = Query("baseline"), horizon: str = Query("current")):
    owner = session.execute(text("SELECT org_id::text FROM funds WHERE fund_id = :f"), {"f": fund_id}).scalar()
    if not owner:
        return {"error": "fund not found"}
    if owner != org_id:
        return {"error": "forbidden"}
    return fund_climate_summary(session, fund_id, scenario, horizon)


@router.get("/funds/{fund_id}/positions", summary="Fund positions, each with issuer physical + transition risk")
def fund_positions(fund_id: str, session: DbSession, org_id: OrgId,
                   scenario: str = Query("baseline"), horizon: str = Query("current")):
    owner = session.execute(text("SELECT org_id::text FROM funds WHERE fund_id = :f"), {"f": fund_id}).scalar()
    if not owner:
        return {"error": "fund not found"}
    if owner != org_id:
        return {"error": "forbidden"}
    positions = fund_positions_with_risk(session, fund_id, scenario, horizon)
    positions.sort(key=lambda p: -(p["physical"]["headline_score"] or 0))
    return {"fund_id": fund_id, "scenario": scenario, "horizon": horizon, "positions": positions}


class Holding(BaseModel):
    isin: str
    market_value_eur: float = Field(..., gt=0)          # the position's value; NOT NULL in the book
    weight_pct: Optional[float] = None                  # if omitted, derived from value share
    asset_class: str = "equity"                         # equity / corporate_bond / sovereign_bond / ...
    currency: Optional[str] = None


class HoldingsUpload(BaseModel):
    as_of_date: Optional[date] = None
    holdings: list[Holding]


@router.post("/funds/{fund_id}/holdings", summary="Onboard holdings by ISIN — resolve, locate, and value-weight into the fund")
def onboard_holdings(fund_id: str, body: HoldingsUpload, session: DbSession, org_id: OrgId):
    """The 'upload ISINs alone' action.

    For each holding we (1) resolve the ISIN to an issuer+security from open data
    (GLEIF), (2) seed the issuer's HQ footprint + score it if the issuer is new,
    and (3) record the value-weighted position. The response is an honest
    COVERAGE report: what matched, what didn't, and which enrichment gaps remain
    (sector/NACE, footprint, emissions) — never a fabricated fill.

    Scale note: footprint geocoding + scoring runs inline here, which is right for
    an early-access upload of tens of holdings but not thousands — that path
    should queue (same Celery pattern the gridded hazards already use).
    """
    owner = session.execute(text("SELECT org_id::text FROM funds WHERE fund_id = :f"), {"f": fund_id}).scalar()
    if not owner:
        return {"error": "fund not found"}
    if owner != org_id:
        return {"error": "forbidden"}
    if not body.holdings:
        return {"error": "no holdings supplied"}

    as_of = body.as_of_date or date.today()
    total_value = sum(h.market_value_eur for h in body.holdings) or 1.0

    # De-dupe by ISIN (a book repeats issuers); keep the first value/weight seen.
    by_isin: dict[str, Holding] = {}
    for h in body.holdings:
        key = (h.isin or "").strip().upper()
        by_isin.setdefault(key, h)

    resolutions, positions_created, footprints = [], 0, {"seeded": 0, "failed": 0, "already": 0}
    for isin, h in by_isin.items():
        res = resolve_isin(session, isin, org_id=org_id, asset_class=h.asset_class, currency=h.currency)
        resolutions.append(res.to_dict())
        if res.status not in ("resolved", "cached") or not res.security_id:
            continue  # unmatched / errored ISINs are reported, never positioned

        # Seed the issuer's footprint if it has none yet, so physical risk is
        # computable. Keyed on "has no facility" (NOT on resolved-vs-cached): an
        # issuer resolved in a prior session but never located would otherwise
        # never get a footprint on re-upload.
        has_fac = session.execute(
            text("SELECT 1 FROM issuer_facilities WHERE issuer_id = :i LIMIT 1"),
            {"i": res.issuer_id}).first()
        if has_fac:
            footprints["already"] += 1
        elif res.lei:
            rec = gleif.fetch_lei(res.lei)
            seeded = seed_hq_footprint(session, res.issuer_id, rec) if rec else None
            footprints["seeded" if seeded else "failed"] += 1
        else:
            footprints["failed"] += 1  # matched security but no LEI to locate from — surfaced

        weight = h.weight_pct if h.weight_pct is not None else round(100.0 * h.market_value_eur / total_value, 6)
        session.execute(text("""
            INSERT INTO fund_positions (fund_id, security_id, market_value_eur, weight_pct, as_of_date)
            VALUES (:f, :s, :mv, :w, :d)
            ON CONFLICT (fund_id, security_id, as_of_date)
            DO UPDATE SET market_value_eur = EXCLUDED.market_value_eur, weight_pct = EXCLUDED.weight_pct
        """), {"f": fund_id, "s": res.security_id, "mv": h.market_value_eur, "w": weight, "d": as_of})
        positions_created += 1

    matched = sum(1 for r in resolutions if r["status"] in ("resolved", "cached"))
    sector_gaps = [r["isin"] for r in resolutions if r["status"] in ("resolved", "cached") and not r["sector_known"]]
    return {
        "fund_id": fund_id, "as_of_date": as_of.isoformat(),
        "holdings_submitted": len(body.holdings), "distinct_isins": len(by_isin),
        "positions_created": positions_created,
        "coverage": {
            "matched": matched,
            "match_rate_pct": round(100.0 * matched / len(by_isin), 1) if by_isin else 0.0,
            "unmatched": [r["isin"] for r in resolutions if r["status"] == "unmatched"],
            "errored": [r["isin"] for r in resolutions if r["status"] == "error"],
            "footprints": footprints,
            "sector_gap_isins": sector_gaps,   # matched but NACE unknown → needed for EU Taxonomy
        },
        "resolutions": resolutions,
        "note": "Physical risk is now computable for located issuers. Sector/NACE, "
                "multi-facility footprints and issuer emissions are the remaining "
                "enrichment inputs (surfaced, not fabricated).",
    }


@router.get("/issuers/{issuer_id}", summary="One issuer — full facility footprint + physical + transition detail")
def issuer_detail(issuer_id: str, session: DbSession, org_id: OrgId,
                  scenario: str = Query("baseline"), horizon: str = Query("current")):
    # tenant check: the issuer must be held by at least one of this org's funds
    held = session.execute(text("""
        SELECT 1 FROM fund_positions p
        JOIN securities s ON s.security_id = p.security_id
        JOIN funds f ON f.fund_id = p.fund_id
        WHERE s.issuer_id = :i AND f.org_id = :o LIMIT 1
    """), {"i": issuer_id, "o": org_id}).first()
    if not held:
        return {"error": "issuer not found in your holdings"}

    issuer = session.execute(text("""
        SELECT issuer_id::text AS issuer_id, lei, name, issuer_type, country, sector, nace_code
        FROM issuers WHERE issuer_id = :i
    """), {"i": issuer_id}).mappings().first()

    facilities = session.execute(text("""
        SELECT f.facility_id::text AS facility_id, f.name, f.facility_type, f.country, f.region,
               CAST(f.latitude AS FLOAT) AS lat, CAST(f.longitude AS FLOAT) AS lon, f.h3_cell,
               CAST(f.materiality_weight AS FLOAT) AS materiality_weight, f.weight_basis
        FROM issuer_facilities f WHERE f.issuer_id = :i ORDER BY f.materiality_weight DESC
    """), {"i": issuer_id}).mappings().all()

    # per-facility current scores (the lowest level — the raw golden-source reading)
    fac_scores = session.execute(text("""
        SELECT facility_id::text AS facility_id, hazard_type,
               ROUND(physical_risk_score::numeric, 1) AS score, risk_bucket, model_version
        FROM v_issuer_facility_physical_risk
        WHERE issuer_id = :i AND scenario = :s AND time_horizon = :h
    """), {"i": issuer_id, "s": scenario, "h": horizon}).mappings().all()
    by_fac: dict = {}
    for r in fac_scores:
        by_fac.setdefault(r["facility_id"], []).append(
            {"hazard": r["hazard_type"], "score": float(r["score"]), "bucket": r["risk_bucket"],
             "model_version": r["model_version"]})

    phys = issuer_physical_scores(session, scenario, horizon, [issuer_id]).get(issuer_id, {})
    trans = issuer_transition_scores(session, scenario, horizon, [issuer_id]).get(issuer_id)
    emissions = session.execute(text("""
        SELECT reporting_year, CAST(scope1_tco2e AS FLOAT) AS scope1, CAST(scope2_tco2e AS FLOAT) AS scope2,
               CAST(scope3_tco2e AS FLOAT) AS scope3, CAST(revenue_eur AS FLOAT) AS revenue_eur, source
        FROM issuer_emissions WHERE issuer_id = :i ORDER BY reporting_year DESC LIMIT 1
    """), {"i": issuer_id}).mappings().first()

    return {
        "issuer": dict(issuer),
        "physical": phys,
        "transition": trans,
        "emissions": dict(emissions) if emissions else None,
        "facilities": [{**dict(f), "scores": by_fac.get(f["facility_id"], [])} for f in facilities],
    }

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
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from api.deps import DbSession
from ml.regulatory.sfdr_pai import entity_pai_statement, sfdr_pai_statement, sfdr_pai_statement_xlsx
from ml.regulatory.sfdr_periodic import periodic_report
from ml.regulatory.sfdr_xbrl import sfdr_pai_xbrl
from ml.regulatory.voluntary_pai import CATALOG as _VOLUNTARY_CATALOG
from ml.regulatory.voluntary_pai import catalog as voluntary_catalog
from ml.regulatory.voluntary_pai import validate_keys
from services.asset_manager_engine import (
    fund_positions_with_risk,
    issuer_physical_scores,
    issuer_transition_scores,
)
from services.fund_disclosure import fund_climate_summary
from services.reference import gleif
from services.reference.emissions_estimation import estimate_emissions
from services.reference.footprint import seed_hq_footprint
from services.reference.fx import FxError, to_eur
from services.reference.resolver import _ASSET_CLASSES, resolve_isin
from services.reference.vendor_ingest import PROFILES as _VENDOR_PROFILES
from services.reference.vendor_ingest import ingest_vendor_extract
from services.sfdr_batch import batch_status, create_batch, run_batch

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
    # Supply EITHER market_value_eur (already in EUR) OR market_value + currency
    # (native, converted to EUR at the book's as-of date). Exactly one is required.
    market_value_eur: Optional[float] = Field(None, gt=0)  # value in EUR
    market_value: Optional[float] = Field(None, gt=0)      # value in the position's native currency
    weight_pct: Optional[float] = None                  # if omitted, derived from value share
    asset_class: Optional[str] = None                   # equity / corporate_bond / sovereign_bond / … (None → default equity on first resolve)
    currency: Optional[str] = None                      # ISO 4217 of market_value (default EUR)

    @model_validator(mode="after")
    def _one_value(self) -> "Holding":
        if self.market_value_eur is None and self.market_value is None:
            raise ValueError("each holding needs market_value_eur, or market_value + currency")
        return self
    # ── Optional issuer data the client already holds (fills SFDR gaps) ──
    nace_code: Optional[str] = None                     # issuer industry → EU Taxonomy + fossil-fuel PAI
    sector: Optional[str] = None
    revenue_eur: Optional[float] = Field(None, gt=0)    # denominator for carbon intensity / WACI — must be positive
    scope1_tco2e: Optional[float] = Field(None, ge=0)
    scope2_tco2e: Optional[float] = Field(None, ge=0)
    scope3_tco2e: Optional[float] = Field(None, ge=0)
    evic_eur: Optional[float] = Field(None, gt=0)       # enterprise value incl. cash → PCAF attribution (PAI 1/2)
    reporting_year: Optional[int] = None
    # ── Non-carbon ESG facts (SFDR PAI 5-14), from the manager's ESG feed ──
    non_renewable_energy_pct: Optional[float] = None    # PAI 5
    energy_intensity_gwh_per_meur: Optional[float] = None  # PAI 6
    biodiversity_sensitive_ops: Optional[bool] = None   # PAI 7
    emissions_to_water_tonnes: Optional[float] = None    # PAI 8
    hazardous_waste_tonnes: Optional[float] = None       # PAI 9
    ungc_oecd_violation: Optional[bool] = None           # PAI 10
    ungc_oecd_no_monitoring: Optional[bool] = None       # PAI 11
    gender_pay_gap_pct: Optional[float] = None           # PAI 12
    board_female_pct: Optional[float] = None             # PAI 13
    controversial_weapons: Optional[bool] = None         # PAI 14
    # EU Taxonomy — the issuer's own Article-8 reported figures (% of revenue)
    taxonomy_eligible_pct: Optional[float] = Field(None, ge=0, le=100)
    taxonomy_aligned_pct: Optional[float] = Field(None, ge=0, le=100)
    # DNSH / minimum-safeguards attestation. NULL = not separately assessed (take
    # reported aligned as-is); False = known to fail → that issuer's aligned excluded.
    taxonomy_dnsh_ok: Optional[bool] = None
    taxonomy_min_safeguards_ok: Optional[bool] = None
    # Voluntary (additional) PAI values, keyed by catalog indicator_key → number or bool.
    voluntary_pai: Optional[dict] = None


class HoldingsUpload(BaseModel):
    as_of_date: Optional[date] = None
    holdings: list[Holding]


def _apply_issuer_enrichment(session, issuer_id: str, org_id: str, h: "Holding") -> dict:
    """Persist the issuer data a client supplied on a holding. Returns which
    fields were written. NACE/sector is a shared fact (enrich only when unknown,
    never clobber); emissions/revenue are the client's PRIVATE disclosure,
    org-scoped and marked source='client' — never a fabricated value."""
    wrote = {"sector": False, "emissions": False, "estimated": False, "esg": False, "voluntary": False}

    if h.nace_code or h.sector:
        session.execute(text("""
            UPDATE issuers
               SET nace_code = COALESCE(nace_code, :nace),
                   sector    = COALESCE(sector, :sector),
                   updated_at = now()
             WHERE issuer_id = :i
        """), {"i": issuer_id, "nace": h.nace_code, "sector": h.sector})
        wrote["sector"] = True

    if h.revenue_eur is not None or h.scope1_tco2e is not None or h.evic_eur is not None:
        session.execute(text("""
            INSERT INTO issuer_emissions
                (issuer_id, org_id, reporting_year, scope1_tco2e, scope2_tco2e, scope3_tco2e,
                 revenue_eur, evic_eur, source, data_vintage)
            VALUES (:i, :org, :yr, :s1, :s2, :s3, :rev, :evic, 'client', now())
            ON CONFLICT (issuer_id, reporting_year, source, org_id) WHERE org_id IS NOT NULL
            -- COALESCE so a partial follow-up (e.g. EVIC only) fills gaps without
            -- erasing figures supplied earlier.
            DO UPDATE SET scope1_tco2e = COALESCE(EXCLUDED.scope1_tco2e, issuer_emissions.scope1_tco2e),
                          scope2_tco2e = COALESCE(EXCLUDED.scope2_tco2e, issuer_emissions.scope2_tco2e),
                          scope3_tco2e = COALESCE(EXCLUDED.scope3_tco2e, issuer_emissions.scope3_tco2e),
                          revenue_eur  = COALESCE(EXCLUDED.revenue_eur, issuer_emissions.revenue_eur),
                          evic_eur     = COALESCE(EXCLUDED.evic_eur, issuer_emissions.evic_eur),
                          data_vintage = EXCLUDED.data_vintage
        """), {"i": issuer_id, "org": org_id, "yr": h.reporting_year or date.today().year,
               "s1": h.scope1_tco2e, "s2": h.scope2_tco2e, "s3": h.scope3_tco2e,
               "rev": h.revenue_eur, "evic": h.evic_eur})
        wrote["emissions"] = True

    # Estimation gap-fill: revenue + sector but no disclosed scope → estimate
    # scope 1+2 (sector intensity × revenue), stored source='estimated', method
    # disclosed. Never overrides a real scope the client gave.
    if h.scope1_tco2e is None and h.revenue_eur:
        nace = h.nace_code or session.execute(
            text("SELECT nace_code FROM issuers WHERE issuer_id = :i"), {"i": issuer_id}).scalar()
        est = estimate_emissions(nace, h.revenue_eur)
        if est:
            session.execute(text("""
                INSERT INTO issuer_emissions
                    (issuer_id, org_id, reporting_year, scope1_tco2e, revenue_eur,
                     source, estimation_method, data_vintage)
                VALUES (:i, :org, :yr, :s12, :rev, 'estimated', :method, now())
                ON CONFLICT (issuer_id, reporting_year, source, org_id) WHERE org_id IS NOT NULL
                DO UPDATE SET scope1_tco2e = EXCLUDED.scope1_tco2e, revenue_eur = EXCLUDED.revenue_eur,
                              estimation_method = EXCLUDED.estimation_method, data_vintage = EXCLUDED.data_vintage
            """), {"i": issuer_id, "org": org_id, "yr": h.reporting_year or date.today().year,
                   "s12": est["scope1_2_tco2e"], "rev": h.revenue_eur, "method": est["method"]})
            wrote["estimated"] = True

    # Non-carbon ESG facts (PAI 5-14) — org-scoped private disclosure.
    esg_fields = {
        "non_renewable_energy_pct": h.non_renewable_energy_pct,
        "energy_intensity_gwh_per_meur": h.energy_intensity_gwh_per_meur,
        "biodiversity_sensitive_ops": h.biodiversity_sensitive_ops,
        "emissions_to_water_tonnes": h.emissions_to_water_tonnes,
        "hazardous_waste_tonnes": h.hazardous_waste_tonnes,
        "ungc_oecd_violation": h.ungc_oecd_violation,
        "ungc_oecd_no_monitoring": h.ungc_oecd_no_monitoring,
        "gender_pay_gap_pct": h.gender_pay_gap_pct,
        "board_female_pct": h.board_female_pct,
        "controversial_weapons": h.controversial_weapons,
        "taxonomy_eligible_pct": h.taxonomy_eligible_pct,
        "taxonomy_aligned_pct": h.taxonomy_aligned_pct,
        "dnsh_ok": h.taxonomy_dnsh_ok,
        "min_safeguards_ok": h.taxonomy_min_safeguards_ok,
    }
    if any(v is not None for v in esg_fields.values()):
        cols = ", ".join(esg_fields)
        placeholders = ", ".join(f":{k}" for k in esg_fields)
        updates = ", ".join(f"{k} = EXCLUDED.{k}" for k in esg_fields)
        session.execute(text(f"""
            INSERT INTO issuer_esg_metrics (issuer_id, org_id, reporting_year, {cols}, source, data_vintage)
            VALUES (:i, :org, :yr, {placeholders}, 'client', now())
            ON CONFLICT (issuer_id, reporting_year, org_id) WHERE org_id IS NOT NULL
            DO UPDATE SET {updates}, data_vintage = now()
        """), {"i": issuer_id, "org": org_id, "yr": h.reporting_year or date.today().year, **esg_fields})
        wrote["esg"] = True

    # Voluntary (additional) PAI values — org-scoped, only for catalog keys.
    if h.voluntary_pai:
        yr = h.reporting_year or date.today().year
        for key, val in h.voluntary_pai.items():
            if key not in _VOLUNTARY_CATALOG:
                continue  # unknown indicator key — surfaced upstream, never stored
            num = val if isinstance(val, (int, float)) and not isinstance(val, bool) else None
            flag = val if isinstance(val, bool) else None
            session.execute(text("""
                INSERT INTO issuer_voluntary_pai (issuer_id, org_id, indicator_key, reporting_year, value_num, value_bool, source)
                VALUES (:i, :org, :k, :yr, :num, :flag, 'client')
                ON CONFLICT (issuer_id, org_id, indicator_key, reporting_year)
                DO UPDATE SET value_num = EXCLUDED.value_num, value_bool = EXCLUDED.value_bool, data_vintage = now()
            """), {"i": issuer_id, "org": org_id, "k": key, "yr": yr, "num": num, "flag": flag})
        wrote["voluntary"] = True

    return wrote


_HOLDINGS_TEMPLATE = (
    "# Tellumen holdings template — one holding per row.\n"
    "# Value the line EITHER in EUR (market_value_eur) OR in its native currency\n"
    "#   (market_value + currency, e.g. 5000000 + USD — we convert to EUR at the ECB\n"
    "#   rate for the book's as-of date). Give one or the other, not both.\n"
    "# Optional (fill what you already hold — it fills the SFDR statement):\n"
    "#   nace_code (EU industry code), revenue_eur, scope1_tco2e, scope2_tco2e, scope3_tco2e,\n"
    "#   evic_eur (enterprise value incl. cash — unlocks financed emissions, PAI 1/2), asset_class, reporting_year.\n"
    "# Leave any optional cell blank; blanks are surfaced as gaps, never guessed. Delete these comment rows before use.\n"
    "isin,market_value_eur,market_value,currency,nace_code,revenue_eur,scope1_tco2e,scope2_tco2e,scope3_tco2e,evic_eur,asset_class,reporting_year\n"
    "US0378331005,5000000,,,26.20,383000000000,55000,0,16200000,2900000000000,equity,2023\n"
    "DE0007164600,4000000,,,62.01,31200000000,30000,45000,4300000,210000000000,equity,2023\n"
    "US5949181045,,6000000,USD,62.01,211900000000,290000,110000,13800000,2700000000000,equity,2023\n"
    "CH0038863350,3500000,,,,,,,,,equity,\n"
)


@router.get("/holdings/template.csv", summary="Download a holdings template a manager fills with their book")
def holdings_template():
    return StreamingResponse(
        iter([_HOLDINGS_TEMPLATE]), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="tellumen_holdings_template.csv"'})


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

    # ── FX: normalize every line to EUR at the book's as-of date ───────────
    # A holding may arrive already in EUR (market_value_eur) or in a native
    # currency (market_value + currency). We convert the native ones and keep
    # the original amount + currency for audit. An unknown currency is a hard,
    # surfaced error — EUR is never silently assumed for a non-EUR line.
    # Aggregate repeated ISINs (a book can list the same security as several lots):
    # SUM their EUR value rather than dropping later lots. Enrichment fields keep
    # the first non-null seen; native base only survives if all lots share a ccy.
    by_isin: dict[str, Holding] = {}
    native: dict[str, dict] = {}     # isin -> {base, ccy, mixed}
    fx_applied: dict[str, dict] = {}  # ccy -> {rate, rate_date, source}
    fx_errors: list[str] = []
    for h in body.holdings:
        key = (h.isin or "").strip().upper()
        raw_ccy = (h.currency or "").strip().upper()
        if h.market_value_eur is not None:
            # EUR value supplied directly — no FX guess needed; currency only labels the native base.
            eur = h.market_value_eur
            ccy = raw_ccy or "EUR"
            base = h.market_value if h.market_value is not None else (eur if ccy == "EUR" else None)
        else:
            # Native value → must convert. A blank currency is NOT assumed to be EUR (audit T9):
            # surface it so the uploader supplies a currency or a market_value_eur.
            if not raw_ccy:
                fx_errors.append(f"{key or 'line'}: market value given without a currency — cannot "
                                 "convert to EUR (specify a currency or provide market_value_eur)")
                continue
            ccy = raw_ccy
            try:
                conv = to_eur(session, h.market_value, ccy, as_of)
            except FxError as e:
                fx_errors.append(str(e))
                continue
            eur = conv["eur"]
            base = h.market_value
            if ccy != "EUR":
                fx_applied[ccy] = {"rate": conv["rate"], "rate_date": conv["rate_date"], "source": conv["source"]}
        if key in by_isin:
            by_isin[key].market_value_eur += eur
            n = native[key]
            if n["ccy"] == ccy and n["base"] is not None and base is not None:
                n["base"] += base
            else:
                n["mixed"] = True
        else:
            by_isin[key] = h.model_copy(update={"market_value_eur": eur})
            native[key] = {"base": base, "ccy": ccy, "mixed": False}

    total_value = sum(h.market_value_eur for h in by_isin.values()) or 1.0

    resolutions, positions_created, footprints = [], 0, {"seeded": 0, "failed": 0, "already": 0}
    enriched = {"sector": 0, "emissions": 0, "estimated": 0, "esg": 0, "voluntary": 0}
    for isin, h in by_isin.items():
        res = resolve_isin(session, isin, org_id=org_id, asset_class=h.asset_class or "equity", currency=h.currency)
        resolutions.append(res.to_dict())
        if res.status not in ("resolved", "cached") or not res.security_id:
            continue  # unmatched / errored ISINs are reported, never positioned

        # An explicit asset-class hint (e.g. corporate_bond, sovereign_bond) must
        # relabel an already-cached security — the resolver's cache fast-path skips
        # the upsert, so a bond first seen as the default 'equity' would stay wrong.
        if h.asset_class and h.asset_class in _ASSET_CLASSES:
            session.execute(text("UPDATE securities SET asset_class = :ac WHERE security_id = :s"),
                            {"ac": h.asset_class, "s": res.security_id})

        # Store any issuer data the client supplied on this holding.
        wrote = _apply_issuer_enrichment(session, res.issuer_id, org_id, h)
        if wrote["sector"]:
            enriched["sector"] += 1
        if wrote["emissions"]:
            enriched["emissions"] += 1
        if wrote["estimated"]:
            enriched["estimated"] += 1
        if wrote["esg"]:
            enriched["esg"] += 1
        if wrote["voluntary"]:
            enriched["voluntary"] += 1

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
        n = native[isin]
        pos_ccy = "EUR" if n["mixed"] else n["ccy"]
        pos_base = None if n["mixed"] else n["base"]
        session.execute(text("""
            INSERT INTO fund_positions (fund_id, security_id, market_value_eur, market_value_base, currency, weight_pct, as_of_date)
            VALUES (:f, :s, :mv, :mvb, :ccy, :w, :d)
            ON CONFLICT (fund_id, security_id, as_of_date)
            DO UPDATE SET market_value_eur = EXCLUDED.market_value_eur,
                          market_value_base = EXCLUDED.market_value_base,
                          currency = EXCLUDED.currency, weight_pct = EXCLUDED.weight_pct
        """), {"f": fund_id, "s": res.security_id, "mv": h.market_value_eur,
               "mvb": pos_base, "ccy": pos_ccy, "w": weight, "d": as_of})
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
            "client_enriched": enriched,        # issuer data the client supplied on this upload
        },
        "fx": {
            "converted_currencies": fx_applied,  # ccy -> {rate (EUR per unit), rate_date, source}
            "errors": fx_errors,                 # lines dropped for an unknown currency (surfaced, never guessed)
        },
        "resolutions": resolutions,
        "note": "Physical risk is now computable for located issuers. Sector/NACE, "
                "multi-facility footprints and issuer emissions are the remaining "
                "enrichment inputs — supply them per holding (optional columns) to "
                "fill the SFDR statement; surfaced, never fabricated.",
    }


class Constituent(BaseModel):
    isin: str
    weight_pct: float = Field(..., gt=0, le=100)   # share of the held fund/ETF


class LookThroughUpload(BaseModel):
    held_isin: str                                 # the ETF/fund held in the parent
    as_of_date: Optional[date] = None
    constituents: list[Constituent]


@router.post("/funds/{fund_id}/lookthrough", summary="Expand a held fund/ETF to its constituents (SFDR look-through)")
def expand_lookthrough(fund_id: str, body: LookThroughUpload, session: DbSession, org_id: OrgId):
    """SFDR requires looking THROUGH a held fund/ETF to its underlying issuers.

    We model the held vehicle as a SUB-FUND: its constituents are onboarded there
    (each valued at held_value × constituent weight), the parent's now-redundant
    ETF line is removed, and the existing fund-hierarchy roll-up (fund_descendant_ids)
    naturally folds the look-through issuers into every PAI figure. No double count.
    """
    err = _fund_owned_or_error(session, fund_id, org_id)
    if err:
        return {"error": err}
    held = (body.held_isin or "").strip().upper()
    as_of = body.as_of_date or date.today()
    # the parent's position value in the held vehicle
    held_mv = session.execute(text("""
        SELECT CAST(p.market_value_eur AS FLOAT) FROM fund_positions p
        JOIN securities s ON s.security_id = p.security_id
        WHERE p.fund_id = :f AND s.isin = :i
        ORDER BY p.as_of_date DESC LIMIT 1
    """), {"f": fund_id, "i": held}).scalar()
    if not held_mv:
        return {"error": f"{held} is not a position in this fund — nothing to look through"}
    if abs(sum(c.weight_pct for c in body.constituents) - 100) > 1.0:
        return {"error": "constituent weights must sum to ~100%",
                "supplied_total_pct": round(sum(c.weight_pct for c in body.constituents), 2)}

    # sub-fund representing the held vehicle's look-through
    subfund_name = f"{held} · look-through"
    parent = session.execute(text("SELECT name, sfdr_classification, base_currency FROM funds WHERE fund_id = :f"),
                             {"f": fund_id}).mappings().first()
    subfund_id = session.execute(text("""
        INSERT INTO funds (org_id, name, fund_type, parent_fund_id, sfdr_classification, base_currency)
        VALUES (:o, :n, 'sub_portfolio', :p, :cls, :ccy)
        RETURNING fund_id
    """), {"o": org_id, "n": subfund_name, "p": fund_id,
           "cls": parent["sfdr_classification"], "ccy": parent["base_currency"] or "EUR"}).scalar()
    subfund_id = str(subfund_id)

    holdings = [Holding(isin=c.isin, market_value_eur=round(held_mv * c.weight_pct / 100, 2)) for c in body.constituents]
    result = onboard_holdings(subfund_id, HoldingsUpload(as_of_date=as_of, holdings=holdings), session, org_id)

    # drop the parent's held-vehicle line so its issuers aren't double-counted.
    session.execute(text("""
        DELETE FROM fund_positions WHERE fund_id = :f AND security_id IN
        (SELECT security_id FROM securities WHERE isin = :i)
    """), {"f": fund_id, "i": held})

    return {
        "held_isin": held, "held_value_eur": round(held_mv), "sub_fund_id": subfund_id,
        "constituents_supplied": len(body.constituents),
        "constituents_resolved": result["coverage"]["matched"],
        "note": "Held vehicle expanded to its constituents as a sub-fund; the parent's "
                "line was removed so PAI figures now reflect the underlying issuers, not the wrapper.",
    }


@router.post("/funds/{fund_id}/sfdr-statement/file", summary="Freeze the current SFDR statement as the official filing for its reference year")
def file_sfdr_statement(fund_id: str, session: DbSession, org_id: OrgId):
    """Snapshot the current statement immutably for its reference year, so next
    year's statement can show the year-on-year comparison against what was filed."""
    err = _fund_owned_or_error(session, fund_id, org_id)
    if err:
        return {"error": err}
    st = sfdr_pai_statement(session, fund_id)
    if st.get("error"):
        return st
    ref_year = st["summary"].get("reference_year")
    if not ref_year:
        return {"error": "no reference year — supply issuer emissions with a reporting year before filing"}
    import json
    session.execute(text("""
        INSERT INTO fund_sfdr_filings (fund_id, org_id, reference_year, period_start, period_end,
               statement, narrative_summary, filed_by, status)
        VALUES (:f, :o, :y, make_date(:y,1,1), make_date(:y,12,31), CAST(:snap AS jsonb), :narr, :by, 'filed')
        ON CONFLICT (fund_id, reference_year)
        DO UPDATE SET statement = EXCLUDED.statement, narrative_summary = EXCLUDED.narrative_summary,
                      filed_by = EXCLUDED.filed_by, filed_at = now()
    """), {"f": fund_id, "o": org_id, "y": ref_year,
           "snap": json.dumps(st), "narr": st["coverage_summary"]["filing_readiness"],
           "by": st["entity"].get("manager_legal_name") or st["entity"]["manager"]})
    return {"ok": True, "reference_year": ref_year,
            "filed": f"FY{ref_year} statement frozen for {st['entity']['fund_name']}"}


@router.get("/funds/{fund_id}/periodic-report", summary="SFDR Article 8/9 periodic disclosure (RTS Annex IV/V)")
def sfdr_periodic_report(fund_id: str, session: DbSession, org_id: OrgId):
    err = _fund_owned_or_error(session, fund_id, org_id)
    if err:
        return {"error": err}
    return periodic_report(session, fund_id)


@router.get("/funds/{fund_id}/sfdr-filings", summary="Prior SFDR filings for this fund (year-on-year history)")
def list_sfdr_filings(fund_id: str, session: DbSession, org_id: OrgId):
    err = _fund_owned_or_error(session, fund_id, org_id)
    if err:
        return {"error": err}
    rows = session.execute(text("""
        SELECT reference_year, filed_at, filed_by, status FROM fund_sfdr_filings
        WHERE fund_id = :f ORDER BY reference_year DESC
    """), {"f": fund_id}).mappings().all()
    return {"fund_id": fund_id, "filings": [dict(r) for r in rows]}


@router.get("/entity/sfdr-statement", summary="Entity-level SFDR PAI statement — aggregated across ALL the manager's funds")
def entity_sfdr_statement(session: DbSession, org_id: OrgId):
    """One PAI statement value-weighted across every fund the manager runs — what a
    large manager files at entity level, alongside per-fund statements."""
    return entity_pai_statement(session, org_id)


class BatchCreate(BaseModel):
    reference_year: int = Field(..., ge=2000, le=2100)
    run: bool = True                 # generate immediately (else create pending only)
    limit: Optional[int] = None      # cap funds processed this call (chunked runs)


@router.post("/entity/sfdr-batch", summary="Generate SFDR statements across ALL the manager's funds (resumable batch)")
def create_sfdr_batch(body: BatchCreate, session: DbSession, org_id: OrgId):
    batch_id = create_batch(session, org_id, body.reference_year)
    if body.run:
        return run_batch(session, batch_id, limit=body.limit)
    return batch_status(session, batch_id)


@router.post("/entity/sfdr-batch/{batch_id}/run", summary="Resume a batch — process the funds still pending/errored")
def resume_sfdr_batch(batch_id: str, session: DbSession, org_id: OrgId,
                      limit: Optional[int] = Query(None)):
    owner = session.execute(text("SELECT org_id::text FROM sfdr_batch_runs WHERE batch_id=:b"), {"b": batch_id}).scalar()
    if not owner:
        return {"error": "batch not found"}
    if owner != org_id:
        return {"error": "forbidden"}
    return run_batch(session, batch_id, limit=limit)


@router.get("/entity/sfdr-batch/{batch_id}", summary="Batch progress + per-fund status")
def get_sfdr_batch(batch_id: str, session: DbSession, org_id: OrgId):
    owner = session.execute(text("SELECT org_id::text FROM sfdr_batch_runs WHERE batch_id=:b"), {"b": batch_id}).scalar()
    if not owner:
        return {"error": "batch not found"}
    if owner != org_id:
        return {"error": "forbidden"}
    return batch_status(session, batch_id)


@router.get("/voluntary-pai/catalog", summary="Selectable additional (voluntary) PAI indicators — RTS Tables 2 & 3")
def voluntary_pai_catalog():
    return {"indicators": voluntary_catalog()}


class VendorIngest(BaseModel):
    profile: str = "msci"                       # msci / iss / custom (with mapping)
    mapping: Optional[dict] = None              # our_field -> vendor column (overrides profile)
    reporting_year: Optional[int] = None
    rows: list[dict]                            # the vendor extract, one dict per issuer row


@router.get("/vendor/profiles", summary="Built-in vendor feed mapping profiles (MSCI/ISS/…)")
def vendor_profiles():
    return {"profiles": {k: v for k, v in _VENDOR_PROFILES.items()}}


@router.post("/vendor/ingest", summary="Ingest a vendor ESG/PAI extract and reconcile against our reference layer")
def vendor_ingest(body: VendorIngest, session: DbSession, org_id: OrgId):
    """Map a vendor's columns to our fields, match rows to issuers by ISIN/LEI, and
    store as source='vendor' (own > vendor > global precedence). Honest reconciliation."""
    if not body.rows:
        return {"error": "no rows supplied"}
    return ingest_vendor_extract(session, org_id, body.rows, profile=body.profile,
                                 mapping=body.mapping, reporting_year=body.reporting_year)


class VoluntaryPaiSelection(BaseModel):
    indicator_keys: list[str]       # the additional indicators the fund adopts


@router.put("/funds/{fund_id}/voluntary-pai", summary="Set the additional PAI indicators a fund adopts (≥1 env + ≥1 social)")
def set_voluntary_pai(fund_id: str, body: VoluntaryPaiSelection, session: DbSession, org_id: OrgId):
    err = _fund_owned_or_error(session, fund_id, org_id)
    if err:
        return {"error": err}
    bad = validate_keys(body.indicator_keys)
    if bad:
        return {"error": f"unknown indicator keys: {bad}", "catalog": list(_VOLUNTARY_CATALOG)}
    session.execute(text("DELETE FROM fund_voluntary_pai WHERE fund_id = :f"), {"f": fund_id})
    for key in dict.fromkeys(body.indicator_keys):   # de-dup, preserve order
        session.execute(text("""
            INSERT INTO fund_voluntary_pai (fund_id, org_id, indicator_key) VALUES (:f, :o, :k)
        """), {"f": fund_id, "o": org_id, "k": key})
    kinds = {_VOLUNTARY_CATALOG[k]["kind"] for k in body.indicator_keys}
    return {
        "fund_id": fund_id, "selected": body.indicator_keys,
        "adoption_compliant": "environmental" in kinds and "social" in kinds,
        "note": "Adopted. Supply per-issuer values (voluntary_pai on the holding upload) to populate the roll-up.",
    }


class LookThroughBody(BaseModel):
    isin: str                       # the held fund/ETF to expand
    constituents: list[Holding]     # its underlying holdings


@router.post("/funds/{fund_id}/look-through", summary="Expand a held fund/ETF to its constituents (look-through)")
def expand_look_through(fund_id: str, body: LookThroughBody, session: DbSession, org_id: OrgId):
    """Replace a held fund/ETF position with a sub-fund holding its constituents,
    so the underlying issuers flow into the PAI (no double-count — the wrapper
    position is removed, constituent values are scaled to preserve total exposure)."""
    err = _fund_owned_or_error(session, fund_id, org_id)
    if err:
        return {"error": err}
    isin = (body.isin or "").strip().upper()
    pos = session.execute(text("""
        SELECT p.position_id::text AS pid, CAST(p.market_value_eur AS FLOAT) AS mv, p.as_of_date,
               sec.name AS sec_name
        FROM fund_positions p JOIN securities sec ON sec.security_id = p.security_id
        WHERE p.fund_id = :f AND sec.isin = :i
          AND p.as_of_date = (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = :f)
    """), {"f": fund_id, "i": isin}).mappings().first()
    if not pos:
        return {"error": f"{isin} is not a current holding of this fund"}
    if not body.constituents:
        return {"error": "no constituents supplied"}

    wrapper_value = pos["mv"]
    # Scale constituents so their values sum to the wrapper's value (preserve exposure).
    supplied_total = sum(c.market_value_eur for c in body.constituents) or 1.0
    scale = wrapper_value / supplied_total
    scaled = [c.model_copy(update={"market_value_eur": round(c.market_value_eur * scale, 2)}) for c in body.constituents]

    # A sub-fund under this fund holds the constituents; the engine rolls it up.
    child_id = str(session.execute(text("""
        INSERT INTO funds (org_id, name, fund_type, parent_fund_id, base_currency)
        VALUES (:o, :n, 'sub_portfolio', :parent, 'EUR') RETURNING fund_id
    """), {"o": org_id, "n": f"{pos['sec_name']} — look-through", "parent": fund_id}).scalar())

    r = onboard_holdings(child_id, HoldingsUpload(as_of_date=pos["as_of_date"], holdings=scaled), session, org_id)
    # Remove the wrapper position from the parent — its exposure now lives in the sub-fund.
    session.execute(text("DELETE FROM fund_positions WHERE position_id = :p"), {"p": pos["pid"]})

    return {
        "expanded_isin": isin, "wrapper_value_eur": round(wrapper_value),
        "sub_fund_id": child_id, "constituents_onboarded": r.get("positions_created", 0),
        "coverage": r.get("coverage"),
        "note": "Wrapper replaced by a look-through sub-fund; its constituents now flow into the fund's PAI.",
    }


def _fund_owned_or_error(session, fund_id: str, org_id: str):
    owner = session.execute(text("SELECT org_id::text FROM funds WHERE fund_id = :f"), {"f": fund_id}).scalar()
    if not owner:
        return "not found"
    if owner != org_id:
        return "forbidden"
    return None


@router.get("/funds/{fund_id}/sfdr-statement", summary="SFDR PAI statement — the filing, as structured JSON")
def sfdr_statement(fund_id: str, session: DbSession, org_id: OrgId):
    err = _fund_owned_or_error(session, fund_id, org_id)
    if err:
        return {"error": err}
    return sfdr_pai_statement(session, fund_id)


@router.get("/funds/{fund_id}/sfdr-statement.xlsx", summary="Download the SFDR PAI statement as a filing-shaped .xlsx")
def sfdr_statement_xlsx(fund_id: str, session: DbSession, org_id: OrgId):
    err = _fund_owned_or_error(session, fund_id, org_id)
    if err:
        return {"error": err}
    statement = sfdr_pai_statement(session, fund_id)
    if statement.get("error"):
        return statement
    buf = sfdr_pai_statement_xlsx(statement)
    fname = f"SFDR_PAI_Statement_{statement['entity']['fund_name'].replace(' ', '_')}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/funds/{fund_id}/sfdr-statement.xbrl", summary="Download the SFDR PAI statement as a machine-readable XBRL instance")
def sfdr_statement_xbrl(fund_id: str, session: DbSession, org_id: OrgId):
    err = _fund_owned_or_error(session, fund_id, org_id)
    if err:
        return {"error": err}
    statement = sfdr_pai_statement(session, fund_id)
    if statement.get("error"):
        return statement
    xml = sfdr_pai_xbrl(statement)
    fname = f"SFDR_PAI_{statement['entity']['fund_name'].replace(' ', '_')}.xbrl"
    return StreamingResponse(
        iter([xml]), media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/entity/sfdr-statement.xbrl", summary="Entity-level SFDR PAI statement as a machine-readable XBRL instance")
def entity_statement_xbrl(session: DbSession, org_id: OrgId):
    statement = entity_pai_statement(session, org_id)
    if statement.get("error"):
        return statement
    xml = sfdr_pai_xbrl(statement)
    fname = f"SFDR_PAI_Entity_{statement['entity']['manager'].replace(' ', '_')}.xbrl"
    return StreamingResponse(
        iter([xml]), media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


class FilingProfile(BaseModel):
    lei: str
    legal_name: Optional[str] = None
    filing_contact_email: Optional[str] = None
    narratives: Optional[dict] = None   # {policies, actions, engagement, standards}


@router.get("/manager/filing-profile", summary="The manager's SFDR filing-entity identity")
def get_filing_profile(session: DbSession, org_id: OrgId):
    row = session.execute(text(
        "SELECT name, legal_name, lei, filing_contact_email, country, sfdr_narratives "
        "FROM organizations WHERE org_id = :o"), {"o": org_id}).mappings().first()
    return dict(row) if row else {"error": "org not found"}


@router.put("/manager/filing-profile", summary="Set the manager LEI + legal name + contact (LEI validated vs GLEIF)")
def set_filing_profile(body: FilingProfile, session: DbSession, org_id: OrgId):
    lei = (body.lei or "").strip().upper()
    rec = gleif.fetch_lei(lei) if len(lei) == 20 else None
    if not rec:
        return {"error": "invalid_lei", "detail": "LEI not found in GLEIF — supply a valid 20-character LEI"}
    # Default the legal name to GLEIF's authoritative name if the caller didn't give one.
    import json as _json
    session.execute(text("""
        UPDATE organizations SET lei = :lei,
               legal_name = COALESCE(:legal_name, :gleif_name),
               filing_contact_email = COALESCE(:email, filing_contact_email),
               sfdr_narratives = COALESCE(CAST(:narr AS jsonb), sfdr_narratives),
               updated_at = now()
        WHERE org_id = :o
    """), {"lei": lei, "legal_name": body.legal_name, "gleif_name": rec.name,
           "email": body.filing_contact_email,
           "narr": _json.dumps(body.narratives) if body.narratives is not None else None, "o": org_id})
    return {"ok": True, "lei": lei, "validated_name": rec.name,
            "lei_status": rec.entity_status, "domicile": rec.country}


@router.put("/funds/{fund_id}/lei", summary="Set a fund's own LEI (optional; validated vs GLEIF)")
def set_fund_lei(fund_id: str, body: FilingProfile, session: DbSession, org_id: OrgId):
    err = _fund_owned_or_error(session, fund_id, org_id)
    if err:
        return {"error": err}
    lei = (body.lei or "").strip().upper()
    rec = gleif.fetch_lei(lei) if len(lei) == 20 else None
    if not rec:
        return {"error": "invalid_lei", "detail": "LEI not found in GLEIF"}
    session.execute(text("UPDATE funds SET lei = :lei, updated_at = now() WHERE fund_id = :f"),
                    {"lei": lei, "f": fund_id})
    return {"ok": True, "lei": lei, "validated_name": rec.name}


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
    # Org-scoped: show THIS org's own disclosure or the global fallback — never
    # another tenant's private (source='client') emissions for the same issuer.
    emissions = session.execute(text("""
        SELECT reporting_year, CAST(scope1_tco2e AS FLOAT) AS scope1, CAST(scope2_tco2e AS FLOAT) AS scope2,
               CAST(scope3_tco2e AS FLOAT) AS scope3, CAST(revenue_eur AS FLOAT) AS revenue_eur, source
        FROM issuer_emissions WHERE issuer_id = :i AND (org_id = :o OR org_id IS NULL)
        ORDER BY (org_id IS NULL), reporting_year DESC LIMIT 1
    """), {"i": issuer_id, "o": org_id}).mappings().first()

    return {
        "issuer": dict(issuer),
        "physical": phys,
        "transition": trans,
        "emissions": dict(emissions) if emissions else None,
        "facilities": [{**dict(f), "scores": by_fac.get(f["facility_id"], [])} for f in facilities],
    }

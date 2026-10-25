"""Fund & issuer endpoints — the asset-manager product's read API.

Exposes the securities-book model (funds -> positions -> securities -> issuers ->
facilities) and its two risk surfaces (physical footprint + transition), plus
the fund-level SFDR PAI output. Distinct from /v1/assetmgmt (the old flat
located-holding vertical); this is the new issuer/footprint/fund model.

Tenant scoping mirrors the other verticals: a user JWT's org wins; an anonymous
caller only ever sees the demo asset-manager org (never an arbitrary org_id).
"""
from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, attachment, own_or_404, require_permission, tenant_resolver
from core import messages
from core.errors import UserError
from ml.regulatory.sfdr_pai import (
    entity_narratives,
    entity_pai_statement,
    frozen_or_live_statement,
    sfdr_pai_statement,
    sfdr_pai_statement_xlsx,
)
from ml.regulatory.voluntary_pai import CATALOG as _VOLUNTARY_CATALOG
from ml.regulatory.voluntary_pai import catalog as voluntary_catalog
from ml.regulatory.voluntary_pai import validate_keys
from services import fund_messages as W
from services.asset_manager_engine import (
    fund_positions_with_risk,
    issuer_physical_scores,
    issuer_transition,
)
from services.fund_disclosure import fund_climate_summary
from services.funds import registry
from services.funds.holding import (  # noqa: F401 — Holding: the look-through's line
    Holding,
    HoldingsUpload,
)
from services.funds.onboarding import onboard
from services.money.params import for_org
from services.reference.vendor_ingest import PROFILES as _VENDOR_PROFILES
from services.reference.vendor_ingest import ingest_vendor_extract
from services.sfdr_batch import batch_status, create_batch, run_batch

router = APIRouter(prefix="/v1", tags=["Asset Management — Funds"])

DEMO_ORG = "44444444-4444-4444-8444-444444444444"  # Nordkap Asset Management (demo)
_bearer = HTTPBearer(auto_error=False)


resolve_org = tenant_resolver(DEMO_ORG)             # one implementation for every sector API (api/deps.py)


OrgId = Annotated[str, Depends(resolve_org)]


def _writer_org(ctx: dict = Depends(require_permission("approvals.create"))) -> str:
    """A change to fund data needs a signed-in preparer; anonymous demo access is read-only (error log E24)."""
    return ctx["org"]["org_id"]


WriterOrgId = Annotated[str, Depends(_writer_org)]


@router.get("/funds", summary="List the org's funds with a headline risk summary")
def list_funds(session: DbSession, org_id: OrgId,
               scenario: str = Query("baseline"), horizon: str = Query("current")):
    funds = session.execute(text("""
        SELECT f.fund_id::text AS fund_id, f.name, f.fund_type, f.sfdr_classification,
               f.parent_fund_id::text AS parent_fund_id
        FROM funds f WHERE f.org_id = :o AND f.parent_fund_id IS NULL
        ORDER BY f.name
    """), {"o": org_id}).mappings().all()
    method = for_org(session, org_id)
    out = []
    for f in funds:
        summ = fund_climate_summary(session, org_id, method, f["fund_id"], scenario, horizon)
        out.append({
            **dict(f),
            "total_value_eur": summ.get("total_value_eur", 0),
            "base": summ.get("base"),
            "positions": summ.get("positions", 0),
            "physical_score": summ.get("physical", {}).get("value_weighted_score"),
            "transition_score": summ.get("transition", {}).get("value_weighted_score"),
            "waci": summ.get("pai", {}).get("pai", {}).get("pai_3_waci_tco2e_per_meur"),
        })
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon, "funds": out}


class FundCreate(BaseModel):
    """A fund as the manager states it (E144): its name, what it is, the SFDR article it discloses under (Regulation
    (EU) 2019/2088 Art. 6, 8 or 9 — the manager's classification, never defaulted), its base currency (ISO 4217); a
    sub-portfolio names the fund it belongs to; a fund LEI is optional and verified against GLEIF like every LEI."""
    name: str = Field(..., min_length=2, max_length=200)
    fund_type: str = Field(..., pattern="^(fund|sub_portfolio|mandate|fund_of_funds)$")
    sfdr_classification: str = Field(..., pattern="^article_(6|8|9)$")
    base_currency: str = Field(..., min_length=3, max_length=3)
    parent_fund_id: Optional[UUID] = None
    lei: Optional[str] = Field(None, max_length=20)


@router.post("/funds", status_code=201, summary="Create a fund (name, type, SFDR article, base currency)")
def create_fund(body: FundCreate, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    org_id = ctx["org"]["org_id"]
    if body.parent_fund_id:
        own_or_404(session, "funds", "fund_id", str(body.parent_fund_id), org_id, "Parent fund")
    fund = registry.check(session, org_id, name=body.name, fund_type=body.fund_type,
                          sfdr_classification=body.sfdr_classification, base_currency=body.base_currency,
                          parent_fund_id=str(body.parent_fund_id) if body.parent_fund_id else None, lei=body.lei)
    fid = registry.create(session, org_id, fund, actor_id=ctx["user"]["id"])
    return {"fund_id": fid, **{k: fund[k] for k in ("name", "fund_type", "sfdr_classification", "base_currency",
                                                     "parent_fund_id", "lei")}}


@router.get("/funds/{fund_id}", summary="Fund climate report — physical + transition + SFDR PAI")
def fund_detail(fund_id: str, session: DbSession, org_id: OrgId,
                scenario: str = Query("baseline"), horizon: str = Query("current")):
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    return fund_climate_summary(session, org_id, for_org(session, org_id), fund_id, scenario, horizon)


@router.get("/funds/{fund_id}/positions", summary="Fund positions, each with issuer physical + transition risk")
def fund_positions(fund_id: str, session: DbSession, org_id: OrgId,
                   scenario: str = Query("baseline"), horizon: str = Query("current")):
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    positions = fund_positions_with_risk(session, org_id, for_org(session, org_id), fund_id, scenario, horizon)
    positions.sort(key=lambda p: -(p["physical"]["headline_score"] or 0))
    return {"fund_id": fund_id, "scenario": scenario, "horizon": horizon, "positions": positions}


@router.get("/funds/{fund_id}/loss-lookthrough",
            summary="Each holding's yearly loss looked through to its issuer's sites: the share of the issuer's physical "
                    "value lost (tested damage curves only) and euros on the holding — or why not")
def fund_loss_lookthrough(fund_id: str, session: DbSession, org_id: OrgId):
    """The holdings look-through (services.loss.lookthrough; the product owner's decisions of 2026-10-22), today's
    climate: every message in customer words (its label and the detail behind its ⓘ)."""
    from services.asset_manager_engine import fund_descendant_ids
    from services.loss.lookthrough import holdings
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    out = holdings(session, org_id, fund_descendant_ids(session, fund_id))
    return {"fund_id": fund_id, **out,
            "accepted_bases": [{"basis": b, "name": messages.name("lookthrough.basis", b)} for b in out["accepted_bases"]],
            "headline": out["headline"] and messages.name("loss.flood_lead", out["headline"])}


# A holding by ISIN, the book as received, and the issuer data a holding states: services/funds/holding.py (one
# definition for the API and the standard file).



_HOLDINGS_TEMPLATE = (
    "# Tellumen holdings template — one holding per row.\n"
    "# Value the line EITHER in EUR (market_value_eur) OR in its native currency\n"
    "#   (market_value + currency, e.g. 5000000 + USD — we convert to EUR at the ECB\n"
    "#   rate for the book's as-of date). Give one or the other, not both.\n"
    "# Optional (fill what you already hold — it fills the SFDR statement):\n"
    "#   nace_code (EU industry code), revenue_eur, scope1_tco2e, scope2_tco2e, scope3_tco2e,\n"
    "#   evic_eur (enterprise value incl. cash — unlocks financed emissions, PAI 1/2), asset_class, reporting_year.\n"
    "#   Company energy (PAI 5/6 — else Tellumen estimates from EU sector / country averages, flagged): energy_consumption_gwh,\n"
    "#   non_renewable_consumption_pct, non_renewable_production_pct (energy producers), energy_intensity_gwh_per_meur.\n"
    "#   Issuer financials in another currency: revenue / evic + financials_currency (+ financials_date, else 31 Dec\n"
    "#   of reporting_year) — revenue converts at the 12-month average, EVIC at that date's rate.\n"
    "#   physical_asset_value_eur (or physical_asset_value + financials_currency): the issuer's buildings, plant,\n"
    "#   machinery and contents, land excluded — unlocks the yearly loss in euros on the holding.\n"
    "# Leave any optional cell blank; blanks are surfaced as gaps, never guessed. Delete these comment rows before use.\n"
    "isin,market_value_eur,market_value,currency,nace_code,revenue_eur,scope1_tco2e,scope2_tco2e,scope3_tco2e,evic_eur,asset_class,reporting_year,revenue,evic,financials_currency,financials_date,energy_consumption_gwh,non_renewable_consumption_pct,non_renewable_production_pct,physical_asset_value_eur,physical_asset_value\n"
    "US0378331005,5000000,,,26.20,,55000,0,16200000,,equity,2023,383000000000,2900000000000,USD,2023-09-30,3200,,,,\n"
    "DE0007164600,4000000,,,62.01,31200000000,30000,45000,4300000,210000000000,equity,2023,,,,,410,62,,,\n"
    "US5949181045,,6000000,USD,62.01,,290000,110000,13800000,,equity,2023,211900000000,2700000000000,USD,2023-06-30,,,,,\n"
    "CH0038863350,3500000,,,,,,,,,equity,,,,,,,,,,\n"
)


@router.get("/holdings/template.csv", summary="Download a holdings template a manager fills with their book")
def holdings_template():
    return StreamingResponse(
        iter([_HOLDINGS_TEMPLATE]), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="tellumen_holdings_template.csv"'})


def _actor_id(ctx: dict = Depends(require_permission("approvals.create"))) -> str:
    """The signed-in preparer, for the audit of what an upload removes."""
    return ctx["user"]["id"]


@router.post("/funds/{fund_id}/holdings", summary="Onboard holdings by ISIN — resolve, locate, and value-weight into the fund")
def onboard_holdings(fund_id: str, body: HoldingsUpload, session: DbSession, org_id: WriterOrgId,
                     actor_id: Annotated[Optional[str], Depends(_actor_id)] = None):
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
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    return onboard(session, org_id, fund_id, body, actor_id)


@router.post("/funds/{fund_id}/sfdr-statement/file", summary="Freeze the fund's PAI analytics as its record for a reference year (not a filing)")
def file_sfdr_statement(fund_id: str, session: DbSession, org_id: WriterOrgId):
    """Keep the fund's PAI analytics as its record for the reference year, so next year's analytics can compare with
    it. Not a filing (a fund's analytics, not a filing: the principal adverse impacts statement is the manager's entity-level statement (Delegated Regulation (EU) 2022/1288, Annex I, filed per reference period); a fund discloses how it considers principal adverse impacts in its SFDR product documents (Annexes II-V)). Freezing the same year again replaces the record."""
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    st = sfdr_pai_statement(session, fund_id)
    if st.get("error"):
        code, params = W.reason(st["error"])
        raise UserError(code, 409, **params)
    ref_year = st["summary"].get("reference_year")
    if not ref_year:
        raise UserError("disclose.fund.refused.no_reference_year")
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
            "filed": f"FY{ref_year} PAI analytics frozen as the record of {st['entity']['fund_name']} (not a filing)",
            "msg": messages.render("disclose.fund.frozen", year=ref_year)}


# The SFDR pre-contractual and periodic templates (Annexes II–V) are served item by item from the governing
# specification by api/routers/sfdr_documents.py and filed as report types sfdr_precontractual / sfdr_periodic.


@router.get("/funds/{fund_id}/sfdr-filings", summary="The years of this fund's PAI analytics frozen as records (not filings)")
def list_sfdr_filings(fund_id: str, session: DbSession, org_id: OrgId):
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    rows = session.execute(text("""
        SELECT reference_year, filed_at, filed_by, status FROM fund_sfdr_filings
        WHERE fund_id = :f ORDER BY reference_year DESC
    """), {"f": fund_id}).mappings().all()
    return {"fund_id": fund_id, "filings": [dict(r) for r in rows]}


@router.get("/entity/sfdr-statement", summary="Entity-level SFDR PAI statement — aggregated across ALL the manager's funds")
def entity_sfdr_statement(session: DbSession, org_id: OrgId, period_end: Optional[date] = Query(None)):
    """One PAI statement value-weighted across every fund the manager runs. With period_end (a 31 December): the
    statement for that reference period, impacts averaged over its four quarter ends (RTS 2022/1288 Art. 4(1), 6(3));
    without: a live view on the latest holdings."""
    from ml.regulatory.sfdr_pai_period import PeriodError
    try:
        return entity_pai_statement(session, org_id, period_end)
    except PeriodError as e:
        raise UserError("disclose.pai.refused.period", date=str(period_end)) from e


def _statement_period(session, org_id: str, period_end: Optional[date]) -> date:
    """The reference period asked for, else the one the organisation reports for (the last 31 December on or before
    its reporting period end)."""
    if period_end is not None:
        return period_end
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(session, org_id)
    return pe if (pe.month, pe.day) == (12, 31) else date(pe.year - 1, 12, 31)


@router.get("/entity/pai-statement/answers",
            summary="What the manager answers in its PAI statement for a reference period (RTS 2022/1288 Art. 5-10)")
def pai_statement_answers(session: DbSession, org_id: OrgId, period_end: Optional[date] = Query(None)):
    """The sections of the governing spec item by item (as the Regulation words them), the answers given for the period,
    every impact row with its previous-period figure, explanation and actions, the historical comparison, and what the
    Regulation still requires. Earlier answers not tied to any period are shown for reference, never used."""
    import services.regspec as R
    from ml.regulatory.sfdr_pai_period import PeriodError
    from services.governance import sfdr_pai_answers as A
    pe = _statement_period(session, org_id, period_end)
    try:
        st = entity_pai_statement(session, org_id, pe)
    except PeriodError as e:
        raise UserError("disclose.pai.refused.period", date=str(period_end)) from e
    if st.get("error"):
        code, params = W.reason(st["error"])
        raise UserError(code, 409, **params)
    spec = R.governing(A.FAMILY, period_end=pe)
    sections = [{"id": sid, "title": R.template(spec, sid)["title"], "ref": R.template(spec, sid)["ref"],
                 "items": [{**i, "binding": A.SECTION_BINDING[sid].get(i["id"])} for i in R.template(spec, sid)["items"]]}
                for sid in A.SECTIONS]
    legacy = entity_narratives(session, org_id)
    return {
        "period_end": pe.isoformat(), "reference_period": st["reference_period"],
        "spec": {"version": spec["version"], "sha256": spec["_sha256"]},
        "sections": sections, "computed": st["sections"]["computed"], "answers": st["sections"]["answers"],
        "rows": [{**r, **st["rows"].get(r["key"], {})} for r in A.impact_rows(st)],
        "prior_period": st["prior_period"], "historical_comparison": st["historical_comparison"],
        "missing": st["filing_readiness"]["missing"], "ready_to_file": st["filing_readiness"]["ready_to_file"],
        "gaps": W.statement_view(st)["readiness"],         # what is missing, as messages (services.fund_messages)
        "prior_source": W.source(st["prior_period"]),
        "legacy_narratives": legacy or None,
    }


class PaiAnswers(BaseModel):
    period_end: date
    answers: dict


@router.put("/entity/pai-statement/answers",
            summary="Answer items of the PAI statement for a reference period (an item set to null is cleared)")
def save_pai_statement_answers(body: PaiAnswers, session: DbSession,
                               ctx: dict = Depends(require_permission("approvals.create"))):
    from api.services.rbac import write_audit
    from ml.regulatory.sfdr_pai_period import PeriodError
    from services.governance import sfdr_pai_answers as A
    org_id = ctx["org"]["org_id"]
    try:
        out = A.save(session, org_id, body.period_end, body.answers, ctx["user"]["id"])
    except PeriodError as e:
        raise UserError("disclose.pai.refused.period", date=body.period_end.isoformat()) from e
    except A.AnswerError as e:
        if e.code:
            raise UserError(e.code, 409, **e.params) from e
        raise UserError("filing.gap.sfdr_unavailable", 409) from e
    if out["refused"]:                  # all or nothing: the error rolls back the answers stored before the refusal
        first = out["refused"][0]
        raise UserError("disclose.answers.refused_all", n=len(out["refused"]), first=first["msg"]["label"])
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="sfdr_pai.answers_saved",
                target_type="template_answers", target_id=f"sfdr_pai/pai_statement/{body.period_end.isoformat()}",
                detail={"items": out["saved"]})
    session.commit()
    return out


class BatchCreate(BaseModel):
    reference_year: int = Field(..., ge=2000, le=2100)
    run: bool = True                 # generate immediately (else create pending only)
    limit: Optional[int] = None      # cap funds processed this call (chunked runs)


@router.post("/entity/sfdr-batch", summary="Compute every fund's PAI analytics (resumable batch) — analytics, not filings")
def create_sfdr_batch(body: BatchCreate, session: DbSession, org_id: WriterOrgId):
    batch_id = create_batch(session, org_id, body.reference_year)
    if body.run:
        return run_batch(session, batch_id, limit=body.limit)
    return batch_status(session, batch_id)


@router.post("/entity/sfdr-batch/{batch_id}/run", summary="Resume a batch — process the funds still pending/errored")
def resume_sfdr_batch(batch_id: str, session: DbSession, org_id: WriterOrgId,
                      limit: Optional[int] = Query(None)):
    own_or_404(session, "sfdr_batch_runs", "batch_id", batch_id, org_id, "Batch")
    return run_batch(session, batch_id, limit=limit)


@router.get("/entity/sfdr-batch/{batch_id}", summary="Batch progress + per-fund status")
def get_sfdr_batch(batch_id: str, session: DbSession, org_id: OrgId):
    own_or_404(session, "sfdr_batch_runs", "batch_id", batch_id, org_id, "Batch")
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
def vendor_ingest(body: VendorIngest, session: DbSession, org_id: WriterOrgId):
    """Map a vendor's columns to our fields, match rows to issuers by ISIN/LEI, and
    store as source='vendor' (own > vendor > global precedence). Honest reconciliation."""
    if not body.rows:
        raise UserError("disclose.fund.refused.no_rows")
    return ingest_vendor_extract(session, org_id, body.rows, profile=body.profile,
                                 mapping=body.mapping, reporting_year=body.reporting_year)


class VoluntaryPaiSelection(BaseModel):
    indicator_keys: list[str]       # the additional indicators the fund adopts


@router.put("/funds/{fund_id}/voluntary-pai", summary="Set the additional PAI indicators a fund adopts (≥1 env + ≥1 social)")
def set_voluntary_pai(fund_id: str, body: VoluntaryPaiSelection, session: DbSession, org_id: WriterOrgId):
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    bad = validate_keys(body.indicator_keys)
    if bad:
        raise UserError("disclose.fund.refused.indicator", n=len(bad))
    session.execute(text("DELETE FROM fund_voluntary_pai WHERE fund_id = :f"), {"f": fund_id})
    for key in dict.fromkeys(body.indicator_keys):   # de-dup, preserve order
        session.execute(text("""
            INSERT INTO fund_voluntary_pai (fund_id, org_id, indicator_key) VALUES (:f, :o, :k)
        """), {"f": fund_id, "o": org_id, "k": key})
    kinds = {_VOLUNTARY_CATALOG[k]["kind"] for k in body.indicator_keys}
    return {
        "fund_id": fund_id, "selected": body.indicator_keys,
        "adoption_compliant": "environmental" in kinds and "social" in kinds,
        "note": "Adopted. Add each investee's values for these indicators to the holdings upload to fill the roll-up.",
        "msg": messages.render("disclose.fund.voluntary.saved", n=len(dict.fromkeys(body.indicator_keys))),
    }


class LookThroughBody(BaseModel):
    isin: str                       # the held fund/ETF to expand
    constituents: list[Holding]     # its underlying holdings


@router.post("/funds/{fund_id}/look-through", summary="Expand a held fund/ETF to its constituents (look-through)")
def expand_look_through(fund_id: str, body: LookThroughBody, session: DbSession, org_id: WriterOrgId):
    """Replace a held fund/ETF position with a sub-fund holding its constituents,
    so the underlying issuers flow into the PAI (no double-count — the wrapper
    position is removed, constituent values are scaled to preserve total exposure)."""
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    isin = (body.isin or "").strip().upper()
    pos = session.execute(text("""
        SELECT p.position_id::text AS pid, CAST(p.market_value_eur AS FLOAT) AS mv, p.as_of_date,
               sec.name AS sec_name
        FROM fund_positions p JOIN securities sec ON sec.security_id = p.security_id
        WHERE p.fund_id = :f AND sec.isin = :i
          AND p.as_of_date = (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = :f)
    """), {"f": fund_id, "i": isin}).mappings().first()
    if not pos:
        raise UserError("disclose.fund.refused.not_held", isin=isin)
    if not body.constituents:
        raise UserError("disclose.fund.refused.no_constituents")

    wrapper_value = pos["mv"]
    # Scale constituents so their values sum to the wrapper's value (preserve exposure).
    supplied_total = sum(c.market_value_eur for c in body.constituents) or 1.0
    scale = wrapper_value / supplied_total
    scaled = [c.model_copy(update={"market_value_eur": round(c.market_value_eur * scale, 2)}) for c in body.constituents]

    # A sub-fund under this fund holds the constituents; the engine rolls it up. Inherit the parent's SFDR
    # classification + base currency (2026-09-24 fix, platform E2E audit finding #8: this used to hardcode
    # 'EUR' and drop sfdr_classification entirely — a look-through sub-fund of a non-EUR or Art. 8/9 parent
    # would silently lose both, same bug the now-removed duplicate /lookthrough endpoint didn't have).
    parent = session.execute(text("SELECT sfdr_classification, base_currency FROM funds WHERE fund_id = :f"),
                             {"f": fund_id}).mappings().first()
    child_id = str(session.execute(text("""
        INSERT INTO funds (org_id, name, fund_type, parent_fund_id, sfdr_classification, base_currency)
        VALUES (:o, :n, 'sub_portfolio', :parent, :cls, :ccy) RETURNING fund_id
    """), {"o": org_id, "n": f"{pos['sec_name']} — look-through", "parent": fund_id,
           "cls": parent["sfdr_classification"], "ccy": parent["base_currency"] or "EUR"}).scalar())

    r = onboard_holdings(child_id, HoldingsUpload(as_of_date=pos["as_of_date"], holdings=scaled), session, org_id)
    # Remove the wrapper position from the parent — its exposure now lives in the sub-fund.
    session.execute(text("DELETE FROM fund_positions WHERE position_id = :p"), {"p": pos["pid"]})

    return {
        "expanded_isin": isin, "wrapper_value_eur": round(wrapper_value),
        "sub_fund_id": child_id, "constituents_onboarded": r.get("positions_created", 0),
        "coverage": r.get("coverage"),
        "note": "Wrapper replaced by a look-through sub-fund; its constituents now flow into the fund's PAI.",
    }


@router.get("/funds/{fund_id}/sfdr-statement", summary="A fund's PAI analytics — the frozen record for the current year if one exists, else live (not a filing)")
def sfdr_statement(fund_id: str, session: DbSession, org_id: OrgId):
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    statement, is_frozen = frozen_or_live_statement(session, fund_id)
    if not statement.get("error"):
        statement["filing_status"] = "filed" if is_frozen else "draft_not_yet_filed"
    statement["view"] = W.statement_view(statement)        # its words for the screen (services.fund_messages)
    return statement


@router.get("/funds/{fund_id}/sfdr-statement.xlsx", summary="Download a fund's PAI analytics as .xlsx (not a filing)")
def sfdr_statement_xlsx(fund_id: str, session: DbSession, org_id: OrgId):
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    # Fixed 2026-09-24 (E2E audit): this used to recompute live on every request, so a downloaded export
    # could silently drift from what was actually filed — reads the FROZEN record now, same discipline as
    # services/governance/filing_export.py. is_frozen=False only for a fund that hasn't filed yet (a
    # legitimate draft preview), stamped in the filename so it's never mistaken for the official filing.
    statement, is_frozen = frozen_or_live_statement(session, fund_id)
    if statement.get("error"):
        return statement
    buf = sfdr_pai_statement_xlsx(statement)
    suffix = "" if is_frozen else "_DRAFT_not_yet_filed"
    fname = f"SFDR_PAI_Statement_{statement['entity']['fund_name'].replace(' ', '_')}{suffix}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": attachment(fname)})


# SFDR PAI (i)XBRL retired (E113): the instance was written under a Tellumen-made namespace, and no official SFDR PAI
# taxonomy is held — an XBRL file under element names we invented is not a regulatory export. The statement
# downloads as a workbook (.xlsx, RTS Table 1 columns) and a filing exports JSON / xlsx. The routes answer 410 with the reason.
_SFDR_XBRL_RETIRED = ("Retired: no official SFDR PAI XBRL taxonomy is held, and an instance under Tellumen-made "
                      "element names is not a filing. Download the statement as .xlsx, or export the filing as JSON / xlsx.")


def _sfdr_xbrl_retired():
    raise UserError("disclose.fund.refused.xbrl_retired", 410)


@router.get("/funds/{fund_id}/sfdr-statement.xbrl", summary="Retired — SFDR PAI XBRL", description=_SFDR_XBRL_RETIRED,
            status_code=410)
def sfdr_statement_xbrl(fund_id: str):
    _sfdr_xbrl_retired()


@router.get("/funds/{fund_id}/sfdr-statement.ixbrl", summary="Retired — SFDR PAI Inline XBRL", description=_SFDR_XBRL_RETIRED,
            status_code=410)
def sfdr_statement_ixbrl(fund_id: str):
    _sfdr_xbrl_retired()


@router.get("/entity/sfdr-statement.xbrl", summary="Retired — entity-level SFDR PAI XBRL", description=_SFDR_XBRL_RETIRED,
            status_code=410)
def entity_statement_xbrl():
    _sfdr_xbrl_retired()


class FilingProfile(BaseModel):
    lei: str
    legal_name: Optional[str] = None
    filing_contact_email: Optional[str] = None
    narratives: Optional[dict] = None   # retired: the statement's answers are per reference period (/entity/pai-statement/answers)


@router.get("/manager/filing-profile", summary="The manager's SFDR filing-entity identity")
def get_filing_profile(session: DbSession, org_id: OrgId):
    row = session.execute(text(
        "SELECT name, legal_name, lei, filing_contact_email, country "
        "FROM organizations WHERE org_id = :o"), {"o": org_id}).mappings().first()
    if not row:
        raise UserError("error.not_found")
    return dict(row)


@router.put("/manager/filing-profile", summary="Set the manager LEI + legal name + contact (LEI validated vs GLEIF)")
def set_filing_profile(body: FilingProfile, session: DbSession,
                       ctx: dict = Depends(require_permission("approvals.create"))):
    org_id = ctx["org"]["org_id"]
    lei = (body.lei or "").strip().upper()
    rec = registry.verified_lei(lei)
    if body.narratives is not None:     # one set for every period answered nothing the Regulation asks, item by item
        raise UserError("disclose.fund.refused.narratives")
    # A legal name not given keeps the one on file for the same LEI; only a new LEI (or none on file) takes GLEIF's
    # name — a narratives save re-sends the LEI alone and must not overwrite the manager's legal name.
    session.execute(text("""
        UPDATE organizations SET lei = CAST(:lei AS varchar),
               legal_name = COALESCE(:legal_name, CASE WHEN lei = CAST(:lei AS varchar) THEN legal_name END, :gleif_name),
               filing_contact_email = COALESCE(:email, filing_contact_email),
               updated_at = now()
        WHERE org_id = :o
    """), {"lei": lei, "legal_name": body.legal_name, "gleif_name": rec.name,
           "email": body.filing_contact_email, "o": org_id})
    return {"ok": True, "lei": lei, "validated_name": rec.name,
            "lei_status": rec.entity_status, "domicile": rec.country}


@router.put("/funds/{fund_id}/lei", summary="Set a fund's own LEI (optional; validated vs GLEIF)")
def set_fund_lei(fund_id: str, body: FilingProfile, session: DbSession, org_id: WriterOrgId):
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    lei = (body.lei or "").strip().upper()
    rec = registry.verified_lei(lei)
    session.execute(text("UPDATE funds SET lei = :lei, updated_at = now() WHERE fund_id = :f"),
                    {"lei": lei, "f": fund_id})
    return {"ok": True, "lei": lei, "validated_name": rec.name}


class WithdrawBody(BaseModel):
    reason: str = Field(..., max_length=1000)


@router.post("/issuers/{issuer_id}/client-data/withdraw",
             summary="Withdraw the data your organisation stated about an issuer (audited, with the reason)")
def withdraw_issuer_data(issuer_id: UUID, body: WithdrawBody, session: DbSession,
                         ctx: dict = Depends(require_permission("approvals.create"))):
    from services import issuer_client_data as C
    try:
        return C.withdraw(session, ctx["org"]["org_id"], str(issuer_id), body.reason, ctx["user"]["id"])
    except C.WithdrawError as e:
        raise UserError(e.code, **e.params) from e


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
        raise UserError("disclose.fund.issuer_not_held")

    issuer = session.execute(text("""
        SELECT issuer_id::text AS issuer_id, lei, name, issuer_type, country, sector, nace_code
        FROM issuers WHERE issuer_id = :i
    """), {"i": issuer_id}).mappings().first()

    facilities = session.execute(text("""
        SELECT f.facility_id::text AS facility_id, f.name, f.facility_type, f.country, f.region,
               CAST(f.latitude AS FLOAT) AS lat, CAST(f.longitude AS FLOAT) AS lon, f.h3_cell,
               CAST(f.materiality_weight AS FLOAT) AS materiality_weight, f.weight_basis, f.source, f.match_basis,
               CAST(f.owner_share AS FLOAT) AS owner_share, f.site_facts
        FROM issuer_facilities f WHERE f.issuer_id = :i ORDER BY f.materiality_weight DESC, f.name
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
    trans = issuer_transition(session, org_id, for_org(session, org_id), scenario, horizon, [issuer_id]).get(issuer_id)
    # Org-scoped: show THIS org's own disclosure or the global fallback — never
    # another tenant's private (source='client') emissions for the same issuer.
    from services.issuer_figures import SOURCE_TIE
    emissions = session.execute(text(f"""
        SELECT reporting_year, CAST(scope1_tco2e AS FLOAT) AS scope1, CAST(scope2_tco2e AS FLOAT) AS scope2,
               CAST(scope3_tco2e AS FLOAT) AS scope3, CAST(revenue_eur AS FLOAT) AS revenue_eur, source
        FROM issuer_emissions WHERE issuer_id = :i AND (org_id = :o OR org_id IS NULL)
        ORDER BY (org_id IS NULL), reporting_year DESC, {SOURCE_TIE} LIMIT 1
    """), {"i": issuer_id, "o": org_id}).mappings().first()

    return {
        "issuer": dict(issuer),
        "physical": phys,
        "transition": trans,
        "emissions": dict(emissions) if emissions else None,
        "facilities": [{**dict(f), "scores": by_fac.get(f["facility_id"], [])} for f in facilities],
        "own_data": _own_issuer_data(session, org_id, issuer_id),   # what this organisation stated (withdrawable, E146)
    }


def _own_issuer_data(session, org_id: str, issuer_id: str) -> dict[str, int]:
    from services.issuer_client_data import held
    return {t: n for t, n in held(session, org_id, issuer_id).items() if n}

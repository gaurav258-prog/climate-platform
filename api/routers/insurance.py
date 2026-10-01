"""
Insurance underwriting — public read-only endpoints for the Loss-curve pricing
workspace.

Projects the golden source (canonical_scores) onto an insurer's property book
via the shared portfolio engine (services/portfolio_engine.py) and the unified
v_portfolio_entity_physical_risk view -- the same engine banking, real estate
and asset management use, so a fix or a new calc-settings trigger only needs
writing once (see the b9c0d1e2f3a4 migration's docstring for the duplication
this replaced). Each policy then runs through ml/scoring/insurance_pricing.py's
score -> scenario loss -> expected annual loss -> premium chain via an
extra_calc hook -- insurance's pricing/trigger block is its own genuinely
different calculation, layered on top of the shared fetch/join/headline logic,
same pattern as real estate's NOI impact. Policies whose cell is unscored
return status='no_canonical_score', premium withheld -- same governance rule
as every other hazard-projected book here.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import CurrentUser, DbSession, own_or_404, tenant_resolver
from api.services.rbac import write_audit
from core.types import HAZARD_VALUES
from ml.scoring.cat_accumulation import catastrophe_accumulation
from ml.scoring.insurance_pricing import price_perils
from ml.scoring.parametric_trigger import trigger_block
from services.calc_settings import get_calc_settings
from services.governance.ifrs_s2_incurred import (
    incurred_loss_summary,
    list_incurred_losses,
    submit_incurred_loss,
)
from services.governance.solvency2_natcat import natcat_scr
from services.ingest.templates import (  # noqa: F401 — re-exported
    CONSTRUCTION_TYPES,
    POLICY_TEMPLATE_FIELDS,
)
from services.money.params import for_org
from services.portfolio_engine import (
    at_risk_by,
    fetch_entities_with_risk,
    get_entity_org,
    get_entity_with_risk,
    value_at_risk,
)
from services.scoring.combined_var import combined_climate_var
from services.templates.workbook import build_export_workbook, build_template_workbook

router = APIRouter(prefix="/v1/insurance", tags=["Insurance"])

DEMO_ORG = "22222222-2222-4222-8222-222222222222"  # Iberia Mutual (demo)
_bearer = HTTPBearer(auto_error=False)


resolve_org = tenant_resolver(DEMO_ORG)             # one implementation for every sector API (api/deps.py)
OrgId = Annotated[str, Depends(resolve_org)]


EXT_INSURANCE_COLUMNS = [
    "CAST(x.deductible_pct AS FLOAT) AS deductible_pct",
    "CAST(x.building_value_eur AS FLOAT) AS building_value_eur",
    "CAST(x.contents_value_eur AS FLOAT) AS contents_value_eur",
    "CAST(x.business_interruption_value_eur AS FLOAT) AS business_interruption_value_eur",
    "e.postal_code AS postal_code",
    "CAST(x.motor_sum_insured_eur AS FLOAT) AS motor_sum_insured_eur",
]


def _insurance_extra(method, trigger_by_policy):
    """extra_calc hook: layers insurance's own pricing/trigger calc on top of the
    shared fetch/join/headline logic (real estate's NOI impact is the same
    pattern). hz is the FULL unfiltered hazard list (heat_acute included) --
    exactly what the parametric trigger needs, since a trigger can legitimately
    be configured against heat_acute even though it's excluded from the
    standing headline/pricing score. Pricing is on the undertaking's stated method for the year."""
    def calc(row, headline, hz):
        # every insured property peril at the location, priced on its own and summed (not only the headline hazard:
        # a headline that changes between scenarios must not drop a peril's loss — ml.scoring.insurance_pricing)
        pricing = price_perils(method, hz, row["primary_value_eur"], row.get("deductible_pct") or 0.0)
        cfg = trigger_by_policy.get(row["entity_id"])
        trigger = None
        if cfg:
            hz_score = next((h["score"] for h in hz if h["hazard"] == cfg["hazard_type"]), None)
            trigger = trigger_block(cfg["hazard_type"], hz_score, cfg["attachment_score"], cfg["exhaustion_score"],
                                     row["primary_value_eur"], cfg["updated_by"], cfg["updated_at"])
        return {"pricing": pricing, "trigger": trigger}
    return calc


def _map_policy_row(row):
    """Shared-engine row -> the exact shape /portfolio, /summary, /triggers
    have always returned (frontend relies on these exact field names)."""
    return {
        "policy_id": row["entity_id"], "policy_name": row["entity_name"], "policy_type": row["entity_type"],
        "country": row["country"], "region": row["region"], "lat": row["lat"], "lon": row["lon"],
        "h3_cell": row["h3_cell"], "sum_insured_eur": row["primary_value_eur"],
        "deductible_pct": row["deductible_pct"], "building_value_eur": row["building_value_eur"],
        "contents_value_eur": row["contents_value_eur"],
        "business_interruption_value_eur": row["business_interruption_value_eur"],
        "postal_code": row["postal_code"], "motor_sum_insured_eur": row["motor_sum_insured_eur"],
        "construction_type": row["construction_type"], "year_built": row["year_built"],
        "number_of_stories": row["number_of_stories"],
        "hazards": row["hazards"], "headline_score": row["headline_score"],
        "headline_bucket": row["headline_bucket"], "headline_hazard": row["headline_hazard"],
        "pricing": row["pricing"], "trigger": row["trigger"],
    }


def _policies_with_risk(session, org_id, scenario, horizon, *, method, entity_ids=None, value_weights=None,
                        translation=None):
    """All of an org's policies (metadata) + their per-hazard projected risk.
    Thin wrapper over the shared portfolio engine (services/portfolio_engine.py)
    -- the fetch/join/headline logic itself lives there, shared with banking,
    real estate and asset management. entity_ids / value_weights scope + weight
    the book for per-entity / consolidated filings."""
    trigger_rows = session.execute(text("""
        SELECT policy_id::text AS policy_id, hazard_type, CAST(attachment_score AS FLOAT) AS attachment_score,
               CAST(exhaustion_score AS FLOAT) AS exhaustion_score, updated_by::text AS updated_by, updated_at
        FROM insurance_policy_triggers WHERE policy_id IN (
            SELECT entity_id FROM portfolio_entities WHERE org_id = :o AND vertical = 'insurance'
        )
    """), {"o": org_id}).mappings().all()
    trigger_by_policy = {t["policy_id"]: dict(t) for t in trigger_rows}

    rows = fetch_entities_with_risk(session, org_id, "insurance", scenario, horizon, method=method,
                                     ext_table="ext_insurance", ext_columns=EXT_INSURANCE_COLUMNS,
                                     extra_calc=_insurance_extra(method, trigger_by_policy),
                                     entity_ids=entity_ids, value_weights=value_weights, translation=translation)
    return [_map_policy_row(r) for r in rows]


def standard_formula_inputs(session, org_id: str, translation=None, entity_id: str | None = None) -> dict:
    """What the Solvency II nat-cat standard formula takes besides the book, for the organisation's reporting date:
    the date (it selects the version of the Regulation), the ATTESTED reinsurance (the illustrative programme never
    mitigates a regulatory figure), the attested premiums and DIV for risks outside Annex XIII, and the governed UK
    reading. Amounts are stated in EUR and follow the book's presentation currency. entity_id: the undertaking (or the
    group's top entity) the book is for — its own attested figures; None = the organisation's."""
    from services.governance.reporting_settings import get_settings
    from services.insurer_capital import natcat_other_regions, programme
    pe = get_settings(session, org_id)["reporting_period_end"]
    ref = date.fromisoformat(str(pe)[:10]) if pe else date(date.today().year - 1, 12, 31)
    treaty, basis = programme(session, org_id, ref, entity_id)
    other = natcat_other_regions(session, org_id, ref, entity_id)
    if translation is not None and translation.presentation != "EUR":
        from services.governance.translation import from_eur
        treaty = {k: from_eur(session, translation, v) if k.endswith("_eur") and v is not None else v for k, v in treaty.items()}
        other = {p: {**x, "premium_eur": from_eur(session, translation, x["premium_eur"]) if x["premium_eur"] is not None else None}
                 for p, x in other.items()}
    return {"ref_date": ref, "treaty": treaty, "treaty_basis": basis, "other_inputs": other,
            "uk_reading": get_calc_settings(session, org_id)["sii_natcat_uk_other_regions"]}


def _scr_from_cat(cat: dict, policies: list, scenario: str, horizon: str, sf_inputs: dict) -> dict:
    """The nat-cat capital on two labelled bases: the prescribed STANDARD FORMULA (services.governance.solvency2_natcat,
    Delegated Regulation 2015/35 — always computed from the book and the attested inputs), and the platform's MODELLED
    1-in-200 annual loss from the catastrophe simulation on the undertaking's stated method — a modelled figure, not an
    approved internal model (Directive 2009/138/EC Art. 112), and a gap while the method is not stated."""
    sf_natcat = natcat_scr(policies, **sf_inputs)
    if not cat or not cat.get("available"):
        return {"available": False, "reason": (cat or {}).get("reason", "No scored policies in this book."),
                **({"gap": cat.get("gap")} if (cat or {}).get("gap") else {}), "standard_formula_natcat": sf_natcat}
    aep200 = (cat.get("aep_eur") or {}).get("rp_200")
    oep200 = (cat.get("oep_eur") or {}).get("rp_200")
    gross_si = sum(p["sum_insured_eur"] or 0 for p in policies if p.get("sum_insured_eur"))
    mean_al = cat.get("mean_annual_loss_eur")
    return {
        "available": True, "scenario": scenario, "horizon": horizon,
        "scr_basis": "modelled_1_in_200_stated_method",
        "modelled_1_in_200_loss_eur": aep200, "aep_1_in_200_eur": aep200, "oep_1_in_200_eur": oep200,
        "mean_annual_loss_eur": mean_al,
        "risk_load_eur": round(aep200 - mean_al) if aep200 is not None and mean_al is not None else None,
        "gross_sum_insured_eur": round(gross_si),
        "scr_pct_of_sum_insured": round(100 * aep200 / gross_si, 3) if gross_si and aep200 else None,
        "n_zones": cat.get("n_zones"),
        # prescribed STANDARD-FORMULA NatCat SCR (windstorm+earthquake+flood+hail+subsidence) — EIOPA's own factors, cited
        "standard_formula_natcat": sf_natcat,
        "note": ("Modelled 1-in-200 (99.5 %) annual-aggregate catastrophe loss from the platform's catastrophe simulation on "
                 "the undertaking's stated damage ratios and event probabilities — a modelled figure, not an approved "
                 "internal model. Alongside it, "
                 "the prescribed standard-formula NatCat SCR — all five sub-modules (windstorm, earthquake, flood, "
                 "hail, subsidence), before and after the attested reinsurance — on the version of Del. Reg. 2015/35 in "
                 "force on the reporting date (Arts 90b, 119-126; Annexes III, V-X, XIII, XXII-XXVI), a regulatory "
                 "calculation rather than a platform hazard model. Both bases are labelled; man-made catastrophe is out "
                 "of scope."),
    }


def _reinsurance_from_cat(cat: dict, program: dict | None, scenario: str, horizon: str) -> dict:
    """Gross-vs-net retention derived from a cat distribution already run WITH the reinsurance program (a gap without
    an attested programme)."""
    if program is None:
        return {"available": False, "reason": "gap", "gap": "no reinsurance treaty attested for the period"}
    if not cat or not cat.get("available"):
        return {"available": False, "reason": (cat or {}).get("reason", "No scored policies in this book."),
                **({"gap": cat.get("gap")} if (cat or {}).get("gap") else {})}
    return {
        "available": True, "scenario": scenario, "horizon": horizon,
        "pml_return_period": cat.get("pml_return_period"),
        "gross_pml_eur": cat.get("pml_eur"),
        "gross_oep_1_in_200_eur": (cat.get("oep_eur") or {}).get("rp_200"),
        "gross_mean_annual_loss_eur": cat.get("mean_annual_loss_eur"),
        "program": program, "net": cat.get("net_of_reinsurance"),
    }


def _investments_block(session, org_id, scenario, horizon, _st, method, translation=None) -> dict:
    """Investment-side (asset) climate VaR — the other regulatory half (EIOPA/IFRS S2), on the stated method. Shared by
    the /investments endpoint and the disclosure snapshot. Returns available:False where no investment book exists."""
    from ml.scoring.valuation_discount import VAR_SIMULATIONS
    rows = fetch_entities_with_risk(session, org_id, "insurer_investments", scenario, horizon, method=method,
                                    translation=translation)
    if not rows:
        return {"available": False, "reason": "No investment portfolio has been uploaded."}
    holdings = [{**r, "position_value_eur": r.get("primary_value_eur")} for r in rows]
    total = sum(h.get("primary_value_eur") or 0 for h in holdings)
    n_scored = sum(1 for h in holdings if h.get("headline_bucket"))
    return {
        "available": True, "scenario": scenario, "horizon": horizon,
        "n_holdings": len(holdings), "n_scored": n_scored, "total_value_eur": round(total),
        "coverage_pct": round(100 * n_scored / len(holdings), 1) if holdings else 0.0,
        "climate_var": combined_climate_var(method, holdings, org_id, scenario, horizon, VAR_SIMULATIONS,
                                            _st["climate_var_dependence"]),
    }


def _rollup(policies, method, org_id=None, scenario=None, horizon=None, *, pml_return_period: int, reinsurance=None,
            zones_of=None):
    """The book's modelled expected annual loss and technical premium on the undertaking's stated method (a gap while any
    priced policy's is not stated), by band, and the catastrophe accumulation. The written premium is the book's own
    figure, not this; a 'loss ratio' of the two modelled figures would only restate the loadings, so none is shown."""
    total = sum(p["sum_insured_eur"] or 0 for p in policies)
    priced = [p for p in policies if p["pricing"]]
    eals = [p["pricing"]["expected_annual_loss_eur"] for p in priced]
    prems = [p["pricing"]["technical_premium_eur"] for p in priced]
    total_eal = None if None in eals else sum(eals)
    total_premium = None if None in prems else sum(prems)
    by_bucket = defaultdict(lambda: {"count": 0, "sum_insured_eur": 0.0, "eal_eur": 0.0})
    for p in policies:
        b = p["headline_bucket"] or "none"
        by_bucket[b]["count"] += 1
        by_bucket[b]["sum_insured_eur"] += p["sum_insured_eur"] or 0
        if p["pricing"] and total_eal is not None:
            by_bucket[b]["eal_eur"] += p["pricing"]["expected_annual_loss_eur"]
    return {
        "n_policies": len(policies),
        "n_priced": len(priced),
        "total_sum_insured_eur": round(total),
        **value_at_risk(policies, "sum_insured_eur", method),
        "at_risk_by_region": at_risk_by(policies, "sum_insured_eur", "region", method),
        "total_expected_annual_loss_eur": None if total_eal is None else round(total_eal),
        "total_technical_premium_eur": None if total_premium is None else round(total_premium),
        **({"gap": method.gap_text()} if method.gap_text() else {}),
        "by_bucket": {k: {"count": v["count"], "sum_insured_eur": round(v["sum_insured_eur"]),
                           "eal_eur": None if total_eal is None else round(v["eal_eur"])} for k, v in by_bucket.items()},
        # Portfolio catastrophe accumulation — AEP/OEP exceedance & PML (the tail the summed EALs hide).
        # In the frozen-snapshot path a reinsurance program is passed so the cat run also yields net-of-reinsurance.
        "catastrophe": (catastrophe_accumulation(policies, org_id, scenario, horizon,
                                                 pml_return_period=pml_return_period, reinsurance=reinsurance,
                                                 zones_of=zones_of)
                        if org_id and scenario and horizon else None),
        "top_policies": sorted(
            [p for p in policies if p["headline_score"] is not None],
            key=lambda p: -p["headline_score"])[:8],
    }


def zones_of(policies: list) -> dict:
    """{policy id: (peril, region)} — the accumulation zones of a reference book, to hold fixed across a scenario
    comparison (ml.scoring.cat_accumulation)."""
    return {str(p["policy_id"]): (p.get("headline_hazard") or "unknown", p.get("region") or "unspecified") for p in policies}


def build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None,
                              zones=None, reporting_entity_id=None, period_end=None):
    """The insurer's climate / NatCat exposure disclosure — sum insured at or above the stated at-risk level by hazard, plus the
    loss-curve rollup. Live and frozen callers share this so a filing can't drift from the live view.
    entity_ids / value_weights scope + consolidation-weight the book (None = whole org). zones: accumulation zones held
    fixed across a scenario comparison (zones_of(reference book policies))."""
    _st = get_calc_settings(session, org_id)
    from services.governance.reporting_settings import get_settings
    from services.portfolio_engine import exposure_by_hazard
    pe = period_end or date.fromisoformat(str(get_settings(session, org_id)["reporting_period_end"])[:10])
    method = for_org(session, org_id, pe)
    policies = _policies_with_risk(session, org_id, scenario, horizon, method=method, entity_ids=entity_ids,
                                   value_weights=value_weights, translation=translation)
    hazards = exposure_by_hazard(policies, "sum_insured_eur", method)
    # One cat run (via _rollup, with the attested reinsurance programme) yields the accumulation curve, the 1-in-200
    # and the net-of-reinsurance retention — the three blocks derived from the SAME frozen distribution. The programme
    # is the undertaking's attested treaty for the period (services.insurer_capital); without one the net is a gap.
    from services.insurer_capital import programme
    if reporting_entity_id is None and entity_ids:          # the undertaking (or group top) this scoped book is for
        from services.governance.entities import root_of
        reporting_entity_id = root_of(session, org_id, entity_ids)
    prog, prog_basis = programme(session, org_id, pe, reporting_entity_id)
    if prog is not None and translation is not None and translation.presentation != "EUR":   # treaty layers are in EUR
        from services.governance.translation import from_eur
        prog = {**prog, **{k: from_eur(session, translation, v) for k, v in prog.items() if k.endswith("_eur") and v is not None}}
    rollup = _rollup(policies, method, org_id, scenario, horizon, pml_return_period=_st["pml_return_period"],
                     reinsurance=prog, zones_of=zones)
    cat = rollup.get("catastrophe") or {}
    return {
        "rollup": rollup, "policies": policies, "by_hazard": hazards,
        "solvency_scr": _scr_from_cat(cat, policies, scenario, horizon,
                                      standard_formula_inputs(session, org_id, translation, reporting_entity_id)),
        "reinsurance": {**_reinsurance_from_cat(cat, prog, scenario, horizon), "program_basis": prog_basis},
        "investments": _investments_block(session, org_id, scenario, horizon, _st, method, translation=translation),
        "method": method.record(),
    }


@router.get("/portfolio", summary="Property book projected onto the golden source")
def portfolio(session: DbSession, org_id: OrgId,
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    _st = get_calc_settings(session, org_id)
    method = for_org(session, org_id)
    policies = _policies_with_risk(session, org_id, scenario, horizon, method=method)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": _rollup(policies, method, org_id, scenario, horizon, pml_return_period=_st["pml_return_period"]), "policies": policies}


@router.get("/investments", summary="Investment-side climate risk — the insurer's asset book (the other regulatory half)")
def investments(session: DbSession, org_id: OrgId,
                scenario: str = Query("disorderly_2c"), horizon: str = Query("current")):
    """An insurer is an underwriter AND a large institutional investor; EIOPA/IFRS S2 require climate risk on
    both sides. The liability side is /portfolio; this is the ASSET side — the same combined physical+transition
    climate-VaR engine the asset managers use, run on the insurer's own investment book. Honest: unscored
    positions are excluded (coverage reported), nothing invented."""
    _st = get_calc_settings(session, org_id)
    return {"org_id": org_id, **_investments_block(session, org_id, scenario, horizon, _st, for_org(session, org_id))}


@router.get("/solvency-scr", summary="Solvency II nat-cat: the standard-formula SCR beside the modelled 1-in-200 loss")
def solvency_scr(session: DbSession, org_id: OrgId,
                 scenario: str = Query("baseline"), horizon: str = Query("current")):
    """Nat-cat capital on TWO labelled bases: under `standard_formula_natcat` the PRESCRIBED STANDARD-FORMULA SCR on
    the version of Delegated Regulation 2015/35 in force on the reporting date (Arts 90b, 119-126 —
    services/governance/solvency2_natcat.py::natcat_scr), before and after the attested reinsurance; beside it the
    MODELLED 1-in-200 (99.5%) annual-aggregate loss of the platform's catastrophe simulation on the undertaking's
    stated method — context, not an approved internal model (Directive 2009/138/EC Art. 112)."""
    _st = get_calc_settings(session, org_id)
    method = for_org(session, org_id)
    policies = _policies_with_risk(session, org_id, scenario, horizon, method=method)
    cat = catastrophe_accumulation(policies, org_id, scenario, horizon, pml_return_period=200)
    return _scr_from_cat(cat, policies, scenario, horizon, standard_formula_inputs(session, org_id))


@router.get("/reinsurance/attested", summary="Net of the reinsurance treaty attested for the period — as the filings freeze it")
def reinsurance_attested(session: DbSession, org_id: OrgId,
                         scenario: str = Query("baseline"), horizon: str = Query("current")):
    """The gross-vs-net retention on the undertaking's ATTESTED treaty for the reporting period (services.insurer_capital)
    — the block every insurer filing freezes; a named gap until a treaty is attested."""
    return build_disclosure_snapshot(session, org_id, scenario, horizon)["reinsurance"]


@router.get("/reinsurance", summary="Net-of-reinsurance retention — test a programme against the gross catastrophe loss")
def reinsurance(session: DbSession, org_id: OrgId,
                scenario: str = Query("baseline"), horizon: str = Query("current"),
                quota_share_pct: float = Query(..., ge=0, le=100, description="the programme to test — no default"),
                xol_attachment_eur: float = Query(..., ge=0), xol_limit_eur: float = Query(..., ge=0)):
    """The loss the insurer actually RETAINS after ceding to reinsurers — the number that hits its capital.
    Applies the reinsurance program (proportional quota share + a per-occurrence catastrophe excess-of-loss
    layer) to the same modelled gross catastrophe loss distribution and returns gross vs net PML/OEP/AEP.
    Honest: the quota share is exact; the cat XoL recovers on the single largest event (exact on the OEP), and
    a within-year aggregate treaty / reinstatements are not modelled — disclosed in the note."""
    _st = get_calc_settings(session, org_id)
    method = for_org(session, org_id)
    policies = _policies_with_risk(session, org_id, scenario, horizon, method=method)
    prog = {"quota_share_pct": quota_share_pct, "xol_attachment_eur": xol_attachment_eur, "xol_limit_eur": xol_limit_eur}
    cat = catastrophe_accumulation(policies, org_id, scenario, horizon,
                                   pml_return_period=_st["pml_return_period"], reinsurance=prog)
    return _reinsurance_from_cat(cat, prog, scenario, horizon)


class IncurredLossRequest(BaseModel):
    period_start: date
    period_end: date
    peril: str
    gross_incurred_loss_eur: float = Field(..., ge=0, description="In `currency`.")
    net_incurred_loss_eur: Optional[float] = Field(None, ge=0, description="In `currency`.")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 code of the losses — never assumed. Losses "
                          "are a flow over the period: converted at the average rate from period_start to period_end.")
    source: str = Field("client", description="Where this figure came from, e.g. 'client', 'audited_accounts'.")
    region: Optional[str] = Field(None, description="Geographic segment (SASB FN-IN-450a.2 disaggregation) — "
                                  "optional, e.g. 'Germany' or 'Western Europe'.")
    modelled: Optional[bool] = Field(None, description="Whether this was a modelled vs non-modelled catastrophe "
                                     "(SASB FN-IN-450a.2 disaggregation) — optional.")


def _modeled_for_incurred(session, org_id: str, scenario: str, horizon: str) -> dict:
    """The ¶16(c)-(d) ANTICIPATED figures (EAL + NatCat SCR, both bases) already disclosed elsewhere — passed
    alongside the ¶16(a) actual-incurred rollup so a reader can compare modelled vs actual without re-deriving
    it. Same underlying cat run the /solvency-scr and /summary endpoints use; honest when nothing is scored."""
    from services.governance.insurer_solvency import modelled_1_in_200
    _st = get_calc_settings(session, org_id)
    method = for_org(session, org_id)
    policies = _policies_with_risk(session, org_id, scenario, horizon, method=method)
    rollup = _rollup(policies, method, org_id, scenario, horizon, pml_return_period=_st["pml_return_period"])
    cat = rollup.get("catastrophe") or {}
    scr = _scr_from_cat(cat, policies, scenario, horizon, standard_formula_inputs(session, org_id))
    sf = scr.get("standard_formula_natcat") or {}
    return {
        "regulation": "IFRS S2 paragraph 16(c)-(d) — anticipated financial effects",
        "scenario": scenario, "horizon": horizon,
        "total_expected_annual_loss_eur": rollup.get("total_expected_annual_loss_eur"),
        "modelled_natcat_1_in_200_eur": modelled_1_in_200(scr) if scr.get("available") else None,
        "standard_formula_natcat_scr_eur": sf.get("natcat_scr_eur") if sf.get("available") else None,
        "available": bool(scr.get("available")),
    }


@router.get("/incurred-losses", summary="IFRS S2 ¶16(a) — actual incurred NatCat losses on file, by peril and period")
def get_incurred_losses(session: DbSession, org_id: OrgId,
                        scenario: str = Query("baseline"), horizon: str = Query("current")):
    """Actual, backward-looking claims for the reporting period — the honest counterpart to the modelled
    EAL/SCR everywhere else on this page (IFRS S2 ¶16(c)-(d)). Customer-supplied; says so explicitly when
    nothing has been submitted yet rather than showing a silent zero."""
    modeled = _modeled_for_incurred(session, org_id, scenario, horizon)
    return {"org_id": org_id, **incurred_loss_summary(session, org_id, modeled=modeled)}


@router.get("/incurred-losses/records", summary="Raw incurred-loss submissions on file (audit ledger)")
def get_incurred_loss_records(session: DbSession, org_id: OrgId):
    return {"org_id": org_id, "records": list_incurred_losses(session, org_id)}


@router.post("/incurred-losses", summary="Submit an actual incurred NatCat loss for a reporting period (audited)")
def post_incurred_loss(body: IncurredLossRequest, session: DbSession, ctx: CurrentUser):
    """Customer-supplied — same discipline as the bank's EVIC backfill / REIT gross-revenue field: an honest
    input for data the platform cannot observe itself (the insurer's own claims/financial records), never
    fabricated. A second submission for the same period+peril is additive (e.g. a claims-development update),
    not an overwrite, so restated history stays visible in the ledger."""
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    if body.peril not in HAZARD_VALUES:
        raise HTTPException(status_code=400, detail=f"Unrecognised peril. Choose one of: {', '.join(HAZARD_VALUES)}")
    if body.period_end < body.period_start:
        raise HTTPException(status_code=400, detail="period_end must not be before period_start")
    if body.net_incurred_loss_eur is not None and body.net_incurred_loss_eur > body.gross_incurred_loss_eur:
        raise HTTPException(status_code=400, detail="net_incurred_loss_eur cannot exceed gross_incurred_loss_eur")

    org_id = ctx["org"]["org_id"]
    from services.intake.money import MoneyError, convert_amount, source_record
    period = (body.period_start, body.period_end)
    try:
        conv = {"gross_incurred_loss_eur": convert_amount(session, body.gross_incurred_loss_eur, body.currency, body.period_end, org_id=org_id,
                                                      flow=True, period=period, label="gross incurred loss")}
        if body.net_incurred_loss_eur is not None:
            conv["net_incurred_loss_eur"] = convert_amount(session, body.net_incurred_loss_eur, body.currency, body.period_end, org_id=org_id,
                                                       flow=True, period=period, label="net incurred loss")
    except MoneyError as e:
        raise HTTPException(status_code=422, detail={"error": "currency", "message": str(e)})
    res = submit_incurred_loss(session, org_id, body.period_start, body.period_end, body.peril,
                               conv["gross_incurred_loss_eur"]["eur"],
                               conv["net_incurred_loss_eur"]["eur"] if "net_incurred_loss_eur" in conv else None, body.source,
                               created_by=ctx["user"]["id"], region=body.region, modelled=body.modelled,
                               money_source=source_record(body.currency.upper(), body.period_end, conv, origin="manual_entry"))
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="incurred_loss.submit",
                target_type="insurer_incurred_losses", target_id=res["loss_id"],
                detail={"period_start": str(body.period_start), "period_end": str(body.period_end),
                        "peril": body.peril, "gross_incurred_loss": body.gross_incurred_loss_eur,
                        "net_incurred_loss": body.net_incurred_loss_eur, "currency": body.currency.upper(),
                        "gross_incurred_loss_eur": conv["gross_incurred_loss_eur"]["eur"], "source": body.source})
    return {"loss_id": res["loss_id"], "reported_at": res["reported_at"].isoformat(), **body.model_dump(mode="json"),
            "gross_incurred_loss_eur": conv["gross_incurred_loss_eur"]["eur"],
            "net_incurred_loss_eur": conv["net_incurred_loss_eur"]["eur"] if "net_incurred_loss_eur" in conv else None,
            "fx": [c["rate"] for c in conv.values() if c.get("rate")]}


@router.get("/forward-risk", summary="Forward-change decision signal — scenario risk migration + runway")
def forward_risk_ep(session: DbSession, org_id: OrgId, scenario: str = Query("disorderly_2c")):
    from services.intelligence.forward_risk import forward_risk
    from services.money.params import for_org
    return forward_risk(session, org_id, "insurance", scenario, for_org(session, org_id))


@router.get("/summary", summary="Loss-curve pricing rollup")
def summary(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id = :o"
    ), {"o": org_id}).mappings().first()
    _st = get_calc_settings(session, org_id)
    method = for_org(session, org_id)
    policies = _policies_with_risk(session, org_id, scenario, horizon, method=method)
    return {"org_id": org_id, "org": dict(org) if org else None, "rollup": _rollup(policies, method, org_id, scenario, horizon, pml_return_period=_st["pml_return_period"])}


@router.get("/triggers", summary="Parametric trigger monitoring — live payout status across the book")
def triggers(session: DbSession, org_id: OrgId,
             scenario: str = Query("baseline"), horizon: str = Query("current")):
    """No claims process: a policy's configured hazard score crossing its
    attachment/exhaustion band (ml/scoring/parametric_trigger.py) IS the payout
    decision, computed live off the same canonical_scores every other insurance
    view reads -- 'automatic payout the moment real data crosses a threshold'."""
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id = :o"
    ), {"o": org_id}).mappings().first()
    _st = get_calc_settings(session, org_id)
    method = for_org(session, org_id)
    policies = _policies_with_risk(session, org_id, scenario, horizon, method=method)
    configured = [p for p in policies if p["trigger"]]
    triggered_now = [p for p in configured if p["trigger"]["is_triggered"]]
    return {
        "org_id": org_id, "org": dict(org) if org else None,
        "rollup": {
            "n_configured": len(configured),
            "n_triggered_now": len(triggered_now),
            "total_payout_if_triggered_eur": round(sum(p["trigger"]["payout_eur"] for p in triggered_now)),
        },
        "triggered_now": sorted(triggered_now, key=lambda p: -p["trigger"]["payout_pct"]),
        "configured": sorted(configured, key=lambda p: -p["trigger"]["payout_pct"]),
    }


@router.get("/policy/{policy_id}", summary="One policy — full projection + pricing + trigger, provenance")
def policy_detail(policy_id: str, session: DbSession, caller_org: OrgId):
    """The per-policy drill-through every other vertical already has (bank's
    /asset/{id}, real estate's /property/{id}, asset mgmt's /holding/{id}) --
    insurance was the one sector missing it, so "Most exposed policies" and
    both ParametricTriggers.jsx lists had nowhere to click through to."""
    own_or_404(session, "portfolio_entities", "entity_id", policy_id, caller_org, "Policy")   # only your own org's record
    org_id = get_entity_org(session, policy_id)
    method = for_org(session, org_id)
    trigger_row = session.execute(text("""
        SELECT policy_id::text AS policy_id, hazard_type, CAST(attachment_score AS FLOAT) AS attachment_score,
               CAST(exhaustion_score AS FLOAT) AS exhaustion_score, updated_by::text AS updated_by, updated_at
        FROM insurance_policy_triggers WHERE policy_id = :p
    """), {"p": policy_id}).mappings().first()
    trigger_by_policy = {trigger_row["policy_id"]: dict(trigger_row)} if trigger_row else {}
    # Pre-existing quirk, same as banking's asset_detail: no scenario/horizon params,
    # so headline is picked across EVERY scenario/horizon this policy has ever been
    # scored under -- can disagree with the portfolio list's scenario-scoped headline.
    row = get_entity_with_risk(session, policy_id, "baseline", "current", method=method,
                                ext_table="ext_insurance", ext_columns=EXT_INSURANCE_COLUMNS,
                                extra_calc=_insurance_extra(method, trigger_by_policy),
                                scope_headline_to_query=False)
    policy = {
        "policy_id": row["entity_id"], "org_id": row["org_id"], "policy_name": row["entity_name"],
        "policy_type": row["entity_type"], "country": row["country"], "region": row["region"],
        "lat": row["lat"], "lon": row["lon"], "h3_cell": row["h3_cell"],
        "sum_insured_eur": row["primary_value_eur"], "deductible_pct": row["deductible_pct"],
        "building_value_eur": row["building_value_eur"], "contents_value_eur": row["contents_value_eur"],
        "business_interruption_value_eur": row["business_interruption_value_eur"],
        "construction_type": row["construction_type"], "year_built": row["year_built"],
        "number_of_stories": row["number_of_stories"], "pricing": row["pricing"], "trigger": row["trigger"],
    }
    audit = session.execute(text("""
        SELECT actor_user_id::text AS actor_user_id, action, detail, created_at
        FROM access_audit_log WHERE target_type = 'insurance_policy' AND target_id = :p
        ORDER BY created_at DESC LIMIT 5
    """), {"p": policy_id}).mappings().all()
    return {"policy": policy, "risks": row["risks"], "audit": [dict(x) for x in audit]}


class TriggerConfigRequest(BaseModel):
    hazard_type: str
    attachment_score: float = Field(..., ge=0, le=100)
    exhaustion_score: float = Field(..., ge=0, le=100)


@router.post("/policies/{policy_id}/trigger-config", summary="Set/update a policy's parametric trigger band (audited)")
def set_trigger_config(policy_id: str, body: TriggerConfigRequest, session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    if body.hazard_type not in HAZARD_VALUES:
        raise HTTPException(status_code=400, detail="Unrecognised hazard type. Choose one of the supported hazards.")
    if body.exhaustion_score <= body.attachment_score:
        raise HTTPException(status_code=400, detail="exhaustion_score must be greater than attachment_score")
    policy = session.execute(text(
        "SELECT org_id::text AS org_id FROM portfolio_entities WHERE entity_id = :p AND vertical = 'insurance'"
    ), {"p": policy_id}).mappings().first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found.")
    if policy["org_id"] != ctx["org"]["org_id"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Policy does not belong to your organization"})

    now = datetime.now(timezone.utc)
    session.execute(text("""
        INSERT INTO insurance_policy_triggers (policy_id, hazard_type, attachment_score, exhaustion_score, updated_by, updated_at)
        VALUES (:p, :h, :a, :e, :u, :now)
        ON CONFLICT (policy_id) DO UPDATE
            SET hazard_type = EXCLUDED.hazard_type, attachment_score = EXCLUDED.attachment_score,
                exhaustion_score = EXCLUDED.exhaustion_score, updated_by = EXCLUDED.updated_by, updated_at = EXCLUDED.updated_at
    """), {"p": policy_id, "h": body.hazard_type, "a": body.attachment_score, "e": body.exhaustion_score,
           "u": ctx["user"]["id"], "now": now})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="policy.trigger_config.set", target_type="insurance_policy", target_id=policy_id,
                detail={"hazard_type": body.hazard_type, "attachment_score": body.attachment_score,
                        "exhaustion_score": body.exhaustion_score})
    return {"policy_id": policy_id, "hazard_type": body.hazard_type,
            "attachment_score": body.attachment_score, "exhaustion_score": body.exhaustion_score}


# A real Statement of Values (SOV, the ACORD 140-style format insurers/reinsurers
# already exchange property schedules in) -- see services/templates/workbook.py's
# template. TIV (Total Insured Value) is properly building + contents + business
# interruption; a bare sum_insured_eur is still accepted as a fallback for a
# counterparty that only has one lump figure.
# POLICY_TEMPLATE_FIELDS lives in services/ingest/templates.py (shared with the intake pipeline)
REQUIRED_POLICY_COLUMNS = [f["name"] for f in POLICY_TEMPLATE_FIELDS if f["required"]]


@router.get("/policies/template.xlsx", summary="Download the Statement of Values upload template (Excel)")
def policies_template_xlsx():
    buf = build_template_workbook(POLICY_TEMPLATE_FIELDS)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=tellumen_sov_template.xlsx"})


@router.post("/policies/validate", summary="Check a Statement of Values (CSV or Excel) before importing — nothing is saved")
async def validate_policies(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                            declared_row_count: Optional[str] = Form(None), declared_totals: Optional[str] = Form(None),
                         mapping_profile_id: Optional[str] = Form(None),
                         currency: Optional[str] = Form(None), book_date: Optional[str] = Form(None)):
    """Dry run of every intake check (security inspection, required columns, row checks, receipt, transformation and
    the gate the import will enforce). Nothing is stored or written."""
    from api.services.intake_http import declared_from_form, preview
    return preview(session, ctx["org"]["org_id"], "insurance_policies", await file.read(), file.filename,
                   declared_from_form(declared_row_count, declared_totals), mapping_profile_id,
                   currency=currency, book_date=book_date)


@router.post("/policies/upload", summary="Import policies (CSV or Excel) into your property book")
async def upload_policies(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                          declared_row_count: Optional[str] = Form(None), declared_totals: Optional[str] = Form(None),
                          approval_reason: Optional[str] = Form(None), mapping_profile_id: Optional[str] = Form(None),
                         currency: Optional[str] = Form(None), book_date: Optional[str] = Form(None)):
    """Runs the Statement of Values through the intake pipeline (services/intake/pipeline.py): the file is stored write-once,
    security-inspected and malware-scanned, then checked. Every check passed → imported now (200). A check failed →
    sent to a second person for approval with your reason (202; nothing lands until approved). Scanner unavailable
    where required → held (202). Nothing valid, or refused on security grounds → 422, and the attempt is recorded."""
    from api.services.intake_http import declared_from_form, submit
    return submit(session, ctx["org"]["org_id"], "insurance_policies", await file.read(), file.filename,
                  user_id=ctx["user"]["id"], declared=declared_from_form(declared_row_count, declared_totals),
                  reason=approval_reason, mapping_profile_id=mapping_profile_id,
                  currency=currency, book_date=book_date)


@router.get("/portfolio.xlsx", summary="Loss-curve pricing book (Excel)")
def portfolio_xlsx(session: DbSession, org_id: OrgId,
                    scenario: str = Query("baseline"), horizon: str = Query("current")):
    _st = get_calc_settings(session, org_id)
    method = for_org(session, org_id)
    policies = _policies_with_risk(session, org_id, scenario, horizon, method=method)
    headers = ["policy_name", "region", "country", "sum_insured_eur", "construction_type", "year_built",
               "headline_hazard", "headline_score", "risk_bucket", "mdr", "scenario_loss_eur",
               "expected_annual_loss_eur", "technical_premium_eur", "rate_on_line_pct"]
    rows = [[p["policy_name"], p["region"], p["country"], p["sum_insured_eur"], p.get("construction_type"),
             p.get("year_built"), p["headline_hazard"], p["headline_score"], p["headline_bucket"] or "unscored",
             p["pricing"]["mdr"] if p["pricing"] else None, p["pricing"]["scenario_loss_eur"] if p["pricing"] else None,
             p["pricing"]["expected_annual_loss_eur"] if p["pricing"] else None,
             p["pricing"]["technical_premium_eur"] if p["pricing"] else None,
             p["pricing"]["rate_on_line_pct"] if p["pricing"] else None] for p in policies]
    buf = build_export_workbook(headers, rows, sheet_name="Loss-curve pricing")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=iberia-loss-curve-pricing.xlsx"})

"""One valuation of an exposure's Taxonomy figures, for every template that reports them — the EU Taxonomy Art. 8
templates of credit institutions (Annex VI of Delegated Regulation (EU) 2021/2178) and the Pillar 3 GAR templates
(Templates 7-9 of ITS 2024/3172, which disclose 'the GAR as referred to in Delegated Regulation (EU) 2021/2178',
'based on the turnover alignment of the counterparty for the general purpose lending part only').

Annex V's method, applied per exposure:
  * a general-purpose exposure to an undertaking is valued by the counterparty's own KPIs (issuer_taxonomy_kpi, frozen
    with the filing): its eligible / aligned / transitional / enabling share, per objective and basis. The CapEx-based
    figure of general lending uses the counterparty's turnover KPI (the vocabulary's basis_rules, cited). Where the
    counterparty's KPIs are not on file, the figure is not known (None) — never estimated
  * a specific-purpose exposure (specialised lending / use of proceeds), a household, a local government or a
    repossessed property is valued by its own stated Taxonomy status, objective and contribution
The facts an exposure states (FINREP counterparty sector and sub-sector, instrument, NFRD / CSRD scope, purpose,
collateral, government level, trading book, EU or not, Taxonomy status / objective / contribution, specialised
lending, EP score, EPC) are read once, here. Declared defaults (reference data, counted on the form): an unstated
instrument is a loan; counterparty sector and collateral are inferred as in pillar3_grids.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from services.governance.pillar3_grids import collateral, counterparty
from services.reference.eu_membership import is_member as eu_member
from services.reference.taxonomy_activities import codes_of

_DECL = Path(__file__).resolve().parents[2] / "data" / "reference" / "declarations"
INSTRUMENT_DEFAULT = json.loads((_DECL / "instrument_type_default.json").read_text())["default"]
UNDERTAKINGS = ("credit_institution", "other_financial_corporation", "non_financial_corporation")


def facts(a: dict, period: tuple[date, date] | None = None) -> dict:
    cp, _ = counterparty(a)
    col, _ = collateral(a)
    instr = (a.get("instrument_type") or "").strip().lower() or None
    status = (a.get("taxonomy_status") or "").strip().lower()
    orig = str(a.get("loan_origination_date") or "")[:10]
    return {"cp": cp, "sub": a.get("counterparty_subsector"), "instr": instr or INSTRUMENT_DEFAULT,
            "instr_stated": instr is not None, "nfrd": a.get("nfrd_subject"), "csrd": a.get("csrd_subject"),
            "purpose": a.get("loan_purpose"),
            "col": col, "govt": (a.get("counterparty_govt_level") or "").strip().lower() or None,
            "trading": bool(a.get("trading_book")), "eu": eu_member(a.get("country")),
            "assessed": status in ("eligible", "aligned", "not_eligible"), "eligible": status in ("eligible", "aligned"),
            # alignment is known only where it is stated: an 'aligned' status or the client's CCM-sustainable fact. The
            # Taxonomy classifier establishes eligibility only (it never returns 'aligned'), so 'eligible' ≠ 'not aligned'.
            "aligned": status == "aligned" or a.get("ccm_sustainable") is True,
            "aligned_known": status in ("aligned", "not_eligible") or a.get("ccm_sustainable") is not None,
            "objective": a.get("taxonomy_objective"),
            "contribution": a.get("taxonomy_contribution"), "specialised": a.get("specialised_lending"),
            "new": bool(period and orig and period[0].isoformat() <= orig <= period[1].isoformat()),
            "ep": a.get("ep_score_kwh_m2"), "ep_estimated": a.get("ep_score_estimated"),
            "epc": (str(a.get("epc_label") or "").strip().upper() or None),
            "kpi": a.get("counterparty_taxonomy_kpi") or {}, "nace": a.get("nace_code"),
            "activities": frozenset(codes_of(a.get("taxonomy_activity")))}


def general_purpose(f: dict) -> bool:
    return f["cp"] in UNDERTAKINGS and f["specialised"] is not True


def _kpi_basis(f: dict, basis: str) -> str:
    from services.governance.taxonomy_vocabulary import vocabulary
    if basis == "capex" and f["instr"] == "loans_and_advances":
        return vocabulary().get("basis_rules", {}).get("capex_general_lending_uses", "capex")
    return basis


def value(f: dict, x: float, measure: str, objectives: tuple[str, ...], basis: str) -> float | None:
    """This exposure's part of a figure over the given objectives (None = the fact it needs is not stated)."""
    if general_purpose(f):
        if measure in ("use_of_proceeds", "adaptation", "transitional_or_adaptation"):
            return 0.0 if measure == "use_of_proceeds" else None
        b = _kpi_basis(f, basis)
        vals = [(f["kpi"].get(f"{b}:{o}") or {}).get(measure) for o in objectives]
        if all(v is None for v in vals):
            # a total the counterparty does not split by objective answers only the all-objectives figure
            from services.reference.taxonomy_objectives import codes
            total = (f["kpi"].get(f"{b}:all") or {}).get(measure)
            if total is None or set(objectives) != set(codes()):
                return None
            return x * float(total) / 100.0
        return x * sum(float(v) for v in vals if v is not None) / 100.0
    # a specific-purpose exposure: its own stated status
    if not f["assessed"]:
        return None
    if f["eligible"] and not f["objective"]:
        return None                                      # eligible, but to which objective is not stated
    hit = f["eligible"] and f["objective"] in objectives
    if measure == "eligible":
        return x if hit else 0.0
    if not f["aligned_known"]:
        return None
    aligned = hit and f["aligned"]
    if measure == "aligned":
        return x if aligned else 0.0
    if measure == "use_of_proceeds":
        return x if aligned and f["specialised"] else 0.0
    if not aligned:
        return 0.0
    if not f["contribution"]:
        return None
    want = {"transitional": ("transitional",), "enabling": ("enabling",), "adaptation": ("adaptation",),
            "transitional_or_adaptation": ("transitional", "adaptation")}[measure]
    return x if f["contribution"] in want else 0.0


def total(pop: list, measure: str, objectives: tuple[str, ...], basis: str) -> float | None:
    """A figure over a population: the known parts added up; None when no exposure states what the figure needs."""
    if measure == "gross":
        return sum(x for _, x in pop)
    parts = [value(f, x, measure, objectives, basis) for f, x in pop]
    known = [p for p in parts if p is not None]
    return sum(known) if known else None

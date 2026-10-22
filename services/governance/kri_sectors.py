"""The REIT, insurer and asset-manager KRI sets, anchored on each sector's live governed report (E87).

They were keyed by TCFD-style report types, retired 2026-10-01 (services.governance.filings.FRAMEWORKS). Each set now
belongs to the report the sector files — REIT: reit_taxonomy; insurer: insurer_solvency; asset manager: sfdr_pai (its
holdings KRIs join the PAI set). A KRI that report prints carries `filed_basis` (where it is printed) and a filed
history read from that report's frozen snapshots; a KRI no governed report prints is `live_only`: it says so, and has
no filed history — nothing is borrowed from another report or invented.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

REIT, INSURER, ASSET_MANAGER = "reit_taxonomy", "insurer_solvency", "sfdr_pai"

# KRI key -> where the anchor report prints it
_REIT_PRINTED = {"taxonomy": "EU Taxonomy Art. 8 filing — Turnover KPI, Taxonomy-eligible (A), % of turnover"}
_INSURER_PRINTED = {"natcat_scr": "Solvency II nat-cat filing — modelled 1-in-200 loss, gross (the stated method; "
                                  "printed beside the S.27.01.01 standard formula, not a template cell)"}


def anchor(kpis: list[dict], printed: dict[str, str]) -> None:
    """Mark each KPI with its filed basis: where the anchor report prints it, or live only — `filed` in the catalogue's
    words, `filed_basis` the same as one line (where it is printed — a citation, shown one click away — or why not)."""
    from services.governance.kri import msg
    for k in kpis:
        where = printed.get(k["key"])
        k["filed"] = msg("kri.filed.printed", where=where) if where else msg("kri.filed.live_only")
        k["filed_basis"] = where or k["filed"]["detail"]["what"]
        k["live_only"] = where is None


def _hist(h: dict, figures: list[dict]) -> dict:
    # the legacy book-value / at-risk slots stay empty: these reports do not print them
    return {"label": h["label"], "filing_id": h["filing_id"], "total_value": None, "value_at_risk": None,
            "pct_at_risk": None, "figures": figures}


def reit_kri(session: Session, org_id: str) -> dict:
    from api.routers.realestate import build_disclosure_snapshot
    from services.governance.kri import (
        _amount,
        _by_hazard,
        _kpi,
        _snapshot_history,
        fact,
        method_gap,
        msg,
    )
    from services.governance.pillar3_templates import stated_level
    from services.governance.reporting_settings import get_settings
    from services.governance.taxonomy_nonfin import summary, summary_of
    s = get_settings(session, org_id)
    snap = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"])
    r = snap["rollup"]
    cov = round(100 * r.get("n_scored", 0) / r.get("n_properties", 1), 1) if r.get("n_properties") else 0
    at_level = None if stated_level(snap) is not None else method_gap("method.at_risk_level")
    kpis = [
        _kpi("total_value", "Property book value", r.get("total_value_eur", 0) or 0, "eur", about=msg("kri.indicator.property_value")),
        _kpi("value_at_risk", "Value at material physical risk", r.get("value_at_risk_eur"), "eur", tone="#fb7185",
             about=msg("kri.indicator.value_at_risk"), gap=at_level),
        _kpi("pct_at_risk", "Share at risk", r.get("pct_value_at_risk"), "pct", tone="#f0a860",
             about=msg("kri.indicator.pct_at_risk"), gap=at_level),
        _kpi("noi_impact", "NOI impact", r.get("portfolio_noi_impact_pct"), "pct", about=msg("kri.indicator.noi_impact"),
             gap=method_gap(r.get("gap")) if r.get("portfolio_noi_impact_pct") is None else None),
        _kpi("coverage", "Book scored", cov, "pct", about=msg("kri.indicator.properties_scored")),
        # the figure the Art. 8 filing prints: the share of turnover from Taxonomy-eligible activities (Turnover KPI)
        _kpi("taxonomy", "EU-Taxonomy eligible turnover", summary(snap.get("properties") or [])["pct"].get("eligible"),
             "pct", about=msg("kri.indicator.taxonomy_turnover")),
    ]
    es = r.get("energy_stranding") or {}
    if es.get("n_assessed"):
        kpis.append(_kpi("stranding", "Value at stranding risk", es.get("value_at_stranding_risk_eur"), "eur",
                         tone="#f0a860", about=msg("kri.indicator.stranding"), gap=method_gap(es.get("gap")),
                         facts=[] if es.get("gap") else [fact("assessed", es.get("epc_coverage_pct"), "pct")]))
    rc = r.get("resilience_capex") or {}
    if rc.get("available"):
        kpis.append(_kpi("resilience_capex", "Resilience capex to de-risk", _amount(rc.get("total_resilience_capex_eur")), "eur",
                         tone="#f0a860", about=msg("kri.indicator.resilience_capex"),
                         facts=[fact("avoided_loss", _amount(rc.get("total_avoided_loss_eur")), "eur"),
                                fact("benefit_cost", rc.get("portfolio_benefit_cost_ratio"), "x")]))
    from services.governance.kri_loss import tested_loss_kpi
    kpis.append(tested_loss_kpi(session, org_id))
    anchor(kpis, _REIT_PRINTED)
    history = [_hist(h, [{"key": "taxonomy", "label": "Taxonomy-eligible turnover", "fmt": "pct",
                          "value": summary_of(h["payload"])["pct"].get("eligible")}])
               for h in _snapshot_history(session, org_id, REIT)]
    return {"framework": REIT, "supported": True, "label": "Property physical-risk and Taxonomy indicators",
            "kpis": kpis, "by_hazard": _by_hazard(snap), "history": history}


def insurer_kri(session: Session, org_id: str) -> dict:
    from api.routers.insurance import build_disclosure_snapshot
    from services.governance.insurer_solvency import modelled_1_in_200, natcat_block
    from services.governance.kri import (
        _amount,
        _by_hazard,
        _kpi,
        _snapshot_history,
        fact,
        method_gap,
        msg,
    )
    from services.governance.pillar3_templates import stated_level
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"])
    r = snap["rollup"]
    cov = round(100 * r.get("n_priced", 0) / r.get("n_policies", 1), 1) if r.get("n_policies") else 0
    kpis = [
        _kpi("sum_insured", "Sum insured", r.get("total_sum_insured_eur", 0) or 0, "eur", about=msg("kri.indicator.sum_insured")),
        _kpi("eal", "Expected annual loss", r.get("total_expected_annual_loss_eur"), "eur", tone="#fb7185",
             about=msg("kri.indicator.expected_annual_loss")),
        _kpi("value_at_risk", "Sum insured at material physical risk", r.get("value_at_risk_eur"), "eur",
             about=msg("kri.indicator.sum_insured_at_risk"),
             gap=None if stated_level(snap) is not None else method_gap("method.at_risk_level")),
        _kpi("coverage", "Policies priced", cov, "pct", about=msg("kri.indicator.policies_priced")),
    ]
    cat = r.get("catastrophe") or {}
    if cat.get("available"):
        rp_ = cat.get("pml_return_period")
        kpis.append(_kpi("cat_pml", f"Catastrophe PML (1-in-{rp_})" if rp_ else "Catastrophe PML", _amount(cat.get("pml_eur")), "eur",
                         tone="#fb7185", about=msg("kri.indicator.probable_maximum_loss"),
                         missing=cat.get("pml_gap_message")))       # no return period chosen: the engine's own message
    scr = snap.get("solvency_scr") or {}
    if scr.get("available"):
        kpis.append(_kpi("natcat_scr", "Modelled 1-in-200 nat-cat loss", _amount(modelled_1_in_200(scr)), "eur",
                         tone="#f0a860", about=msg("kri.indicator.modelled_annual_loss")))
    reins = snap.get("reinsurance") or {}
    net = reins.get("net") or {}
    if reins.get("available") and net:
        kpis.append(_kpi("net_retention", "Net retention (post-reinsurance PML)", _amount(net.get("net_pml_eur")), "eur",
                         tone="#f0a860", about=msg("kri.indicator.net_retention"),
                         facts=[fact("ceded", net.get("cession_ratio_pct"), "pct")]))
    inv = snap.get("investments") or {}
    iv = inv.get("climate_var") or {}
    if inv.get("available") and iv.get("available"):
        kpis.append(_kpi("investment_var", "Investment climate VaR (99%)", _amount(iv.get("var99_eur")), "eur",
                         tone="#fb7185", about=msg("kri.indicator.investment_var"),
                         facts=[fact("positions_scored", inv.get("coverage_pct"), "pct")]))
    from services.governance.kri_loss import tested_loss_kpi
    kpis.append(tested_loss_kpi(session, org_id))
    anchor(kpis, _INSURER_PRINTED)
    history = [_hist(h, [{"key": "natcat_scr", "label": "Modelled 1-in-200 loss, gross", "fmt": "eur",
                          "value": (natcat_block(h["payload"]).get("natcat_scr") or {}).get("gross_1_in_200_eur")}])
               for h in _snapshot_history(session, org_id, INSURER)]
    return {"framework": INSURER, "supported": True, "label": "Nat-cat indicators",
            "kpis": kpis, "by_hazard": _by_hazard(snap), "history": history}


def holdings_kpis(session: Session, org_id: str) -> tuple[list[dict], list[dict]]:
    """The asset manager's holdings-book KRIs (climate VaR, concentration, taxonomy eligibility of value) — none is
    printed by the SFDR PAI statement, so each is live only — and the book's exposure by hazard."""
    from api.routers.assetmgmt import build_disclosure_snapshot
    from services.governance.kri import _by_hazard, _hazard_name, _kpi, fact, msg
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"])
    r, tax, conc = snap.get("rollup", {}), snap.get("taxonomy", {}), snap.get("concentration", {})
    elig = (tax.get("eligible") or {}).get("value_eur", 0) or 0
    tax_total = sum((v or {}).get("value_eur", 0) or 0 for v in tax.values())
    cov = round(100 * r.get("n_scored", 0) / r.get("n_holdings", 1), 1) if r.get("n_holdings") else 0
    kpis = [
        _kpi("holdings_value", "Portfolio value (holdings book)", r.get("total_portfolio_value_eur", 0) or 0, "eur",
             about=msg("kri.indicator.holdings_value")),
        _kpi("climate_var", "Portfolio climate VaR", r.get("total_climate_var_eur"), "eur", tone="#fb7185",
             about=msg("kri.indicator.climate_var")),
        _kpi("var_pct", "Climate VaR (% of book)", r.get("portfolio_climate_var_pct"), "pct", tone="#f0a860",
             about=msg("kri.indicator.climate_var_share")),
        _kpi("holdings_coverage", "Holdings scored", cov, "pct", about=msg("kri.indicator.holdings_scored")),
        _kpi("holdings_taxonomy", "EU-Taxonomy eligible (share of value)",
             round(100 * elig / tax_total, 1) if tax_total else 0, "pct", about=msg("kri.indicator.taxonomy_eligible")),
    ]
    if conc.get("available"):
        tr = conc.get("top_region") or {}
        cs = conc.get("common_shock") or {}
        kpis.append(_kpi("common_shock", "VaR in largest common-shock", conc.get("common_shock_var_pct_of_total"), "pct",
                         tone="#fb7185", about=msg("kri.indicator.common_shock"),
                         facts=[*([fact("cluster_hazard", _hazard_name(cs["hazard"]), "text")] if cs.get("hazard") else []),
                                *([fact("cluster_region", cs["region"], "text")] if cs.get("region") else [])]))
        kpis.append(_kpi("top_region_conc", "Top-region concentration", tr.get("pct_of_book"), "pct", tone="#f0a860",
                         about=msg("kri.indicator.top_region"),
                         facts=[*([fact("largest_region", tr["region"], "text")] if tr.get("region") else []),
                                fact("effective_regions", conc.get("effective_regions"), "num"),
                                fact("effective_hazards", conc.get("effective_hazards"), "num")]))
    anchor(kpis, {})
    return kpis, _by_hazard(snap)


def sfdr_kri(session: Session, org_id: str) -> dict:
    """The asset manager's entity-level SFDR PAI KRIs (the holdings-book ones join them: holdings_kpis)."""
    from ml.regulatory.sfdr_pai import entity_pai_statement
    from services.governance.kri import _kpi, _snapshot_history, fact, msg
    st = entity_pai_statement(session, org_id)
    if st.get("error"):                      # the statement's reason, in the catalogue's words
        e = st["error"]
        n = msg("kri.sfdr.no_funds" if e == "manager has no funds" else
                "kri.sfdr.no_positions" if e.startswith("manager has no positions") else "kri.sfdr.no_statement")
        return {"framework": "sfdr_pai", "supported": True, "label": "SFDR adverse-impact indicators", "kpis": [],
                "by_hazard": [], "history": [], "notice": n}
    ent = st.get("entity", {})
    cs = st.get("coverage_summary", {})
    ind = {i["number"]: i for i in (st.get("indicators") or [])}

    def _val(n):
        return (ind.get(n) or {}).get("value")
    em1 = _val(1)
    total_em = em1.get("total") if isinstance(em1, dict) else em1   # PAI 1 total (Scope 1-3)
    # The mandatory climate PAI indicators, surfaced as KRIs (values, not just counts) — the RTS Annex I
    # Table 1 climate block. Each is the value-weighted figure the fund statement already computes.
    pai = [("nav", "NAV in scope", ent.get("total_value_eur"), "eur", "nav"),
           ("positions", "Positions", ent.get("positions"), "num", "positions"),
           ("pai_emissions", "Financed emissions", total_em, "num", "pai_emissions"),
           ("carbon_footprint", "Carbon footprint", _val(2), "num", "carbon_footprint"),
           ("waci", "WACI", _val(3), "num", "waci"),
           ("fossil_fuel", "Fossil-fuel exposure", _val(4), "pct", "fossil_fuel"),
           ("non_renewable", "Non-renewable energy", _val(5), "pct", "non_renewable"),
           ("energy_intensity", "Energy intensity", _val(6), "dec", "energy_intensity"),
           ("biodiversity", "Biodiversity areas", _val(7), "pct", "biodiversity"),
           ("emissions_water", "Emissions to water", _val(8), "dec", "emissions_water"),
           ("hazardous_waste", "Hazardous waste", _val(9), "dec", "hazardous_waste"),
           ("ungc_violations", "UNGC / OECD violations", _val(10), "pct", "ungc_violations"),
           ("ungc_no_process", "No UNGC monitoring", _val(11), "pct", "ungc_no_process"),
           ("gender_pay_gap", "Gender pay gap", _val(12), "pct", "gender_pay_gap"),
           ("board_diversity", "Board gender diversity", _val(13), "pct", "board_diversity"),
           ("controversial_weapons", "Controversial weapons", _val(14), "pct", "controversial_weapons"),
           ("emissions_cov", "Emissions coverage", cs.get("emissions_coverage_pct"), "pct", "emissions_coverage")]
    kpis = [_kpi(key, label, value, fmt, about=msg(f"kri.indicator.{code}")) for key, label, value, fmt, code in pai]
    kpis.append(_kpi("indicators", "PAI indicators computed", cs.get("computed"), "num", about=msg("kri.indicator.indicators_computed"),
                     facts=[fact("mandatory", cs.get("mandatory_indicators"), "num")]))
    history = [{"label": h["label"], "filing_id": h["filing_id"],
                "total_value": (h["payload"].get("entity") or {}).get("total_value_eur"),
                "value_at_risk": None, "pct_at_risk": None}
               for h in _snapshot_history(session, org_id, "sfdr_pai")]
    return {"framework": "sfdr_pai", "supported": True, "label": "SFDR adverse-impact indicators",
            "kpis": kpis, "by_hazard": [], "history": history}

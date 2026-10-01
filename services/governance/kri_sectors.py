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
LIVE_ONLY = "Live only — no governed report prints this figure, so it has no filed history."

# KRI key -> where the anchor report prints it
_REIT_PRINTED = {"taxonomy": "EU Taxonomy Art. 8 filing — Turnover KPI, Taxonomy-eligible (A), % of turnover"}
_INSURER_PRINTED = {"natcat_scr": "Solvency II nat-cat filing — modelled 1-in-200 loss, gross (the stated method; "
                                  "printed beside the S.27.01.01 standard formula, not a template cell)"}


def anchor(kpis: list[dict], printed: dict[str, str]) -> None:
    """Mark each KPI with its filed basis: where the anchor report prints it, or live only."""
    for k in kpis:
        where = printed.get(k["key"])
        k["filed_basis"] = where or LIVE_ONLY
        k["live_only"] = where is None


def _hist(h: dict, figures: list[dict]) -> dict:
    # the legacy book-value / at-risk slots stay empty: these reports do not print them
    return {"label": h["label"], "filing_id": h["filing_id"], "total_value": None, "value_at_risk": None,
            "pct_at_risk": None, "figures": figures}


def reit_kri(session: Session, org_id: str) -> dict:
    from api.routers.realestate import build_disclosure_snapshot
    from services.governance.kri import _amount, _by_hazard, _kpi, _millions, _snapshot_history
    from services.governance.reporting_settings import get_settings
    from services.governance.taxonomy_nonfin import summary, summary_of
    s = get_settings(session, org_id)
    snap = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"])
    r = snap["rollup"]
    cov = round(100 * r.get("n_scored", 0) / r.get("n_properties", 1), 1) if r.get("n_properties") else 0
    kpis = [
        _kpi("total_value", "Property book value", r.get("total_value_eur", 0) or 0, "eur"),
        _kpi("value_at_risk", "Value at material physical risk", r.get("value_at_risk_eur"), "eur", tone="#fb7185",
             hint="Value at or above the stated at-risk level (method.at_risk_level)"),
        _kpi("pct_at_risk", "Share at risk", r.get("pct_value_at_risk"), "pct", tone="#f0a860"),
        _kpi("noi_impact", "NOI impact", r.get("portfolio_noi_impact_pct"), "pct",
             hint="Insurance cost of the insured perils on the insured values (stated method), as a share of NOI"),
        _kpi("coverage", "Book scored", cov, "pct"),
        # the figure the Art. 8 filing prints: the share of turnover from Taxonomy-eligible activities (Turnover KPI)
        _kpi("taxonomy", "EU-Taxonomy eligible turnover", summary(snap.get("properties") or [])["pct"].get("eligible"),
             "pct", hint="Share of turnover from Taxonomy-eligible activities — the Turnover KPI of the EU Taxonomy "
                         "Art. 8 filing (Del. Reg. (EU) 2021/2178)"),
    ]
    es = r.get("energy_stranding") or {}
    if es.get("n_assessed"):
        kpis.append(_kpi("stranding", "Value at stranding risk", es.get("value_at_stranding_risk_eur"), "eur",
                         tone="#f0a860", hint=(es.get("gap") and f"Not computed — {es['gap']}") or
                         (f"Value the owner's stated brown discount per EPC grade takes (transition risk); "
                          f"{es.get('epc_coverage_pct')}% of the book is assessed (EPC and value on record)")))
    rc = r.get("resilience_capex") or {}
    if rc.get("available"):
        kpis.append(_kpi("resilience_capex", "Resilience capex to de-risk", _amount(rc.get("total_resilience_capex_eur")), "eur",
                         tone="#f0a860", hint=(f"Adaptation capex modelled against {_millions(rc.get('total_avoided_loss_eur'))} "
                                               f"avoided physical loss (benefit-cost {rc.get('portfolio_benefit_cost_ratio')}×), "
                                               "on the stated method")))
    anchor(kpis, _REIT_PRINTED)
    history = [_hist(h, [{"key": "taxonomy", "label": "Taxonomy-eligible turnover", "fmt": "pct",
                          "value": summary_of(h["payload"])["pct"].get("eligible")}])
               for h in _snapshot_history(session, org_id, REIT)]
    return {"framework": REIT, "supported": True, "label": "REIT physical-risk and Taxonomy KRIs",
            "kpis": kpis, "by_hazard": _by_hazard(snap), "history": history}


def insurer_kri(session: Session, org_id: str) -> dict:
    from api.routers.insurance import build_disclosure_snapshot
    from services.governance.insurer_solvency import modelled_1_in_200, natcat_block
    from services.governance.kri import _amount, _by_hazard, _kpi, _snapshot_history
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"])
    r = snap["rollup"]
    cov = round(100 * r.get("n_priced", 0) / r.get("n_policies", 1), 1) if r.get("n_policies") else 0
    kpis = [
        _kpi("sum_insured", "Sum insured", r.get("total_sum_insured_eur", 0) or 0, "eur"),
        _kpi("eal", "Expected annual loss", r.get("total_expected_annual_loss_eur"), "eur", tone="#fb7185"),
        _kpi("value_at_risk", "Sum insured at material physical risk", r.get("value_at_risk_eur"), "eur",
             hint="Sum insured at or above the stated at-risk level (method.at_risk_level)"),
        _kpi("coverage", "Policies priced", cov, "pct"),
    ]
    cat = r.get("catastrophe") or {}
    if cat.get("available"):
        rp_ = cat.get("pml_return_period")
        kpis.append(_kpi("cat_pml", f"Catastrophe PML (1-in-{rp_})" if rp_ else "Catastrophe PML", _amount(cat.get("pml_eur")), "eur",
                         tone="#fb7185", hint=cat.get("pml_gap") or ("Probable maximum loss — the single largest modelled "
                                              "event at your chosen return period, from the common-shock accumulation engine")))
    scr = snap.get("solvency_scr") or {}
    if scr.get("available"):
        kpis.append(_kpi("natcat_scr", "Modelled 1-in-200 nat-cat loss", _amount(modelled_1_in_200(scr)), "eur",
                         tone="#f0a860", hint="The 1-in-200 annual loss of the platform's catastrophe simulation on the "
                                              "undertaking's stated damage ratios and event probabilities — not an "
                                              "approved internal model; the standard formula is on the Solvency page"))
    reins = snap.get("reinsurance") or {}
    net = reins.get("net") or {}
    if reins.get("available") and net:
        kpis.append(_kpi("net_retention", "Net retention (post-reinsurance PML)", _amount(net.get("net_pml_eur")), "eur",
                         tone="#f0a860", hint=f"PML retained after the attested reinsurance treaty "
                                              f"({net.get('cession_ratio_pct')}% ceded)"))
    inv = snap.get("investments") or {}
    iv = inv.get("climate_var") or {}
    if inv.get("available") and iv.get("available"):
        kpis.append(_kpi("investment_var", "Investment climate VaR (99%)", _amount(iv.get("var99_eur")), "eur",
                         tone="#fb7185", hint=f"Combined physical+transition climate VaR on the insurer's own investment "
                                              f"book ({inv.get('coverage_pct')}% of positions scored) — the asset side"))
    anchor(kpis, _INSURER_PRINTED)
    history = [_hist(h, [{"key": "natcat_scr", "label": "Modelled 1-in-200 loss, gross", "fmt": "eur",
                          "value": (natcat_block(h["payload"]).get("natcat_scr") or {}).get("gross_1_in_200_eur")}])
               for h in _snapshot_history(session, org_id, INSURER)]
    return {"framework": INSURER, "supported": True, "label": "Insurer nat-cat KRIs",
            "kpis": kpis, "by_hazard": _by_hazard(snap), "history": history}


def holdings_kpis(session: Session, org_id: str) -> tuple[list[dict], list[dict]]:
    """The asset manager's holdings-book KRIs (climate VaR, concentration, taxonomy eligibility of value) — none is
    printed by the SFDR PAI statement, so each is live only — and the book's exposure by hazard."""
    from api.routers.assetmgmt import build_disclosure_snapshot
    from services.governance.kri import _by_hazard, _kpi
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"])
    r, tax, conc = snap.get("rollup", {}), snap.get("taxonomy", {}), snap.get("concentration", {})
    elig = (tax.get("eligible") or {}).get("value_eur", 0) or 0
    tax_total = sum((v or {}).get("value_eur", 0) or 0 for v in tax.values())
    cov = round(100 * r.get("n_scored", 0) / r.get("n_holdings", 1), 1) if r.get("n_holdings") else 0
    kpis = [
        _kpi("holdings_value", "Portfolio value (holdings book)", r.get("total_portfolio_value_eur", 0) or 0, "eur"),
        _kpi("climate_var", "Portfolio climate VaR", r.get("total_climate_var_eur"), "eur", tone="#fb7185",
             hint="Position value − climate-discounted value across the book"),
        _kpi("var_pct", "Climate VaR (% of book)", r.get("portfolio_climate_var_pct"), "pct", tone="#f0a860"),
        _kpi("holdings_coverage", "Holdings scored", cov, "pct"),
        _kpi("holdings_taxonomy", "EU-Taxonomy eligible (share of value)",
             round(100 * elig / tax_total, 1) if tax_total else 0, "pct"),
    ]
    if conc.get("available"):
        tr = conc.get("top_region") or {}
        cs = conc.get("common_shock") or {}
        kpis.append(_kpi("common_shock", "VaR in largest common-shock", conc.get("common_shock_var_pct_of_total"), "pct",
                         tone="#fb7185", hint=(f"Share of total climate VaR in the single largest common-shock cluster "
                                               f"({cs.get('hazard', '—')} in {cs.get('region', '—')}) — the "
                                               "concentration a single event exposes")))
        kpis.append(_kpi("top_region_conc", "Top-region concentration", tr.get("pct_of_book"), "pct", tone="#f0a860",
                         hint=(f"Largest single region: {tr.get('region', '—')}. Effective independent regions "
                               f"(1/HHI): {conc.get('effective_regions')} · hazards: {conc.get('effective_hazards')}")))
    anchor(kpis, {})
    return kpis, _by_hazard(snap)

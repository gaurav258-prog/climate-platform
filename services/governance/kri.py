"""Key Regulatory Indicator (KRI) dashboard — the regulator's-eye consolidated risk view.

One place for the headline physical-risk indicators of the book: how much value sits at High+ risk, the
share of the book, coverage, financed emissions and taxonomy eligibility, plus the same figures over the
org's filed history so a trend is visible. Current figures come from the live engine (the same source the
disclosure uses); the history comes from the immutable filed snapshots, so the trend is auditable.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session


def _kpi(key, label, value, fmt, tone=None, hint=None, integrated=False, integrated_note=None):
    # `integrated` = a regulator datapoint whose value comes from OUTSIDE this engine (e.g. GHG from the
    # customer's carbon tool, or Taxonomy alignment flags) — shown honestly rather than fabricated or blanked.
    # `kind` makes the data provenance explicit for the dashboard's computed-vs-integrated legend/filter.
    # It mirrors the canonical datapoint catalog's `coverage_source(lane)`: our engine + processed uploads
    # (compute/granular) → "computed"; a pre-calculated value the customer/vendor brings in (provided) →
    # "integrated". This is the SAME `integrated` flag that already drove the honest "—" rendering, now
    # surfaced as a first-class classification so every KRI is labelled ours-vs-brought-in.
    return {"key": key, "label": label, "value": value, "fmt": fmt, "tone": tone, "hint": hint,
            "integrated": integrated, "integrated_note": integrated_note,
            "kind": "integrated" if integrated else "computed"}


# the frameworks with a KRI builder, and their short picker labels (one org-type can report several)
_KRI_LABELS = {"bank_tcfd": "TCFD · Taxonomy", "bank_p3esg": "Pillar 3 ESG", "sfdr_pai": "SFDR PAI",
               "reit_tcfd": "TCFD · property", "insurer_climate": "Climate / NatCat", "esrs_pack": "ESRS E1·E3·E4",
               "assetmgmt_tcfd": "TCFD · holdings"}


def kri_frameworks(org_type: str | None) -> list[dict]:
    """The KRI frameworks an org-type can report on — the picker options on the KRI dashboard."""
    from services.governance.filings import available_frameworks
    return [{"framework": f["framework"], "label": _KRI_LABELS[f["framework"]]}
            for f in available_frameworks(org_type or "") if f["framework"] in _KRI_LABELS]


def kri(session: Session, org_id: str, framework: str) -> dict:
    if framework == "bank_tcfd":
        result = _bank_kri(session, org_id)
    elif framework == "bank_p3esg":
        result = _p3esg_kri(session, org_id)
    elif framework == "sfdr_pai":
        result = _sfdr_kri(session, org_id)
    elif framework == "reit_tcfd":
        result = _reit_kri(session, org_id)
    elif framework == "insurer_climate":
        result = _insurer_kri(session, org_id)
    elif framework == "assetmgmt_tcfd":
        result = _assetmgmt_kri(session, org_id)
    elif framework in ("csrd_e1", "esrs_pack"):
        result = _agri_kri(session, org_id, framework)
    else:
        return {"framework": framework, "supported": False,
                "message": "No KRI dashboard for this framework yet."}
    # grade every KPI against the org's appetite bands → green / amber / red (a monitored control, not a number)
    if result.get("supported") and result.get("kpis"):
        from services.governance import kri_regmap, kri_thresholds
        kri_thresholds.apply(session, org_id, result["framework"], result["kpis"])
        result["breaches"] = sum(1 for k in result["kpis"] if k.get("breached"))
        # regulator framing: name the supervisor/disclosure, tag each KRI with the datapoint it feeds, and
        # summarise submission-readiness (which core datapoints the regulator expects are covered)
        result["regulator"] = kri_regmap.regulator(result["framework"])
        result["readiness"] = kri_regmap.annotate(result["framework"], result["kpis"])
    return result


def _hplus(by_bucket: dict, key: str) -> float:
    return sum((by_bucket.get(b, {}).get(key, 0) or 0) for b in ("H", "VH"))


def _reit_kri(session: Session, org_id: str) -> dict:
    from api.routers.realestate import build_disclosure_snapshot
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"])
    r = snap["rollup"]
    tax = snap.get("taxonomy", {})
    total = r.get("total_value_eur", 0) or 0
    var = _hplus(r.get("by_bucket", {}), "value_eur")
    elig = (tax.get("eligible") or {}).get("value_eur", 0) or 0
    tax_total = sum((v or {}).get("value_eur", 0) or 0 for v in tax.values())
    cov = round(100 * r.get("n_scored", 0) / r.get("n_properties", 1), 1) if r.get("n_properties") else 0
    kpis = [
        _kpi("total_value", "Property book value", total, "eur"),
        _kpi("value_at_risk", "Value at risk (High+)", round(var), "eur", tone="#fb7185"),
        _kpi("pct_at_risk", "Share at risk", round(100 * var / total, 1) if total else 0, "pct", tone="#f0a860"),
        _kpi("noi_impact", "NOI impact", r.get("portfolio_noi_impact_pct"), "pct",
             hint="Modelled hit to net operating income"),
        _kpi("coverage", "Book scored", cov, "pct"),
        _kpi("taxonomy", "EU-Taxonomy eligible", round(100 * elig / tax_total, 1) if tax_total else 0, "pct"),
    ]
    # transition risk — energy-performance stranding (share of value below the rising minimum-EPC floor)
    es = r.get("energy_stranding") or {}
    if es.get("n_assessed"):
        kpis.append(_kpi("stranding", "Value below EPC floor", es.get("pct_portfolio_value_below_floor"), "pct",
                         tone="#f0a860", hint=f"Share of portfolio value below the modelled EPC-{es.get('floor_epc')} "
                                              f"minimum-to-let (transition/stranding risk); {es.get('epc_coverage_pct')}% "
                                              "of the book carries an EPC"))
    # adaptation — resilience capex to de-risk and the loss it avoids (benefit-cost)
    rc = r.get("resilience_capex") or {}
    if rc.get("available"):
        kpis.append(_kpi("resilience_capex", "Resilience capex to de-risk", round(rc.get("total_resilience_capex_eur") or 0), "eur",
                         tone="#f0a860", hint=(f"Adaptation capex modelled against {round((rc.get('total_avoided_loss_eur') or 0)/1e6,1)}m "
                                               f"avoided physical loss (benefit-cost {rc.get('portfolio_benefit_cost_ratio')}×); "
                                               f"{round((rc.get('taxonomy_adaptation_aligned_capex_eur') or 0)/1e6,1)}m Taxonomy adaptation-aligned")))
    by_hazard = _by_hazard(snap)
    history = [{"label": h["label"], "filing_id": h["filing_id"], "total_value": (h["payload"].get("rollup") or {}).get("total_value_eur"),
                "value_at_risk": _hplus((h["payload"].get("rollup") or {}).get("by_bucket", {}), "value_eur"),
                "pct_at_risk": None} for h in _snapshot_history(session, org_id, "reit_tcfd")]
    return {"framework": "reit_tcfd", "supported": True, "label": "REIT physical-risk KRIs",
            "kpis": kpis, "by_hazard": by_hazard, "history": history}


def _insurer_kri(session: Session, org_id: str) -> dict:
    from api.routers.insurance import build_disclosure_snapshot
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"])
    r = snap["rollup"]
    total = r.get("total_sum_insured_eur", 0) or 0
    var = _hplus(r.get("by_bucket", {}), "sum_insured_eur")
    cov = round(100 * r.get("n_priced", 0) / r.get("n_policies", 1), 1) if r.get("n_policies") else 0
    kpis = [
        _kpi("sum_insured", "Sum insured", total, "eur"),
        _kpi("eal", "Expected annual loss", r.get("total_expected_annual_loss_eur"), "eur", tone="#fb7185"),
        _kpi("loss_ratio", "Loss ratio", r.get("portfolio_loss_ratio_pct"), "pct", tone="#f0a860",
             hint="Expected annual loss ÷ gross premium"),
        _kpi("value_at_risk", "Sum insured at risk (High+)", round(var), "eur"),
        _kpi("coverage", "Policies priced", cov, "pct"),
    ]
    # Catastrophe PML — the correlated 1-in-N tail the summed EALs hide (read from the frozen snapshot).
    cat = r.get("catastrophe") or {}
    if cat.get("available"):
        kpis.append(_kpi("cat_pml", f"Catastrophe PML (1-in-{cat.get('pml_return_period')})", round(cat.get("pml_eur") or 0), "eur",
                         tone="#fb7185", hint="Probable maximum loss — the single largest modelled event at the chosen "
                                              "return period, from the common-shock accumulation engine"))
    # Solvency II NatCat capital — the 1-in-200 (99.5% VaR) modelled catastrophe charge (internal-model basis)
    scr = snap.get("solvency_scr") or {}
    if scr.get("available"):
        kpis.append(_kpi("natcat_scr", "NatCat SCR (99.5%, modelled)", round(scr.get("natcat_scr_eur") or 0), "eur",
                         tone="#f0a860", hint="Modelled 1-in-200 (99.5% VaR) catastrophe capital charge, internal-model "
                                              "basis; the standard-formula SCR uses EIOPA's prescribed regional factors "
                                              "(governed input to load)"))
    # Net-of-reinsurance retention — the loss that actually hits capital after ceding (illustrative program).
    reins = snap.get("reinsurance") or {}
    net = reins.get("net") or {}
    if reins.get("available") and net:
        kpis.append(_kpi("net_retention", "Net retention (post-reinsurance PML)", round(net.get("net_pml_eur") or 0), "eur",
                         tone="#f0a860", hint=f"PML retained after the illustrative reinsurance program "
                                              f"({net.get('cession_ratio_pct')}% ceded); the insurer configures their own "
                                              "program on the live workspace"))
    # the ASSET side — climate VaR on the insurer's own investment book (EIOPA/IFRS S2 require both sides)
    inv = snap.get("investments") or {}
    iv = inv.get("climate_var") or {}
    if inv.get("available") and iv.get("available"):
        kpis.append(_kpi("investment_var", "Investment climate VaR (99%)", round(iv.get("var99_eur") or 0), "eur",
                         tone="#fb7185", hint=f"Combined physical+transition climate VaR on the insurer's own investment "
                                              f"book ({inv.get('coverage_pct')}% of positions scored) — the asset side, "
                                              "EIOPA/IFRS S2"))
    by_hazard = _by_hazard(snap)
    history = [{"label": h["label"], "filing_id": h["filing_id"], "total_value": (h["payload"].get("rollup") or {}).get("total_sum_insured_eur"),
                "value_at_risk": (h["payload"].get("rollup") or {}).get("total_expected_annual_loss_eur"),
                "pct_at_risk": None} for h in _snapshot_history(session, org_id, "insurer_climate")]
    return {"framework": "insurer_climate", "supported": True, "label": "Insurer climate/NatCat KRIs",
            "kpis": kpis, "by_hazard": by_hazard, "history": history}


def _assetmgmt_kri(session: Session, org_id: str) -> dict:
    from api.routers.assetmgmt import build_disclosure_snapshot
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"])
    r = snap.get("rollup", {})
    tax = snap.get("taxonomy", {})
    conc = snap.get("concentration", {})
    total = r.get("total_portfolio_value_eur", 0) or 0
    elig = (tax.get("eligible") or {}).get("value_eur", 0) or 0
    tax_total = sum((v or {}).get("value_eur", 0) or 0 for v in tax.values())
    cov = round(100 * r.get("n_scored", 0) / r.get("n_holdings", 1), 1) if r.get("n_holdings") else 0
    kpis = [
        _kpi("total_value", "Portfolio value", total, "eur"),
        _kpi("climate_var", "Portfolio climate VaR", r.get("total_climate_var_eur"), "eur", tone="#fb7185",
             hint="Position value − climate-discounted value across the book"),
        _kpi("var_pct", "Climate VaR (% of book)", r.get("portfolio_climate_var_pct"), "pct", tone="#f0a860"),
        _kpi("coverage", "Holdings scored", cov, "pct"),
        _kpi("taxonomy", "EU-Taxonomy eligible", round(100 * elig / tax_total, 1) if tax_total else 0, "pct"),
    ]
    # concentration — the diversification diagnostic (common-shock share + top-region share)
    if conc.get("available"):
        tr = conc.get("top_region") or {}
        kpis.append(_kpi("common_shock", "VaR in largest common-shock", conc.get("common_shock_var_pct_of_total"), "pct",
                         tone="#fb7185", hint=(f"Share of total climate VaR in the single largest common-shock cluster "
                                               f"({(conc.get('common_shock') or {}).get('hazard', '—')} in "
                                               f"{(conc.get('common_shock') or {}).get('region', '—')}) — the "
                                               "concentration a single event exposes")))
        kpis.append(_kpi("top_region_conc", "Top-region concentration", tr.get("pct_of_book"), "pct", tone="#f0a860",
                         hint=(f"Largest single region: {tr.get('region', '—')}. Effective independent regions "
                               f"(1/HHI): {conc.get('effective_regions')} · hazards: {conc.get('effective_hazards')}")))
    by_hazard = _by_hazard(snap)
    history = [{"label": h["label"], "filing_id": h["filing_id"],
                "total_value": (h["payload"].get("rollup") or {}).get("total_portfolio_value_eur"),
                "value_at_risk": (h["payload"].get("rollup") or {}).get("total_climate_var_eur"),
                "pct_at_risk": (h["payload"].get("rollup") or {}).get("portfolio_climate_var_pct")}
               for h in _snapshot_history(session, org_id, "assetmgmt_tcfd")]
    return {"framework": "assetmgmt_tcfd", "supported": True, "label": "Asset-manager holdings KRIs",
            "kpis": kpis, "by_hazard": by_hazard, "history": history}


def _agri_kri(session: Session, org_id: str, framework: str = "csrd_e1") -> dict:
    """ESRS E1 (climate) KRIs for an agri / manufacturer book — the real E1-9 climate financial effects from
    build_e1_report (own operations + upstream sourcing), NOT GHG. GHG accounting (Scope 1/2/3) and energy are
    deliberately out of scope here — the platform computes the physical / nature ESRS and integrates GHG from
    the customer's carbon-accounting tool — so we never surface a fabricated emissions number."""
    from api.routers.supply import _plots_with_hazard
    from services.governance.reporting_settings import get_settings
    from services.intelligence.csrd_e1 import build_e1_report
    s = get_settings(session, org_id)
    e1 = build_e1_report(session, org_id, s["scenario"], s["horizon"])
    oo = e1.get("own_operations", {}) or {}
    us = e1.get("upstream_sourcing", {}) or {}
    fe = e1.get("financial_effects", {}) or {}
    plots = list(_plots_with_hazard(session, org_id, s["scenario"], s["horizon"]))
    scored = sum(1 for p in plots if p["hazard_score"] is not None)
    asset = oo.get("asset_value_eur") or 0
    asset_at_risk = oo.get("asset_value_at_risk_eur") or 0

    kpis = [
        _kpi("asset_value", "Own-site asset value", asset, "eur", hint="Own operations — sites in scope"),
        _kpi("asset_at_risk", "Own-site value at risk", asset_at_risk, "eur",
             hint="Site asset value in severe hazard bands, at the reporting pathway"),
        _kpi("pct_at_risk", "Share of sites at risk", round(100 * asset_at_risk / asset, 1) if asset else 0, "pct"),
        _kpi("business_interruption", "Business interruption", oo.get("business_interruption_eur"), "eur",
             hint="v0 illustrative — throughput × expected downtime by hazard band"),
        _kpi("ingredient_spend", "Ingredient spend", us.get("ingredient_spend_eur"), "eur", hint="Upstream sourcing spend"),
        _kpi("cogs_at_risk", "COGS at risk (published)", fe.get("cogs_at_risk_published_eur"), "eur",
             hint="Upstream COGS at risk where the hazard→yield chain validates (r² ≥ 0.40)"),
        _kpi("cogs_withheld", "Exposure mapped · € withheld", fe.get("exposure_mapped_but_withheld_eur"), "eur",
             hint="Spend exposed but the euro withheld pending calibration — honest, not zero"),
        _kpi("coverage", "Plots scored", round(100 * scored / len(plots), 1) if plots else 0, "pct"),
        _kpi("ghg_emissions", "GHG emissions (Scope 1-3)", None, "num", integrated=True, integrated_note="carbon tool",
             hint="ESRS E1-6 GHG accounting is integrated from your carbon-accounting tool — Tellumen computes the physical/nature ESRS, not the emissions inventory."),
    ]
    # supply-shock concentration — is the sourcing book concentrated in one crop / one hazard (diversification lens)
    try:
        from services.intelligence.supply_cogs import project_org_supply
        from services.intelligence.supply_concentration import supply_concentration
        conc = supply_concentration(project_org_supply(session, org_id, scenario=s["scenario"], time_horizon=s["horizon"]).commodities)
        if conc.get("available"):
            cshock = conc.get("common_shock") or {}
            kpis.append(_kpi("supply_common_shock", "Spend in largest common shock", conc.get("common_shock_pct_of_spend"), "pct",
                             tone="#fb7185", hint=(f"Share of sourcing spend exposed to the single biggest common shock "
                                                   f"({cshock.get('hazard', '—')} across {cshock.get('n_commodities', 0)} crops) — "
                                                   "a bad season on this one hazard hits this much of the book at once")))
            kpis.append(_kpi("supply_diversification", "Effective independent crops", conc.get("effective_commodities"), "num",
                             tone="#f0a860", hint=(f"1/HHI over sourcing spend — the book behaves like this many equally-weighted "
                                                   f"independent crops (of {len(conc.get('by_commodity') or [])} sourced). "
                                                   f"Effective independent hazards: {conc.get('effective_hazards')}")))
    except Exception:  # noqa: BLE001 — a missing supply signal must not sink the KRI set
        pass
    # Separate regional frost-severity indicator (E1 physical hazard) — standalone, shown only where the
    # org sources from a region we hold frost data for. A HAZARD-extent number, NOT a euro (coffee € stays
    # held); kept distinct from the per-plot score and from the COGS figures above.
    from services.intelligence.frost_severity import org_frost_severity
    for fr in org_frost_severity(session, org_id):
        band = fr.get("latest_band", "unknown")
        tone = {"severe": "#fb7185", "elevated": "#f0a860", "normal": "#4ade80"}.get(band)
        severe = fr.get("severe_years") or []
        kpis.append(_kpi(
            "frost_severity", f"Frost severity · {fr['label']}",
            round((fr.get("latest_extent") or 0) * 100, 1), "pct", tone=tone,
            hint=(f"Winter {fr['latest_year']}: {fr['latest_extent']:.0%} of the belt below "
                  f"{fr['threshold_c']:.0f}°C ({band}). Worst on record {fr['worst_year']} "
                  f"({fr['worst_extent']:.0%}); {len(severe)} severe frost(s) in {fr['n_years']} yrs"
                  + (f", last {severe[-1]}" if severe else "")
                  + ". Regional frost HAZARD severity from ERA5 — a separate signal, not the (held) coffee €.")))
    label = "ESRS E1 climate KRIs"
    # The full nature pack (esrs_pack) also carries E3 Water and E4 Biodiversity — real values from the same
    # engine (E3 = hazard-exposure derived; E4 = EUDR deforestation determinations), NOT measured water use.
    if framework == "esrs_pack":
        from services.intelligence.esrs_nature import build_esrs_pack
        tp = {t.get("topic"): t for t in (build_esrs_pack(session, org_id, s["scenario"], s["horizon"]).get("topics") or [])}
        e3u = (tp.get("E3", {}) or {}).get("upstream", {}) or {}
        e4 = tp.get("E4", {}) or {}
        kpis += [
            _kpi("water_plots_stressed", "Plots water-stressed", e3u.get("plots_water_stressed"), "num",
                 hint="Plots at water-stress score ≥ 40 · ESRS E3 (hazard-exposure derived)"),
            _kpi("water_spend_exposed", "Spend water-exposed", e3u.get("spend_exposed_eur"), "eur",
                 hint="Upstream spend on water-stressed plots · ESRS E3"),
            _kpi("water_peak", "Peak water-stress", e3u.get("peak_score"), "num",
                 hint="Worst standing water-stress score (0-100) · ESRS E3"),
            _kpi("deforestation_free_pct", "Deforestation-free", e4.get("deforestation_free_pct_of_determined"), "pct",
                 hint="Share of determined plots deforestation-free vs the EUDR cutoff · ESRS E4"),
            _kpi("non_compliant", "Non-compliant plots", e4.get("non_compliant"), "num",
                 hint="Plots with post-cutoff deforestation · ESRS E4 / EUDR"),
            _kpi("forest_loss_ha", "Post-cutoff forest loss", e4.get("post_cutoff_forest_loss_ha"), "ha",
                 hint="Hectares of forest lost after the 2020 EUDR cutoff · ESRS E4"),
        ]
        # ESRS E4 — sites/plots in or near a Natura 2000 protected area (free-gov EEA feed, H3 overlap)
        from services.intelligence.protected_area import protected_area_exposure
        pa = protected_area_exposure(session, org_id)
        if pa["cells_loaded"] > 0:
            in_pa = pa["sites"]["in_protected"] + pa["plots"]["in_protected"]
            exposed_m = round((pa["sites"]["value_in_eur"] + pa["plots"]["spend_in_eur"]) / 1e6, 1)
            _names = {"natura2000": "Natura 2000 (© EEA)", "osm": "OpenStreetMap (ODbL)", "wdpa": "WDPA",
                      "wdoecm": "WD-OECM", "kba": "KBA"}
            src = " · ".join(_names.get(d, d) for d in pa["datasets"]) or "protected areas"
            kpis.append(_kpi("protected_area", "In protected areas", in_pa, "num",
                             hint=f"Own sites + sourcing plots in/near a protected area · source: {src} · €{exposed_m}m exposed · ESRS E4"))
        label = "ESRS E1·E3·E4 nature KRIs"

    # by-hazard drives the drill (which reads _plots_with_hazard), so keep it plot-hazard keyed
    haz: dict = {}
    for p in plots:
        if p.get("top_hazard") and (p["hazard_score"] or 0) >= 50:
            g = haz.setdefault(p["top_hazard"], {"value": 0.0, "score": 0.0})
            g["value"] += p["spend_eur"] or 0
            g["score"] = max(g["score"], p["hazard_score"] or 0)
    by_hazard = sorted([{"hazard": h, "value": round(v["value"]), "score": round(v["score"], 1)}
                        for h, v in haz.items() if v["value"] > 0], key=lambda x: -x["value"])
    return {"framework": framework, "supported": True, "label": label,
            "kpis": kpis, "by_hazard": by_hazard, "history": [],
            "scope_note": "Physical & nature ESRS (E1 climate financial effects · E3 water · E4 deforestation). "
                          "GHG accounting (Scope 1/2/3) and energy are integrated from your carbon-accounting tool, "
                          "not computed here."}


def _by_hazard(snap: dict) -> list[dict]:
    return sorted([{"hazard": h, "value": b.get("exposed_value_eur", 0), "score": b.get("max_score", 0)}
                   for h, b in (snap.get("by_hazard") or {}).items() if (b.get("exposed_value_eur") or 0) > 0],
                  key=lambda x: -x["value"])


# noun per framework for the hazard drill
_NOUN = {"bank_tcfd": "assets", "bank_p3esg": "assets", "reit_tcfd": "properties", "insurer_climate": "policies"}


def _live_snapshot(session: Session, org_id: str, framework: str, scenario: str, horizon: str) -> dict:
    if framework in ("bank_tcfd", "bank_p3esg"):
        from api.routers.bank import build_disclosure_snapshot
    elif framework == "reit_tcfd":
        from api.routers.realestate import build_disclosure_snapshot
    elif framework == "insurer_climate":
        from api.routers.insurance import build_disclosure_snapshot
    else:
        return {}
    return build_disclosure_snapshot(session, org_id, scenario, horizon)


def kri_hazard(session: Session, org_id: str, framework: str, hazard: str) -> dict:
    """The entities contributing a hazard's exposure (live) — the drill under a KRI by-hazard bar."""
    from services.governance.filing_lineage import _LIST_CFG
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    cfg = _LIST_CFG.get(framework)
    if cfg:
        snap = _live_snapshot(session, org_id, framework, s["scenario"], s["horizon"])
        ents = []
        for e in snap.get(cfg["list"], []):
            hz = next((h for h in e.get("hazards", []) if h.get("hazard") == hazard
                       and h.get("bucket") in ("H", "VH")), None)
            if hz:
                ents.append({"name": e.get(cfg["name"]), "value": e.get(cfg["value"]),
                             "h3_cell": e.get("h3_cell"), "country": e.get("country"), "score": hz.get("score")})
        ents.sort(key=lambda x: -(x["value"] or 0))
        return {"supported": True, "hazard": hazard, "noun": _NOUN.get(framework, "items"), "entities": ents[:100]}
    if framework in ("csrd_e1", "esrs_pack"):
        from api.routers.supply import _plots_with_hazard
        ents = [{"name": p["plot_name"], "value": p["spend_eur"], "h3_cell": p.get("h3_cell"),
                 "country": p.get("country"), "score": p["hazard_score"]}
                for p in _plots_with_hazard(session, org_id, s["scenario"], s["horizon"])
                if p.get("top_hazard") == hazard and (p["hazard_score"] or 0) >= 50]
        ents.sort(key=lambda x: -(x["value"] or 0))
        return {"supported": True, "hazard": hazard, "noun": "sourcing plots", "entities": ents[:100]}
    return {"supported": False, "hazard": hazard, "entities": []}


# ── KRI drill-down: the underlying data + methodology + trend + composition behind one KRI ──────────────
# Exposure KRIs decompose by hazard; the rest by their own natural breakdown (emissions by scope, coverage
# scored/unscored, taxonomy eligible/not). Everything here is derived from the SAME live snapshot the KRI
# tile is computed from — no separate or fabricated data.
_EXPOSURE_KEYS = {"total_value", "value_at_risk", "pct_at_risk", "asset_value", "asset_at_risk",
                  "sum_insured", "eal", "cogs_at_risk", "cogs_withheld", "ingredient_spend", "value_exposed"}
_HIST_FIELD = {"total_value": "total_value", "value_at_risk": "value_at_risk", "pct_at_risk": "pct_at_risk"}
# forward-looking + physical-split KRIs also earn the "explore forward in Analytics" action
_FORWARD_KEYS = {"forward_share", "acute_share", "chronic_share"}

# Plain-language, factual "how it's computed" per KRI. Where a key is absent the UI falls back to the tile's
# own hint. Written to be honest about calibration gates and integrated (client-provided) datapoints.
_METHODOLOGY = {
    "total_value": "Total euro exposure of the book in scope for this filing, summed from your uploaded book.",
    "value_at_risk": "Exposure sitting in the top two physical-risk severity bands (High + Very High), in euro. Scored per asset by Tellumen's hazard engine, then aggregated.",
    "pct_at_risk": "Value at risk as a share of total book value — how concentrated the book is in High+ physical risk.",
    "acute_share": "Share of the book in the top two bands (High + Very High) whose driver is an ACUTE, event-driven peril — flood, storm, wildfire, frost, acute heat. This is the sudden-loss / provisioning lens of Pillar 3 Template 5; an exposure can also count as chronic.",
    "chronic_share": "Share of the book in the top two bands whose driver is a CHRONIC, gradual peril — drought, chronic heat, coastal/sea-level, water stress. This is the long-run repricing lens of Template 5; the acute and chronic shares overlap where an exposure faces both.",
    "forward_share": "Projected share of the book crossing into High+ at the furthest modelled horizon under a warming pathway (per your reporting-settings scenario, or Disorderly 2°C). The forward early-warning to compare against today's point-in-time share.",
    "sector_concentration": "Share of the book in the EBA high-climate-impact sectors (NACE sections A–H and L), with the single most-concentrated sector called out. Concentration in these sectors is the axis Pillar 3 Templates 1 & 5 are organised around and a standard prudential concentration control.",
    "p3_alignment": "Pillar 3 Template 3 — the gross-weighted distance of the book's counterparty CO₂-intensity to the IEA Net-Zero-by-2050 2030 pathway per sector: 100×((current intensity − IEA 2030 target)/IEA 2030 target). Tellumen holds the IEA benchmark and does the calculation; the counterparty physical intensity (gCO₂/kWh, tCO₂/t…) is a vendor/counterparty feed, so this reads '—' until that feed is provided. A TCFD-not-required, Pillar-3-specific indicator.",
    "p3_top20": "Pillar 3 Template 4 — share of the book lent to the world's 20 most carbon-intensive companies (the Carbon Majors list), matched by counterparty identity. Policy action against top emitters can deteriorate their creditworthiness, so this is a concentrated transition-credit indicator prescribed by Pillar 3 (not TCFD).",
    "coverage": "Share of the book carrying a physical-risk score on the golden source. Unscored exposure is excluded from the risk figures, never assumed safe.",
    "fin_emissions": "PCAF-attributed financed emissions (Scope 1–3, tCO₂e): counterparty emissions weighted by your attribution share, with a NACE-intensity estimate filling gaps where a counterparty figure is missing.",
    "taxonomy": "EU Taxonomy Article 8 eligible share — the portion of the book in Taxonomy-eligible activities (the GAR numerator's eligibility leg), from your book's activity classification.",
    "gar": "The Green Asset Ratio needs the Taxonomy-ALIGNED share (substantial contribution + DNSH + minimum safeguards) that you determine per exposure. Only eligibility is computed here; alignment is your input, so this reads '—' until provided.",
    "noi_impact": "Physical-risk drag on net operating income — the modelled climate insurance premium as a share of NOI.",
    "sum_insured": "Total sum insured across the underwriting book in scope.",
    "eal": "Expected annual loss — probability-weighted scenario loss across the book, from the CLIMADA-style mean-damage-ratio × per-peril occurrence frequency.",
    "loss_ratio": "Modelled claims-vs-premiums (NatCat loss ratio) implied by the current hazard exposure of the book.",
    "asset_value": "Book value of your own operating sites in scope.",
    "asset_at_risk": "Own-site value in the top two physical-risk bands (High + Very High).",
    "cogs_at_risk": "Cost-of-goods-sold at risk that clears the r²≥0.40 calibration gate — published only where the hazard→yield chain validates for that crop × origin.",
    "cogs_withheld": "Sourcing spend exposed to hazard whose euro impact is honestly WITHHELD because the hazard→yield link hasn't cleared the calibration gate — mapped, not fabricated.",
    "ingredient_spend": "Total upstream sourcing (ingredient) spend in scope.",
    "ghg_emissions": "GHG Scope 1–3 — integrated from your carbon-accounting tool. Tellumen computes the physical/nature ESRS, not your emissions inventory.",
    "deforestation_free_pct": "Share of determined sourcing plots that are deforestation-free against the 2020 EUDR cutoff, from per-plot satellite forest-loss determinations.",
    "non_compliant": "Sourcing plots with post-2020 forest loss — non-compliant under EUDR.",
    "protected_area": "Own sites / sourcing plots in or within 1 km of a protected area, computed from the loaded protected-area datasets.",
    "frost_severity": "Regional frost severity — the fraction of the sourcing belt whose winter minimum "
                      "temperature fell to a crop-damaging level (≤2°C at 2m screen height), from Copernicus "
                      "ERA5 raw-hourly data. A SEPARATE physical-hazard extent metric, not a euro: the "
                      "frost→yield link does not clear the r²≥0.40 calibration gate at any resolution, so this "
                      "reports how severe the frost season was — with the worst year and severe-frost frequency "
                      "on record for context — rather than a financial figure.",
    "pai_emissions": "SFDR PAI 1 — total financed GHG emissions (Scope 1–3, tCO₂e) across the fund's value-weighted holdings.",
    "carbon_footprint": "SFDR PAI 2 — financed emissions per €M invested.",
    "waci": "SFDR PAI 3 — weighted-average carbon intensity (tCO₂e per €M investee revenue).",
    "fossil_fuel": "SFDR PAI 4 — share of fund value in companies active in the fossil-fuel sector.",
    "non_renewable": "SFDR PAI 5 — share of non-renewable energy consumption / production.",
}


def kri_detail(session: Session, org_id: str, framework: str, kri_key: str) -> dict:
    """The drill behind one KRI tile: the tile itself (value, appetite, provenance, regulator datapoint),
    a plain-language methodology, its trend across filed history where tracked, and its composition
    (by-hazard / by-scope / scored-unscored / eligible-not) — all from the same live snapshot."""
    result = kri(session, org_id, framework)
    if not result.get("supported"):
        return {"supported": False, "message": result.get("message", "unsupported")}
    kpi = next((k for k in result.get("kpis", []) if k["key"] == kri_key), None)
    if not kpi:
        return {"supported": False, "message": "unknown KRI"}
    hf = _HIST_FIELD.get(kri_key)
    trend = [{"label": h["label"], "value": h.get(hf), "filing_id": h.get("filing_id")}
             for h in (result.get("history") or []) if hf and h.get(hf) is not None] if hf else []
    return {
        "supported": True, "framework": framework, "kpi": kpi,
        "regulator": result.get("regulator"),
        "methodology": _METHODOLOGY.get(kri_key),
        "trend": {"points": trend, "fmt": kpi.get("fmt")},
        "projection": _kri_projection(session, org_id, framework, kri_key, kpi),
        "composition": _kri_composition(session, org_id, framework, kri_key, result),
        "drivers": _kri_drivers(session, org_id, framework, kri_key),
        "actions": {
            "analytics": (kri_key in _EXPOSURE_KEYS or kri_key in _FORWARD_KEYS) and framework in ("bank_tcfd", "bank_p3esg", "reit_tcfd"),
            "provide": kpi.get("kind") == "integrated",
        },
    }


# Physical/forward KRIs get a forward trajectory chart (value across horizons under a warming pathway, with
# an act-vs-inaction band and the appetite thresholds) — the "when do we cross appetite" decision view.
_PROJECTION_KEYS = {"value_at_risk", "pct_at_risk", "forward_share"}


def _kri_projection(session: Session, org_id: str, framework: str, kri_key: str, kpi: dict) -> dict | None:
    if kri_key not in _PROJECTION_KEYS or framework not in ("bank_tcfd", "bank_p3esg", "reit_tcfd"):
        return None
    try:
        from services.governance.reporting_settings import get_settings
        from services.intelligence.forward_risk import forward_risk
        vert = {"reit_tcfd": "realestate"}.get(framework, "banking")
        s = get_settings(session, org_id)
        scen = s["scenario"] if s.get("scenario") and s["scenario"] != "baseline" else "disorderly_2c"
        fr = forward_risk(session, org_id, vert, scen)
        book = fr.get("book_eur") or 0
        is_pct = kri_key in ("pct_at_risk", "forward_share")
        pts = []
        for t in fr.get("trajectory") or []:
            band = t.get("at_risk_band_eur") or [t.get("at_risk_eur"), t.get("at_risk_eur")]
            to = (lambda v: round(100 * v / book, 1) if book else 0) if is_pct else (lambda v: round(v))
            pts.append({"horizon": t.get("horizon"),
                        "value": t.get("at_risk_pct") if is_pct else round(t.get("at_risk_eur") or 0),
                        "lo": to(band[0]), "hi": to(band[1])})
        if len(pts) < 2:
            return None
        return {"points": pts, "unit": "pct" if is_pct else "eur",
                "warn": kpi.get("amber"), "breach": kpi.get("red"),
                "scenario": scen.replace("_", " "),
                "note": "Central estimate of value exposed at High+ across horizons under " + scen.replace("_", " ")
                        + "; the shaded band is the CMIP6/AR6 climate-model uncertainty range (lower–upper "
                        + "confidence bound of the hazard scores), not a best/worst policy case."}
    except Exception:  # noqa: BLE001 — a missing projection must not break the drawer
        return None


# KRIs whose most-granular drill is the individual exposures (assets) behind the number.
_DRIVER_KEYS = {"total_value", "value_at_risk", "pct_at_risk", "acute_share", "chronic_share",
                "forward_share", "sector_concentration", "fin_emissions"}


def _kri_drivers(session: Session, org_id: str, framework: str, kri_key: str,
                 seg_type: str | None = None, seg_value: str | None = None) -> dict | None:
    """The most granular view: the individual exposures (assets) behind a KRI, largest-contribution first —
    the actual names a risk officer acts on, each carrying its asset id so the row opens the asset detail.
    Without a segment, the filter follows the KRI. With a segment (from a click on a composition bar) the
    filter narrows to that slice: seg_type 'scope' (emissions Scope 1/2/3), 'hazard' (High+ on one peril),
    or 'sector' (one NACE section). Only for bank/REIT books; never fabricated."""
    if framework not in ("bank_tcfd", "bank_p3esg", "reit_tcfd"):
        return None
    if not seg_type and kri_key not in _DRIVER_KEYS:
        return None
    from services.governance.pillar3_templates import HIGH_CLIMATE_NACE, _asset_hits, _section
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = _live_snapshot(session, org_id, framework, s["scenario"], s["horizon"])
    assets = (snap or {}).get("assets") or []
    if not assets:
        return None
    def _val(a):
        return a.get("value_eur") or a.get("outstanding_loan_balance_eur") or 0
    def high(a):
        return (a.get("headline_bucket") in ("H", "VH"))

    if seg_type == "scope" and seg_value in ("1", "2", "3"):
        def keep(a):
            return (a.get(f"ghg{seg_value}") or 0) > 0
        def weight(a):
            return a.get(f"ghg{seg_value}") or 0
        unit = "num"
    elif seg_type == "hazard" and seg_value:
        def keep(a):
            return any(h.get("hazard") == seg_value and h.get("bucket") in ("H", "VH") for h in (a.get("hazards") or []))
        weight, unit = _val, "eur"
    elif seg_type == "sector" and seg_value:
        def keep(a):
            return _section(a.get("nace_code")) == seg_value
        weight, unit = _val, "eur"
    else:                                             # KRI-scoped default
        def keep(a):
            if kri_key in ("value_at_risk", "pct_at_risk", "forward_share"):
                return high(a)
            if kri_key == "acute_share":
                return _asset_hits(a)[1]
            if kri_key == "chronic_share":
                return _asset_hits(a)[0]
            if kri_key == "sector_concentration":
                return _section(a.get("nace_code")) in HIGH_CLIMATE_NACE
            return True                               # total_value / fin_emissions → whole book
        weight = (lambda a: sum((a.get(f"ghg{i}") or 0) for i in (1, 2, 3))) if kri_key == "fin_emissions" else _val
        unit = "num" if kri_key == "fin_emissions" else "eur"

    rows = [a for a in assets if keep(a) and weight(a) > 0]
    rows.sort(key=weight, reverse=True)
    items = [{
        "id": a.get("asset_id"), "name": a.get("asset_name") or a.get("asset_id"), "sector": a.get("sector"),
        "country": a.get("country"), "nace": a.get("nace_code"),
        "value": round(weight(a)), "hazard": a.get("headline_hazard"),
        "bucket": a.get("headline_bucket"), "score": a.get("headline_score"),
    } for a in rows[:8]]
    return {"unit": unit, "total_count": len(rows), "items": items} if items else None


def _kri_composition(session: Session, org_id: str, framework: str, kri_key: str, result: dict) -> dict | None:
    """The real breakdown behind a KRI — never fabricated; returns None when no honest decomposition exists."""
    if kri_key in _EXPOSURE_KEYS and result.get("by_hazard"):
        return {"type": "hazard", "unit": "eur",
                "items": [{"label": h["hazard"], "value": h["value"], "score": h.get("score")}
                          for h in result["by_hazard"]]}
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = _live_snapshot(session, org_id, framework, s["scenario"], s["horizon"])
    if not snap:
        return None
    if kri_key == "fin_emissions":
        em = snap.get("financed_emissions_tco2e", {}) or {}
        items = [{"label": f"Scope {i}", "value": round(em.get(f"scope{i}") or 0)} for i in (1, 2, 3)]
        return {"type": "scope", "unit": "num", "items": items} if sum(x["value"] for x in items) > 0 else None
    if kri_key == "coverage":
        r = snap.get("rollup", {}) or {}
        n, sc = r.get("n_assets") or 0, r.get("n_scored") or 0
        return {"type": "coverage", "unit": "num",
                "items": [{"label": "Scored", "value": sc}, {"label": "Not yet scored", "value": max(0, n - sc)}]} if n else None
    if kri_key == "taxonomy":
        tax = snap.get("taxonomy", {}) or {}
        elig = (tax.get("eligible") or {}).get("value_eur", 0) or 0
        total = sum((v or {}).get("value_eur", 0) or 0 for v in tax.values())
        return {"type": "taxonomy", "unit": "eur",
                "items": [{"label": "Eligible", "value": round(elig)}, {"label": "Not eligible", "value": round(max(0, total - elig))}]} if total else None
    # acute / chronic peril exposure — the value-weighted hazard breakdown WITHIN that peril category
    if kri_key in ("acute_share", "chronic_share"):
        from services.governance.pillar3_templates import (
            _HIGH_BUCKETS,
            ACUTE_HAZARDS,
            CHRONIC_HAZARDS,
        )
        cats = ACUTE_HAZARDS if kri_key == "acute_share" else CHRONIC_HAZARDS
        by_h: dict[str, float] = {}
        for a in snap.get("assets") or []:
            v = a.get("value_eur") or 0
            if not v:
                continue
            for h in a.get("hazards") or []:
                if h.get("hazard") in cats and h.get("bucket") in _HIGH_BUCKETS:
                    by_h[h["hazard"]] = by_h.get(h["hazard"], 0.0) + v
        items = sorted(({"label": k, "value": round(v)} for k, v in by_h.items()), key=lambda x: -x["value"])
        return {"type": "hazard", "unit": "eur", "items": items} if items else None
    # climate-sector concentration — value by NACE section (the concentration axis of Templates 1 & 5)
    if kri_key == "sector_concentration":
        from services.governance.pillar3_templates import (
            HIGH_CLIMATE_NACE,
            NACE_SECTIONS,
            concentration_split,
        )
        cs = concentration_split(snap.get("assets") or [])
        items = sorted(
            ({"label": f"{sec} · {NACE_SECTIONS.get(sec, 'Unclassified')}"[:34], "value": round(val)}
             for sec, val in cs["by_sector"].items() if sec in HIGH_CLIMATE_NACE),
            key=lambda x: -x["value"])
        return {"type": "sector", "unit": "eur", "items": items} if items else None
    # forward share — the projected at-risk trajectory across horizons under the warming pathway
    if kri_key == "forward_share":
        try:
            from services.intelligence.forward_risk import forward_risk
            scen = s["scenario"] if s.get("scenario") and s["scenario"] != "baseline" else "disorderly_2c"
            traj = forward_risk(session, org_id, "banking", scen).get("trajectory") or []
            items = [{"label": t.get("horizon"), "value": t.get("at_risk_pct") or 0} for t in traj]
            return {"type": "horizon", "unit": "pct", "items": items} if len(items) >= 2 else None
        except Exception:  # noqa: BLE001
            return None
    return None


def _snapshot_history(session: Session, org_id: str, framework: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT rs.version, rs.reporting_basis, rs.payload, rf.period_label, rf.filing_id::text AS filing_id
        FROM report_snapshots rs
        JOIN regulatory_filing rf ON rf.snapshot_id = rs.snapshot_id
        WHERE rs.org_id = :o AND rs.report_type = :fw
        ORDER BY rf.period_end, rs.version
    """), {"o": org_id, "fw": framework}).mappings().all()
    out = []
    for r in rows:
        p = r["payload"]
        if isinstance(p, str):
            p = json.loads(p)
        out.append({"label": f'{r["period_label"]} v{r["version"]}', "payload": p, "filing_id": r["filing_id"]})
    return out


def _bank_kri(session: Session, org_id: str) -> dict:
    from api.routers.bank import build_disclosure_snapshot
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"])
    r = snap.get("rollup", {})
    em = snap.get("financed_emissions_tco2e", {})
    tax = snap.get("taxonomy", {})
    total = r.get("total_value_eur", 0) or 0
    elig = (tax.get("eligible") or {}).get("value_eur", 0) or 0
    tax_total = sum((v or {}).get("value_eur", 0) or 0 for v in tax.values())
    cov = round(100 * r.get("n_scored", 0) / r.get("n_assets", 1), 1) if r.get("n_assets") else 0

    # Decision / concentration KRIs computed from the same per-asset book the Pillar 3 templates use.
    # Acute vs chronic split (Template 5), climate-sector concentration (the NACE axis of Templates 1 & 5),
    # and the forward early-warning (projected share crossing High+). Nothing new-sourced.
    from services.governance.pillar3_templates import concentration_split
    cs = concentration_split(snap.get("assets") or [])
    acute_val, chronic_val, hci_val = cs["acute_val"], cs["chronic_val"], cs["high_climate_val"]
    top_sec, top_val = cs["top_sector"], cs["top_sector_val"]
    def _share(x):
        return round(100 * x / total, 1) if total else 0

    # Forward early-warning: projected share-at-risk at the furthest horizon under a warming pathway.
    fwd_share = fwd_note = None
    try:
        from services.intelligence.forward_risk import forward_risk
        scen = s["scenario"] if s.get("scenario") and s["scenario"] != "baseline" else "disorderly_2c"
        traj = (forward_risk(session, org_id, "banking", scen).get("trajectory") or [])
        fut = [t for t in traj if t.get("horizon") != "current"]
        if fut:
            pt = fut[-1]
            fwd_share = pt.get("at_risk_pct")
            fwd_note = f"under {scen.replace('_', ' ')} by {pt.get('horizon')}"
    except Exception:  # noqa: BLE001 — a missing projection must not sink the whole KRI set
        pass

    kpis = [
        _kpi("total_value", "Total book value", total, "eur"),
        _kpi("value_at_risk", "Value at risk (High+)", r.get("value_at_risk_eur"), "eur", tone="#fb7185",
             hint="Value of the book in the top two severity bands"),
        _kpi("pct_at_risk", "Share at risk", r.get("pct_value_at_risk"), "pct", tone="#f0a860"),
        _kpi("acute_share", "Acute-peril exposure", _share(acute_val), "pct", tone="#fb7185",
             hint="Share of the book High/Very-High on an ACUTE, event-driven peril (flood, storm, wildfire, "
                  "frost, acute heat) — the sudden-loss / provisioning driver. Template 5 acute column."),
        _kpi("chronic_share", "Chronic-peril exposure", _share(chronic_val), "pct", tone="#f0a860",
             hint="Share High/Very-High on a CHRONIC, gradual peril (drought, chronic heat, coastal/sea-level, "
                  "water stress) — the long-run repricing driver. Template 5 chronic column."),
        _kpi("forward_share", "Projected share at risk", fwd_share, "pct", tone="#fb7185",
             hint=("Share of the book projected to cross into High+ " + (fwd_note or "under a warming pathway")
                   + " — the forward early-warning vs today's share at risk.")),
        _kpi("sector_concentration", "Climate-sector concentration", _share(hci_val), "pct", tone="#f0a860",
             hint=(f"Share of the book in EBA high-climate-impact sectors (NACE A–H, L). Largest single sector: "
                   f"{top_sec} · {_share(top_val)}%. The concentration axis of Pillar 3 Templates 1 & 5.")),
        _kpi("coverage", "Book scored", cov, "pct", hint="Share of assets scored on the golden source"),
        _kpi("fin_emissions", "Financed emissions", sum((em.get(k) or 0) for k in ("scope1", "scope2", "scope3")),
             "num", hint="tCO₂e · PCAF-attributed"),
        _kpi("taxonomy", "EU-Taxonomy eligible", round(100 * elig / tax_total, 1) if tax_total else 0, "pct"),
        _kpi("gar", "Green Asset Ratio", None, "pct", integrated=True, integrated_note="needs alignment",
             hint="Taxonomy-ALIGNED share (the Art. 8 GAR) needs alignment flags — substantial contribution + DNSH + minimum safeguards — provided in your book; only eligibility is computed here."),
    ]
    # Climate expected loss (IFRS-9 / ECL-relevant) — annual + lifetime, maturity-matched, from the frozen snapshot.
    elb = snap.get("expected_loss") or {}
    if elb.get("annual_el_eur") is not None:
        kpis.append(_kpi("expected_loss", "Climate expected loss (annual)", round(elb.get("annual_el_eur") or 0), "eur",
                         tone="#fb7185", hint=(f"Physical climate annual EL ({elb.get('annual_el_bps')} bps of EAD); "
                                               f"lifetime {round((elb.get('lifetime_el_eur') or 0)/1e6,1)}m "
                                               f"({elb.get('lifetime_el_bps')} bps), maturity-matched. Exposure × P(event) × "
                                               f"collateral severity under {elb.get('scenario')} — a disclosed relative model, not a fitted PD·LGD.")))

    # Transition risk ON THE COLLATERAL — loan value at risk if RE collateral strands below the rising EPC floor
    # (an LGD driver, distinct from the counterparty carbon-price transition). Only where the bank has RE collateral.
    csr = snap.get("collateral_stranding") or {}
    if csr.get("available"):
        kpis.append(_kpi(
            "collateral_stranding", "Collateral value at risk · EPC stranding",
            csr.get("collateral_value_at_risk_eur"), "eur", tone="#fb7185",
            hint=(f"Recovery-cushion erosion if real-estate collateral strands below the modelled EPC-{csr.get('floor_epc')} "
                  f"minimum-to-let floor — the LGD driver on {csr.get('n_below_floor')} of {csr.get('n_re_loans')} "
                  f"RE-collateralised loans ({csr.get('pct_re_loans_below_floor')}% of RE-book exposure below floor). "
                  f"Exposure-weighted LTV migrates {csr.get('exposure_weighted_ltv_pct')}%→{csr.get('stressed_ltv_pct')}% "
                  f"(+{csr.get('ltv_uplift_pp')}pp); €{round((csr.get('loan_value_at_risk_eur') or 0)/1e6,1)}m exposure "
                  f"uncovered (LTV>100%). {csr.get('epc_coverage_pct')}% carry an EPC. Disclosed EPBD-recast scenario, not a market fit.")))
    by_hazard = sorted(
        [{"hazard": h, "value": b.get("exposed_value_eur", 0), "score": b.get("max_score", 0)}
         for h, b in (snap.get("by_hazard") or {}).items() if (b.get("exposed_value_eur") or 0) > 0],
        key=lambda x: -x["value"])
    history = [{"label": h["label"], "filing_id": h["filing_id"],
                "total_value": (h["payload"].get("rollup") or {}).get("total_value_eur"),
                "value_at_risk": (h["payload"].get("rollup") or {}).get("value_at_risk_eur"),
                "pct_at_risk": (h["payload"].get("rollup") or {}).get("pct_value_at_risk")}
               for h in _snapshot_history(session, org_id, "bank_tcfd")]
    return {"framework": "bank_tcfd", "supported": True, "label": "TCFD physical-risk KRIs",
            "kpis": kpis, "by_hazard": by_hazard, "history": history}


def _p3esg_kri(session: Session, org_id: str) -> dict:
    """Pillar 3 ESG KRIs — the shared banking-book core (physical risk, financed emissions, GAR/Taxonomy) PLUS
    the indicators the EBA prudential templates prescribe that TCFD does NOT: the IEA-NZE2050 alignment-metric
    distance (Template 3) and exposure to the top-20 carbon-intensive firms (Template 4). Tagged to the Pillar 3
    framework so it grades against its own appetite bands and regulator framing."""
    r = _bank_kri(session, org_id)
    r["framework"] = "bank_p3esg"
    r["label"] = "Pillar 3 ESG KRIs"
    # append the Pillar-3-only prescribed indicators, computed from the same book via the transition engine
    try:
        from services.governance.reporting_settings import get_settings
        from services.governance.transition_alignment import template3_grid, template4_top20
        s = get_settings(session, org_id)
        snap = _live_snapshot(session, org_id, "bank_p3esg", s["scenario"], s["horizon"])
        assets = (snap or {}).get("assets") or []
        total = (snap or {}).get("rollup", {}).get("total_value_eur") or sum(a.get("value_eur") or 0 for a in assets)
        g3 = template3_grid(assets)
        g4 = template4_top20(assets)
        align_pending = g3.get("portfolio_distance") is None
        r["kpis"].append(_kpi(
            "p3_alignment", "IEA alignment distance", g3.get("portfolio_distance"), "pct",
            integrated=align_pending, integrated_note="needs intensity feed" if align_pending else None, tone="#fb7185",
            hint="Template 3 — gross-weighted distance of the book's counterparty CO₂-intensity to the IEA NZE2050 "
                 "2030 pathway (100×((current−IEA2030)/IEA2030)). Needs a counterparty physical-intensity feed "
                 "(vendor/counterparty) — shows '—' until provided."))
        r["kpis"].append(_kpi(
            "p3_top20", "Top-20 carbon-intensive exposure", round(100 * (g4.get("total_exposure") or 0) / total, 1) if total else 0,
            "pct", tone="#f0a860",
            hint=f'Template 4 — share of the book lent to the world\'s 20 most carbon-intensive firms (Carbon Majors). '
                 f'{g4.get("matched_count", 0)} of {g4.get("list_size", 20)} matched.'))
    except Exception:  # noqa: BLE001 — a missing transition input must not sink the KRI set
        pass
    r["history"] = [{**h, } for h in [{"label": x["label"], "filing_id": x["filing_id"],
                     "total_value": (x["payload"].get("rollup") or {}).get("total_value_eur"),
                     "value_at_risk": (x["payload"].get("rollup") or {}).get("value_at_risk_eur"),
                     "pct_at_risk": (x["payload"].get("rollup") or {}).get("pct_value_at_risk")}
                    for x in _snapshot_history(session, org_id, "bank_p3esg")]]
    return r


def _sfdr_kri(session: Session, org_id: str) -> dict:
    from ml.regulatory.sfdr_pai import entity_pai_statement
    st = entity_pai_statement(session, org_id)
    if st.get("error"):
        return {"framework": "sfdr_pai", "supported": True, "label": "SFDR KRIs", "kpis": [],
                "by_hazard": [], "history": [], "note": st["error"]}
    ent = st.get("entity", {})
    cs = st.get("coverage_summary", {})
    ind = {i["number"]: i for i in (st.get("indicators") or [])}

    def _val(n):
        return (ind.get(n) or {}).get("value")
    em1 = _val(1)
    total_em = em1.get("total") if isinstance(em1, dict) else em1   # PAI 1 total (Scope 1-3)
    # The mandatory climate PAI indicators, surfaced as KRIs (values, not just counts) — the RTS Annex I
    # Table 1 climate block. Each is the value-weighted figure the fund statement already computes.
    kpis = [
        _kpi("nav", "NAV in scope", ent.get("total_value_eur"), "eur"),
        _kpi("positions", "Positions", ent.get("positions"), "num"),
        _kpi("pai_emissions", "Financed emissions", total_em, "num", hint="tCO₂e · PAI 1 total (Scope 1-3)"),
        _kpi("carbon_footprint", "Carbon footprint", _val(2), "num", hint="tCO₂e per €M invested · SFDR PAI 2"),
        _kpi("waci", "WACI", _val(3), "num", hint="Weighted-avg carbon intensity · tCO₂e/€M revenue · PAI 3"),
        _kpi("fossil_fuel", "Fossil-fuel exposure", _val(4), "pct", hint="Share of value in fossil-fuel companies · PAI 4"),
        _kpi("non_renewable", "Non-renewable energy", _val(5), "pct", hint="Share of non-renewable energy · PAI 5"),
        _kpi("energy_intensity", "Energy intensity", _val(6), "dec", hint="GWh per €M revenue (high-impact sectors) · SFDR PAI 6"),
        _kpi("biodiversity", "Biodiversity areas", _val(7), "pct", hint="Share of value in/near biodiversity-sensitive areas · PAI 7"),
        _kpi("emissions_water", "Emissions to water", _val(8), "dec", hint="Tonnes per €M invested · SFDR PAI 8"),
        _kpi("hazardous_waste", "Hazardous waste", _val(9), "dec", hint="Tonnes per €M invested · SFDR PAI 9"),
        _kpi("ungc_violations", "UNGC / OECD violations", _val(10), "pct", hint="Share of value in violation · SFDR PAI 10"),
        _kpi("ungc_no_process", "No UNGC monitoring", _val(11), "pct", hint="Share lacking monitoring processes · SFDR PAI 11"),
        _kpi("gender_pay_gap", "Gender pay gap", _val(12), "pct", hint="Unadjusted · SFDR PAI 12"),
        _kpi("board_diversity", "Board gender diversity", _val(13), "pct", hint="Share female on boards · SFDR PAI 13"),
        _kpi("controversial_weapons", "Controversial weapons", _val(14), "pct", hint="Share exposed to controversial weapons · SFDR PAI 14"),
        _kpi("emissions_cov", "Emissions coverage", cs.get("emissions_coverage_pct"), "pct",
             hint="Share of NAV with issuer emissions data"),
        _kpi("indicators", "PAI indicators computed", cs.get("computed"), "num",
             hint=f'of {cs.get("mandatory_indicators")} mandatory'),
    ]
    history = [{"label": h["label"], "filing_id": h["filing_id"],
                "total_value": (h["payload"].get("entity") or {}).get("total_value_eur"),
                "value_at_risk": None, "pct_at_risk": None}
               for h in _snapshot_history(session, org_id, "sfdr_pai")]
    return {"framework": "sfdr_pai", "supported": True, "label": "SFDR entity KRIs",
            "kpis": kpis, "by_hazard": [], "history": history}

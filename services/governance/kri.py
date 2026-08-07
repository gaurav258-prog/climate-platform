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
    return {"key": key, "label": label, "value": value, "fmt": fmt, "tone": tone, "hint": hint,
            "integrated": integrated, "integrated_note": integrated_note}


def kri(session: Session, org_id: str, framework: str) -> dict:
    if framework == "bank_tcfd":
        result = _bank_kri(session, org_id)
    elif framework == "sfdr_pai":
        result = _sfdr_kri(session, org_id)
    elif framework == "reit_tcfd":
        result = _reit_kri(session, org_id)
    elif framework == "insurer_climate":
        result = _insurer_kri(session, org_id)
    elif framework in ("csrd_e1", "esrs_pack"):
        result = _agri_kri(session, org_id, framework)
    else:
        return {"framework": framework, "supported": False,
                "message": "No KRI dashboard for this framework yet."}
    # grade every KPI against the org's appetite bands → green / amber / red (a monitored control, not a number)
    if result.get("supported") and result.get("kpis"):
        from services.governance import kri_thresholds, kri_regmap
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
    by_hazard = _by_hazard(snap)
    history = [{"label": h["label"], "filing_id": h["filing_id"], "total_value": (h["payload"].get("rollup") or {}).get("total_sum_insured_eur"),
                "value_at_risk": (h["payload"].get("rollup") or {}).get("total_expected_annual_loss_eur"),
                "pct_at_risk": None} for h in _snapshot_history(session, org_id, "insurer_climate")]
    return {"framework": "insurer_climate", "supported": True, "label": "Insurer climate/NatCat KRIs",
            "kpis": kpis, "by_hazard": by_hazard, "history": history}


def _agri_kri(session: Session, org_id: str, framework: str = "csrd_e1") -> dict:
    """ESRS E1 (climate) KRIs for an agri / manufacturer book — the real E1-9 climate financial effects from
    build_e1_report (own operations + upstream sourcing), NOT GHG. GHG accounting (Scope 1/2/3) and energy are
    deliberately out of scope here — the platform computes the physical / nature ESRS and integrates GHG from
    the customer's carbon-accounting tool — so we never surface a fabricated emissions number."""
    from services.intelligence.csrd_e1 import build_e1_report
    from api.routers.supply import _plots_with_hazard
    from services.governance.reporting_settings import get_settings
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
            src = "Natura 2000 (© EEA)" if set(pa["datasets"]) <= {"natura2000"} else "protected areas (EEA Natura 2000 · WDPA via IBAT)"
            kpis.append(_kpi("protected_area", "In protected areas", in_pa, "num",
                             hint=f"Own sites + sourcing plots in/near a {src} · €{exposed_m}m exposed · ESRS E4"))
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
_NOUN = {"bank_tcfd": "assets", "reit_tcfd": "properties", "insurer_climate": "policies"}


def _live_snapshot(session: Session, org_id: str, framework: str, scenario: str, horizon: str) -> dict:
    if framework == "bank_tcfd":
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

    kpis = [
        _kpi("total_value", "Total book value", total, "eur"),
        _kpi("value_at_risk", "Value at risk (High+)", r.get("value_at_risk_eur"), "eur", tone="#fb7185",
             hint="Value of the book in the top two severity bands"),
        _kpi("pct_at_risk", "Share at risk", r.get("pct_value_at_risk"), "pct", tone="#f0a860"),
        _kpi("coverage", "Book scored", cov, "pct", hint="Share of assets scored on the golden source"),
        _kpi("fin_emissions", "Financed emissions", sum((em.get(k) or 0) for k in ("scope1", "scope2", "scope3")),
             "num", hint="tCO₂e · PCAF-attributed"),
        _kpi("taxonomy", "EU-Taxonomy eligible", round(100 * elig / tax_total, 1) if tax_total else 0, "pct"),
        _kpi("gar", "Green Asset Ratio", None, "pct", integrated=True, integrated_note="needs alignment",
             hint="Taxonomy-ALIGNED share (the Art. 8 GAR) needs alignment flags — substantial contribution + DNSH + minimum safeguards — provided in your book; only eligibility is computed here."),
    ]
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

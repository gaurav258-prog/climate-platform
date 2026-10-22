"""The bank's two KRI sets, each anchored on the governed report it belongs to (E95, as services.governance.kri_sectors
does for the REIT, insurer and asset manager, E87).

  bank_tcfd   the EU Taxonomy Art. 8 report: it prints the Summary of KPIs (Template 0) — the GAR stock, turnover-based
              and CapEx-based, and its coverage. Those KRIs carry `filed_basis` and a filed history read from the
              report's frozen snapshots (taxonomy_forms.kpi_summary — the same function the form uses).
  bank_p3esg  Pillar 3 ESG: Template 1 prints the counterparties' gross Scope 1, 2 and 3 emissions (column i of its total
              row) — the financed-emissions KRI's filed basis. Template 5 prints physical-risk exposure per NACE sector and
              geography row on the gross carrying amount; it prints no book-level total, so the book-level physical-risk
              KRIs are live only on both tabs — and a KRI per Template 5 row and column (services.governance.kri_t5, E98)
              carries what the template does print, with its filed history.

Every other KRI is `live_only`: it says so and has no filed history — nothing is borrowed from another report.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from services.governance.kri_sectors import anchor
from services.governance.pillar3_t1 import RECORD as T1_RECORD

TAXONOMY, PILLAR3 = "bank_tcfd", "bank_p3esg"
_T0 = "EU Taxonomy Art. 8 filing — Summary of KPIs (Template 0), GAR stock"
_TAX_PRINTED = {"gar": f"{_T0}, KPI turnover-based", "gar_capex": f"{_T0}, KPI CapEx-based",
                "gar_coverage": f"{_T0}, % coverage over total assets"}
_P3_PRINTED = {"fin_emissions": "Pillar 3 ESG filing — Template 1, total row, column i (gross Scope 1, 2 and 3 of the "
                                "counterparties stating all three)"}
_PHYSICAL = ("value_at_risk", "pct_at_risk", "acute_share", "chronic_share", "forward_share", "sector_concentration")
_GAR_KPIS = (("gar", "Green Asset Ratio (stock, turnover-based)", "turnover", "kri.indicator.gar_turnover"),
             ("gar_capex", "Green Asset Ratio (stock, CapEx-based)", "capex", "kri.indicator.gar_capex"),
             ("gar_coverage", "GAR coverage over total assets", "coverage", "kri.indicator.gar_coverage"))


def _anchor(kpis: list[dict], printed: dict[str, str]) -> None:
    from services.governance.kri import msg
    anchor(kpis, printed)
    for k in kpis:
        if k["live_only"] and k["key"] in _PHYSICAL:          # the Pillar 3 filing prints physical risk per row (Template 5)
            k["filed"] = msg("kri.filed.live_only_physical")
            k["filed_basis"] = k["filed"]["detail"]["what"]


def _hist(h: dict, figures: list[dict]) -> dict:
    # the legacy book-value / at-risk slots stay empty: neither report prints them as a figure
    return {"label": h["label"], "filing_id": h["filing_id"], "total_value": None, "value_at_risk": None,
            "pct_at_risk": None, "figures": figures}


def taxonomy_kri(session: Session, org_id: str) -> dict:
    from services.governance.bank_taxonomy_report import live_kpis
    from services.governance.kri import _kpi, _snapshot_history, msg
    from services.governance.taxonomy_forms import kpi_summary
    r = book_kri(session, org_id)
    sm = live_kpis(session, org_id) or {}
    gar = [_kpi(key, label, sm.get(basis), "pct", tone="#4ade80", about=msg(code)) for key, label, basis, code in _GAR_KPIS]
    r["kpis"] = [k for k in r["kpis"] if k["key"] != "gar"] + gar
    _anchor(r["kpis"], _TAX_PRINTED)

    def figures(p: dict) -> list[dict]:
        s = kpi_summary(p) or {}
        return [{"key": key, "label": label, "fmt": "pct", "value": s.get(basis)} for key, label, basis, _ in _GAR_KPIS]
    r["history"] = [_hist(h, figures(h["payload"])) for h in _snapshot_history(session, org_id, TAXONOMY)]
    r.update(framework=TAXONOMY, label="EU Taxonomy indicators")
    return r


def _t1_emissions(spec: dict | None, assets: list[dict], t1: dict | None):
    """Template 1's total row, column i, as the filing prints it on its stated method `t1` (None where the version has no
    Template 1, or the method is not stated)."""
    from services.governance.pillar3_grids import BINDING, build
    if not spec or not assets or not any(t["id"] == "T1" for t in spec["templates"]):
        return None
    total = next((rid for rid, how in BINDING["T1"]["rows"].items() if how == "computed:total"), None)
    row = next((x for x in build(spec, "T1", assets, t1=t1)["rows"] if x["id"] == total), None)
    v = None if row is None else (row.get("values") or {}).get("i")
    return None if v is None else round(v)


def _p3_live_spec(session: Session, org_id: str) -> dict | None:
    from services.calc_settings import get_calc_settings
    from services.governance.filing_annex import _p3_spec
    from services.governance.filings import reporting_period_end
    from services.governance.report_snapshots import _spec_record
    rec = _spec_record(session, PILLAR3, reporting_period_end(session, org_id), get_calc_settings(session, org_id))
    return _p3_spec({"_specs": {PILLAR3: rec}} if rec and rec.get("version") else {})


def pillar3_kri(session: Session, org_id: str) -> dict:
    """The banking-book core plus the indicators the Pillar 3 templates prescribe beyond it: the IEA-NZE2050 alignment
    distance (Template 3) and the exposure to the top-20 carbon-intensive firms (Template 4)."""
    from services.governance import kri_t5
    from services.governance.filing_annex import _p3_spec
    from services.governance.kri import _kpi, _live_snapshot, _snapshot_history, fact, msg
    from services.governance.reporting_settings import get_settings
    r = book_kri(session, org_id)
    live_spec, t5 = _p3_live_spec(session, org_id), []
    try:
        from services.governance.transition_alignment import template3_grid, template4_top20
        s = get_settings(session, org_id)
        snap = _live_snapshot(session, org_id, PILLAR3, s["scenario"], s["horizon"])
        assets = (snap or {}).get("assets") or []
        t5 = kri_t5.kpis(live_spec, kri_t5.grid(snap, live_spec), (snap.get("rollup") or {}).get("gap"))
        total = (snap or {}).get("rollup", {}).get("total_value_eur") or sum(a.get("value_eur") or 0 for a in assets)
        for kpi in r["kpis"]:
            if kpi["key"] == "fin_emissions":           # the figure Template 1 prints, on the stated method (E103)
                from services.governance.pillar3_t1 import ESTIMATION, RECORD, gaps
                rec = (snap or {}).get(RECORD)
                kpi["value"] = _t1_emissions(live_spec, assets, rec)
                about = msg("kri.indicator.financed_emissions_filed")
                missing = gaps(rec)                     # the institution's emissions method, not stated: which choice
                kpi.update(about=about, hint=about["detail"]["what"], facts=[],
                           missing=(msg("kri.gap.emissions_estimation") if any(ESTIMATION in g for g in missing)
                                    else msg("kri.gap.emissions_attribution") if missing else None))
                break
        g3, g4 = template3_grid(assets), template4_top20(assets)
        align_pending = g3.get("portfolio_distance") is None
        r["kpis"].append(_kpi(
            "p3_alignment", "IEA alignment distance", g3.get("portfolio_distance"), "pct", tone="#fb7185",
            integrated=align_pending, about=msg("kri.indicator.alignment_distance"),
            needs=msg("kri.provide.intensity_feed") if align_pending else None))
        r["kpis"].append(_kpi(
            "p3_top20", "Top-20 carbon-intensive exposure", round(100 * (g4.get("total_exposure") or 0) / total, 1) if total else 0,
            "pct", tone="#f0a860", about=msg("kri.indicator.top_emitters"),
            facts=[fact("matched", f'{g4.get("matched_count", 0)} of {g4.get("list_size", 20)}', "text")]))
    except Exception:  # noqa: BLE001 — a missing transition input must not sink the KRI set
        pass
    _anchor(r["kpis"], _P3_PRINTED)
    r["kpis"] += t5                                     # Template 5 per row and column: filed basis and history (E98)
    r["history"] = [_hist(h, [{"key": "fin_emissions", "label": "Financed emissions", "fmt": "num",
                               "value": _t1_emissions(_p3_spec(h["payload"]), h["payload"].get("assets") or [],
                                                      h["payload"].get(T1_RECORD))}]
                          + kri_t5.figures(h["payload"], live_spec))
                    for h in _snapshot_history(session, org_id, PILLAR3)]
    r.update(framework=PILLAR3, label="Pillar 3 ESG indicators")
    return r


def book_kri(session: Session, org_id: str) -> dict:
    """The banking book's live KRIs (physical risk, financed emissions, Taxonomy eligibility, credit-risk overlays) —
    shared by both sets; each set anchors what its report prints."""
    from api.routers.bank import build_disclosure_snapshot
    from core import messages
    from services.governance.kri import _amount, _kpi, fact, method_gap, msg
    from services.governance.pillar3_templates import (
        NACE_SECTIONS,
        concentration_split,
        stated_level,
    )
    from services.governance.reporting_settings import get_settings
    from services.scoring.pcaf import financed_total
    s = get_settings(session, org_id)
    snap = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"])
    r = snap.get("rollup", {})
    em, pcaf, tax = snap.get("financed_emissions_tco2e", {}), snap.get("financed_emissions_pcaf", {}), snap.get("taxonomy", {})
    total = r.get("total_value_eur", 0) or 0
    elig = (tax.get("eligible") or {}).get("value_eur", 0) or 0
    tax_total = sum((v or {}).get("value_eur", 0) or 0 for v in tax.values())
    cov = round(100 * r.get("n_scored", 0) / r.get("n_assets", 1), 1) if r.get("n_assets") else 0
    # acute / chronic split, climate-sector concentration and the forward early-warning, from the same per-asset book
    level = stated_level(snap)
    cs = concentration_split(snap.get("assets") or [], level)
    at_level = None if level is not None else method_gap("method.at_risk_level")   # 'at risk' is the stated level

    def _share(x):
        return None if x is None else round(100 * x / total, 1) if total else 0

    fwd_share, fwd_facts = None, []
    try:
        from services.intelligence.forward_risk import forward_risk
        from services.money.params import for_org
        scen = s["scenario"] if s.get("scenario") and s["scenario"] != "baseline" else "disorderly_2c"
        fut = [t for t in (forward_risk(session, org_id, "banking", scen, for_org(session, org_id)).get("trajectory") or [])
               if t.get("horizon") != "current"]
        if fut:
            fwd_share = fut[-1].get("at_risk_pct")
            fwd_facts = [fact("scenario", messages.name("scenario", scen), "text"), fact("year", fut[-1].get("horizon"), "text")]
    except Exception:  # noqa: BLE001 — a missing projection must not sink the whole KRI set
        pass
    top = cs.get("top_sector")
    pcaf_facts = [
        fact("counterparties_stating", f"{pcaf.get('n_counterparties_with_emissions', 0):,} of {pcaf.get('n_counterparties', 0):,}", "text"),
        fact("lending_covered", pcaf.get("exposure_with_emissions_pct"), "pct"),
        fact("with_enterprise_value", pcaf.get("n_evic_covered", 0), "num"),
        *([fact("all_scopes", pcaf["n_attributed_all_scopes"], "num")] if "n_attributed_all_scopes" in pcaf else []),
        *([fact("not_attributed", pcaf["not_covered_total"], "t")] if pcaf.get("not_covered_total") else []),
    ]
    kpis = [
        _kpi("total_value", "Total book value", total, "eur", about=msg("kri.indicator.total_value")),
        _kpi("value_at_risk", "Value at material physical risk", r.get("value_at_risk_eur"), "eur", tone="#fb7185",
             about=msg("kri.indicator.value_at_risk"), gap=at_level),
        _kpi("pct_at_risk", "Share at risk", r.get("pct_value_at_risk"), "pct", tone="#f0a860",
             about=msg("kri.indicator.pct_at_risk"), gap=at_level),
        _kpi("acute_share", "Acute-peril exposure", _share(cs["acute_val"]), "pct", tone="#fb7185",
             about=msg("kri.indicator.acute_share"), gap=at_level),
        _kpi("chronic_share", "Chronic-peril exposure", _share(cs["chronic_val"]), "pct", tone="#f0a860",
             about=msg("kri.indicator.chronic_share"), gap=at_level),
        _kpi("forward_share", "Projected share at risk", fwd_share, "pct", tone="#fb7185",
             about=msg("kri.indicator.forward_share"), facts=fwd_facts, gap=at_level),
        _kpi("sector_concentration", "Climate-sector concentration", _share(cs["high_climate_val"]), "pct", tone="#f0a860",
             about=msg("kri.indicator.sector_concentration"),
             facts=[fact("largest_sector", NACE_SECTIONS.get(top, "Unclassified"), "text"),
                    fact("largest_sector_share", _share(cs["top_sector_val"]), "pct")] if top else []),
        _kpi("coverage", "Book scored", cov, "pct", about=msg("kri.indicator.coverage")),
        # PCAF-attributed, over the counterparties that state emissions AND carry EVIC — none attributable is no figure
        _kpi("fin_emissions", "Financed emissions", financed_total(em) if pcaf.get("n_evic_covered") else None, "num",
             about=msg("kri.indicator.financed_emissions"), facts=pcaf_facts),
        _kpi("taxonomy", "EU-Taxonomy eligible", round(100 * elig / tax_total, 1) if tax_total else 0, "pct",
             about=msg("kri.indicator.taxonomy_eligible")),
        _kpi("gar", "Green Asset Ratio", None, "pct", integrated=True, about=msg("kri.indicator.green_asset_ratio"),
             needs=msg("kri.provide.alignment")),
    ]
    elb = snap.get("expected_loss") or {}
    if elb.get("annual_el_eur") is not None:
        kpis.append(_kpi("expected_loss", "Climate expected loss (annual)", _amount(elb.get("annual_el_eur")), "eur",
                         tone="#fb7185", about=msg("kri.indicator.expected_loss"),
                         facts=[fact("annual_share", elb.get("annual_el_bps"), "bps"),
                                fact("lifetime", _amount(elb.get("lifetime_el_eur")), "eur"),
                                fact("lifetime_share", elb.get("lifetime_el_bps"), "bps"),
                                *([fact("scenario", messages.name("scenario", elb["scenario"]), "text")]
                                  if elb.get("scenario") in messages.names().get("scenario", {}) else [])]))
    csr = snap.get("collateral_stranding") or {}
    if csr.get("available"):
        kpis.append(_kpi(
            "collateral_stranding", "Collateral value at risk · EPC stranding", csr.get("collateral_value_at_risk_eur"), "eur",
            tone="#fb7185", about=msg("kri.indicator.collateral_stranding"), gap=method_gap(csr.get("gap")),
            facts=[] if csr.get("gap") else [
                fact("loans_discounted", f"{csr.get('n_discounted')} of {csr.get('n_re_loans')}", "text"),
                fact("exposure_discounted", csr.get("pct_exposure_discounted"), "pct"),
                fact("ltv", csr.get("exposure_weighted_ltv_pct"), "pct"),
                fact("ltv_after", csr.get("stressed_ltv_pct"), "pct"),
                fact("uncovered", csr.get("loan_value_at_risk_eur"), "eur"),
                fact("assessed", csr.get("epc_coverage_pct"), "pct")]))
    from services.governance.kri import _by_hazard
    from services.governance.kri_loss import tested_loss_kpi
    kpis.append(tested_loss_kpi(session, org_id))
    return {"supported": True, "kpis": kpis, "by_hazard": _by_hazard(snap), "history": []}

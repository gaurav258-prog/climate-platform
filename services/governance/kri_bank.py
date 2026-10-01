"""The bank's two KRI sets, each anchored on the governed report it belongs to (E95, as services.governance.kri_sectors
does for the REIT, insurer and asset manager, E87).

  bank_tcfd   the EU Taxonomy Art. 8 report: it prints the Summary of KPIs (Template 0) — the GAR stock, turnover-based
              and CapEx-based, and its coverage. Those KRIs carry `filed_basis` and a filed history read from the
              report's frozen snapshots (taxonomy_forms.kpi_summary — the same function the form uses).
  bank_p3esg  Pillar 3 ESG: Template 1 prints the counterparties' gross Scope 1, 2 and 3 emissions (column i of its total
              row) — the financed-emissions KRI's filed basis. Template 5 prints physical-risk exposure per NACE sector and
              geography row on the gross carrying amount; it prints no book-level total, so the book-level physical-risk
              KRIs are live only on both tabs.

Every other KRI is `live_only`: it says so and has no filed history — nothing is borrowed from another report.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from services.governance.kri_sectors import anchor

TAXONOMY, PILLAR3 = "bank_tcfd", "bank_p3esg"
_T0 = "EU Taxonomy Art. 8 filing — Summary of KPIs (Template 0), GAR stock"
_TAX_PRINTED = {"gar": f"{_T0}, KPI turnover-based", "gar_capex": f"{_T0}, KPI CapEx-based",
                "gar_coverage": f"{_T0}, % coverage over total assets"}
_P3_PRINTED = {"fin_emissions": "Pillar 3 ESG filing — Template 1, total row, column i (gross Scope 1, 2 and 3 of the "
                                "counterparties stating all three)"}
_PHYSICAL = ("value_at_risk", "pct_at_risk", "acute_share", "chronic_share", "forward_share", "sector_concentration")
_PHYSICAL_LIVE = ("Live only — Pillar 3 Template 5 prints physical-risk exposure per NACE sector and geography row, on the "
                  "gross carrying amount; no template prints this book-level figure, so it has no filed history.")
_GAR_KPIS = (("gar", "Green Asset Ratio (stock, turnover-based)", "turnover"),
             ("gar_capex", "Green Asset Ratio (stock, CapEx-based)", "capex"),
             ("gar_coverage", "GAR coverage over total assets", "coverage"))


def _anchor(kpis: list[dict], printed: dict[str, str]) -> None:
    anchor(kpis, printed)
    for k in kpis:
        if k["live_only"] and k["key"] in _PHYSICAL:
            k["filed_basis"] = _PHYSICAL_LIVE


def _hist(h: dict, figures: list[dict]) -> dict:
    # the legacy book-value / at-risk slots stay empty: neither report prints them as a figure
    return {"label": h["label"], "filing_id": h["filing_id"], "total_value": None, "value_at_risk": None,
            "pct_at_risk": None, "figures": figures}


def taxonomy_kri(session: Session, org_id: str) -> dict:
    from services.governance.bank_taxonomy_report import live_kpis
    from services.governance.kri import _kpi, _snapshot_history
    from services.governance.taxonomy_forms import kpi_summary
    r = book_kri(session, org_id)
    sm = live_kpis(session, org_id) or {}
    gar = [_kpi(key, label, sm.get(basis), "pct", tone="#4ade80",
                hint=f"{_TAX_PRINTED[key]} — over today's book, on the version governing your reporting period "
                     "(blank where no exposure states the facts it needs)") for key, label, basis in _GAR_KPIS]
    r["kpis"] = [k for k in r["kpis"] if k["key"] != "gar"] + gar
    _anchor(r["kpis"], _TAX_PRINTED)

    def figures(p: dict) -> list[dict]:
        s = kpi_summary(p) or {}
        return [{"key": key, "label": label, "fmt": "pct", "value": s.get(basis)} for key, label, basis in _GAR_KPIS]
    r["history"] = [_hist(h, figures(h["payload"])) for h in _snapshot_history(session, org_id, TAXONOMY)]
    r.update(framework=TAXONOMY, label="EU Taxonomy Art. 8 KRIs")
    return r


def _t1_emissions(spec: dict | None, assets: list[dict]):
    """Template 1's total row, column i, as the filing prints it (None where the version has no Template 1)."""
    from services.governance.pillar3_grids import BINDING, build
    if not spec or not assets or not any(t["id"] == "T1" for t in spec["templates"]):
        return None
    total = next((rid for rid, how in BINDING["T1"]["rows"].items() if how == "computed:total"), None)
    row = next((x for x in build(spec, "T1", assets)["rows"] if x["id"] == total), None)
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
    from services.governance.filing_annex import _p3_spec
    from services.governance.kri import _kpi, _live_snapshot, _snapshot_history
    from services.governance.reporting_settings import get_settings
    r = book_kri(session, org_id)
    try:
        from services.governance.transition_alignment import template3_grid, template4_top20
        s = get_settings(session, org_id)
        snap = _live_snapshot(session, org_id, PILLAR3, s["scenario"], s["horizon"])
        assets = (snap or {}).get("assets") or []
        total = (snap or {}).get("rollup", {}).get("total_value_eur") or sum(a.get("value_eur") or 0 for a in assets)
        for kpi in r["kpis"]:
            if kpi["key"] == "fin_emissions":           # the figure Template 1 prints (gross, no PCAF attribution)
                kpi["value"] = _t1_emissions(_p3_live_spec(session, org_id), assets)
                kpi["hint"] = ("tCO₂e · gross Scope 1–3 of the counterparties that state all three — Template 1, total "
                               "row, column i (no PCAF attribution there). A scope not stated is never counted as zero.")
                break
        g3, g4 = template3_grid(assets), template4_top20(assets)
        align_pending = g3.get("portfolio_distance") is None
        r["kpis"].append(_kpi(
            "p3_alignment", "IEA alignment distance", g3.get("portfolio_distance"), "pct",
            integrated=align_pending, integrated_note="needs intensity feed" if align_pending else None, tone="#fb7185",
            hint="Template 3 / EU CRFR4 (pending adoption) — gross-weighted distance of the book's counterparty CO₂-intensity "
                 "to the IEA NZE2050 2030 pathway (100×((current−IEA2030)/IEA2030)). Needs a counterparty physical-intensity "
                 "feed (vendor/counterparty) — shows '—' until provided."))
        r["kpis"].append(_kpi(
            "p3_top20", "Top-20 carbon-intensive exposure", round(100 * (g4.get("total_exposure") or 0) / total, 1) if total else 0,
            "pct", tone="#f0a860",
            hint=f'Template 4 — share of the book lent to the world\'s 20 most carbon-intensive firms (Carbon Majors). '
                 f'{g4.get("matched_count", 0)} of {g4.get("list_size", 20)} matched.'))
    except Exception:  # noqa: BLE001 — a missing transition input must not sink the KRI set
        pass
    _anchor(r["kpis"], _P3_PRINTED)
    r["history"] = [_hist(h, [{"key": "fin_emissions", "label": "Financed emissions (Template 1, column i)", "fmt": "num",
                               "value": _t1_emissions(_p3_spec(h["payload"]), h["payload"].get("assets") or [])}])
                    for h in _snapshot_history(session, org_id, PILLAR3)]
    r.update(framework=PILLAR3, label="Pillar 3 ESG KRIs")
    return r


def book_kri(session: Session, org_id: str) -> dict:
    """The banking book's live KRIs (physical risk, financed emissions, Taxonomy eligibility, credit-risk overlays) —
    shared by both sets; each set anchors what its report prints."""
    from api.routers.bank import build_disclosure_snapshot
    from services.governance.kri import _amount, _kpi, _millions, _money_text
    from services.governance.pillar3_templates import concentration_split, stated_level
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
    cs = concentration_split(snap.get("assets") or [], stated_level(snap))

    def _share(x):
        return None if x is None else round(100 * x / total, 1) if total else 0

    fwd_share = fwd_note = None
    try:
        from services.intelligence.forward_risk import forward_risk
        from services.money.params import for_org
        scen = s["scenario"] if s.get("scenario") and s["scenario"] != "baseline" else "disorderly_2c"
        fut = [t for t in (forward_risk(session, org_id, "banking", scen, for_org(session, org_id)).get("trajectory") or [])
               if t.get("horizon") != "current"]
        if fut:
            fwd_share, fwd_note = fut[-1].get("at_risk_pct"), f"under {scen.replace('_', ' ')} by {fut[-1].get('horizon')}"
    except Exception:  # noqa: BLE001 — a missing projection must not sink the whole KRI set
        pass
    kpis = [
        _kpi("total_value", "Total book value", total, "eur"),
        _kpi("value_at_risk", "Value at material physical risk", r.get("value_at_risk_eur"), "eur", tone="#fb7185",
             hint="Value at or above the bank's stated at-risk level (method.at_risk_level)"),
        _kpi("pct_at_risk", "Share at risk", r.get("pct_value_at_risk"), "pct", tone="#f0a860"),
        _kpi("acute_share", "Acute-peril exposure", _share(cs["acute_val"]), "pct", tone="#fb7185",
             hint="Share of the book at or above the stated at-risk level on an ACUTE, event-driven peril (flood, storm, "
                  "wildfire, frost, acute heat) — the sudden-loss / provisioning driver."),
        _kpi("chronic_share", "Chronic-peril exposure", _share(cs["chronic_val"]), "pct", tone="#f0a860",
             hint="Share at or above the stated at-risk level on a CHRONIC, gradual peril (drought, chronic heat, "
                  "coastal/sea-level, water stress) — the long-run repricing driver."),
        _kpi("forward_share", "Projected share at risk", fwd_share, "pct", tone="#fb7185",
             hint=("Share of the book projected at or above the stated at-risk level " + (fwd_note or "under a warming pathway")
                   + " — the forward early-warning vs today's share at risk.")),
        _kpi("sector_concentration", "Climate-sector concentration", _share(cs["high_climate_val"]), "pct", tone="#f0a860",
             hint=(f"Share of the book in EBA high-climate-impact sectors (NACE A–H, L). Largest single sector: "
                   f"{cs['top_sector']} · {_share(cs['top_sector_val'])}%.")),
        _kpi("coverage", "Book scored", cov, "pct", hint="Share of assets scored on the golden source"),
        # PCAF-attributed, over the counterparties that state emissions AND carry EVIC — none attributable is no figure
        _kpi("fin_emissions", "Financed emissions", financed_total(em) if pcaf.get("n_evic_covered") else None, "num",
             hint=(f"tCO₂e · PCAF-attributed (factor = outstanding ÷ counterparty EVIC, capped at 100%) · "
                   f"{pcaf.get('n_counterparties_with_emissions', 0)} of {pcaf.get('n_counterparties', 0)} counterparties "
                   f"state emissions ({pcaf.get('exposure_with_emissions_pct')}% of outstanding; scope 3 by "
                   f"{(pcaf.get('n_stating') or {}).get('scope3', 0)}), {pcaf.get('n_evic_covered', 0)} of them carry EVIC"
                   + (f", {pcaf['n_attributed_all_scopes']} of those state all three scopes — the total sums only them"
                      if "n_attributed_all_scopes" in pcaf else "")
                   + (f" · {pcaf.get('not_covered_total', 0):,} tCO₂e stated without EVIC, not attributed"
                      if pcaf.get("not_covered_total") else "")
                   + " · a counterparty that states no emissions is not counted as zero")),
        _kpi("taxonomy", "EU-Taxonomy eligible", round(100 * elig / tax_total, 1) if tax_total else 0, "pct",
             hint="Share of book value in Taxonomy-eligible activities, from each exposure's stated Taxonomy status"),
        _kpi("gar", "Green Asset Ratio", None, "pct", integrated=True, integrated_note="needs alignment",
             hint="Taxonomy-ALIGNED share (the Art. 8 GAR) needs alignment flags — substantial contribution + DNSH + "
                  "minimum safeguards — provided in your book; only eligibility is computed here."),
    ]
    elb = snap.get("expected_loss") or {}
    if elb.get("annual_el_eur") is not None:
        kpis.append(_kpi("expected_loss", "Climate expected loss (annual)", _amount(elb.get("annual_el_eur")), "eur",
                         tone="#fb7185", hint=(f"Physical climate annual EL ({elb.get('annual_el_bps')} bps of EAD); "
                                               f"lifetime {_millions(elb.get('lifetime_el_eur'))} "
                                               f"({elb.get('lifetime_el_bps')} bps), maturity-matched. Exposure × P(event) × "
                                               f"the stated damage ratio under {elb.get('scenario')} — the bank's own method, "
                                               "not a fitted PD·LGD.")))
    csr = snap.get("collateral_stranding") or {}
    if csr.get("available"):
        kpis.append(_kpi(
            "collateral_stranding", "Collateral value at risk · EPC stranding", csr.get("collateral_value_at_risk_eur"), "eur",
            tone="#fb7185",
            hint=(f"Not computed — {csr['gap']}" if csr.get("gap") else
                  f"Recovery-cushion erosion on the stated brown discount per EPC grade — {csr.get('n_discounted')} of "
                  f"{csr.get('n_re_loans')} RE-collateralised loans in a discounted grade ({csr.get('pct_exposure_discounted')}% "
                  f"of assessed exposure). Exposure-weighted LTV {csr.get('exposure_weighted_ltv_pct')}%→{csr.get('stressed_ltv_pct')}%; "
                  f"{_money_text(session, org_id, csr.get('loan_value_at_risk_eur'))} exposure uncovered (LTV>100%). "
                  f"{csr.get('epc_coverage_pct')}% assessed.")))
    from services.governance.kri import _by_hazard
    return {"supported": True, "kpis": kpis, "by_hazard": _by_hazard(snap), "history": []}

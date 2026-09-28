"""The official regulator form — the same frozen datapoints arranged into the ACTUAL Annex / template
layout the regulator publishes, so a preparer sees the filing as it will be submitted, not just a flat list.

Each framework maps to the structure of its official form (SFDR RTS Annex I Table 1; the EU-Taxonomy
Article 8 GAR summary; the ESRS E1 disclosure requirements; the EIOPA/IFRS-S2 nat-cat table). The layout is
built from the merged datapoints (`dps` = key -> datapoint, already carrying any approved/pending override),
so a value cell references a datapoint KEY and the frontend renders it with the same value + manual/pending
flag + override control as the datapoint list. Descriptive cells are static official text. Figures are never
invented — a datapoint the snapshot doesn't carry renders as "—".
"""
from __future__ import annotations

from services.governance import money_format
from services.governance.reg_reference import reference


def _txt(s):
    return {"text": s}


def _num(s):
    """A right-aligned numeric text cell (for computed grid figures like Template 5)."""
    return {"text": s, "num": True}


def _mnum(s, source):
    """A numeric cell that also declares its source ('computed' = Tellumen engine, 'integrated' = institution
    banking systems, 'manual' = authored). Lets the official form show, per cell, who fills each figure."""
    return {"text": s, "num": True, "source": source}


def _cell(dps, key):
    """A value cell bound to a datapoint key — carries the merged datapoint (value + manual/pending) or a
    placeholder so the official row still appears when the snapshot has no figure for it."""
    d = dps.get(key)
    return {"dp": d} if d else {"dp": {"key": key, "label": "", "value": None, "fmt": "num",
                                       "unit": None, "source": "calculated", "note": None}}


def _pct_text(part, whole):
    if not isinstance(part, (int, float)) or not isinstance(whole, (int, float)) or not whole:
        return "—"
    return f"{round(part / whole * 100, 1)}%"


def _pretty_hazard(label: str) -> str:
    """Readable hazard name for the official-form label column (drought → Drought, soil_water → Soil water)."""
    s = (label or "").replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else s


# ── SFDR — RTS (EU) 2022/1288 Annex I (the PAI statement) ──────────────────────────────────────────────────
# Built to the ACTUAL Annex I template, not a summary. Table 1 = the 18 MANDATORY principal-adverse-impact
# indicators (14 investee-company + 2 sovereign/supranational + 2 real-estate), each with its verbatim
# "Metric" wording from the Annex; Tables 2 & 3 = the opt-in "additional" indicators (the filer selects at
# least one from each). Each row carries the Annex's own six columns: Adverse sustainability indicator ·
# Metric · Impact [reference period] · Impact [prior period] · Explanation · Actions taken/planned.
# The impact figure binds to the assembled datapoint (indicator.<n>); the prior period / explanation /
# actions columns bind to indicator.<n>.prior|expl|action so an override can populate them, else render "—".
# ── SFDR principal-adverse-impacts statement: Table 1 and the adopted Table 2 / 3 indicators, from the spec ─────
def _sfdr_dp_key(how: str) -> str:
    """The form datapoint behind a Table 1 row binding ('computed:indicator.1.total' → 'indicator.1')."""
    key = how.split(":", 1)[1]
    return key[: -len(".total")] if key.endswith(".total") else key


def _sfdr_annex(dps: dict, payload: dict) -> list[dict]:
    import services.regspec as R
    from services.governance.sfdr_binding import BINDING
    spec = _frozen_spec("sfdr_pai", payload)
    t1 = R.template(spec, "T1")
    cols = [c["label"] for c in t1["columns"]]
    sections: list[dict] = []
    by_part: dict[str, list] = {}
    for r in t1["rows"]:
        by_part.setdefault(r["label"].split(" > ")[0], []).append(r)
    for part, rows_ in by_part.items():
        rows, heading = [], None
        for r in rows_:
            segs = r["label"].split(" > ")
            if " › ".join(segs[1:-2]) != heading:
                heading = " › ".join(segs[1:-2])
                rows.append({"type": "subheader", "label": heading})
            key = _sfdr_dp_key(BINDING["T1"]["rows"][r["id"]])
            rows.append({"type": "row", "cells": [
                _txt(segs[-2]), _txt(segs[-1]), _cell(dps, key), _cell(dps, f"{key}.prior"),
                _txt((dps.get(f"{key}.expl") or {}).get("value") or "—"),
                _txt((dps.get(f"{key}.action") or {}).get("value") or "—")]})
        sections.append({"title": f"{t1['code']} · {part}", "key": f"sfdr_t1_{len(sections) + 1}", "columns": cols,
                         "rows": rows, "note": None,
                         "spec": {"version": spec["version"], "template": "T1", "sha256": spec["_sha256"]}})
    sections[0]["note"] = (f"{t1['title']} ({R.citation(spec, 'T1')}). Impact [year n] is the frozen figure: the average of "
                           "the impacts on 31 March, 30 June, 30 September and 31 December (Article 6(3)); the year n-1, "
                           "explanation and actions columns are completed on this form.")

    # the adopted additional indicators (Article 6(1)): at least one from Table 2 and one from Table 3, reported in the
    # Table 1 format under 'Other indicators …'
    add = (payload or {}).get("additional_indicators") or {}
    other = next((t for t in spec["templates"] if t["structure"] == "listed" and t["title"].startswith("Other indicators")), None)
    rows = []
    for tid in ("T2", "T3"):
        t = R.template(spec, tid)
        adopted = [i for i in add.get("indicators") or [] if i.get("table") == int(tid[1])]
        if adopted:
            rows.append({"type": "subheader", "label": f"{t['code']} — {t['title']}"})
        for i in adopted:
            key = f"additional.{i['key']}"
            rows.append({"type": "row", "cells": [
                _txt(f"{i.get('row', '')}. {i['name']}".lstrip(". ")), _txt(i.get("metric") or i["name"]),
                _cell(dps, key), _cell(dps, f"{key}.prior"),
                _txt((dps.get(f"{key}.expl") or {}).get("value") or "—"),
                _txt((dps.get(f"{key}.action") or {}).get("value") or "—")]})
    missing = add.get("missing") or []
    sections.append({"title": (other or {}).get("title", "Other indicators for principal adverse impacts"), "key": "sfdr_other",
                     "columns": cols, "rows": rows or [{"type": "row", "cells": [_txt("No additional indicator adopted"), _txt("—"),
                                                                                  _txt("—"), _txt("—"), _txt("—"), _txt("—")]}],
                     "note": ("At least one additional indicator from Table 2 and one from Table 3 must be reported "
                              f"({R.citation(spec, 'T2')}; Article 6(1))."
                              + (f" Not yet adopted: {', '.join(missing)}." if missing else ""))})
    return sections


# ── EU-Taxonomy Article 8 (GAR summary) + PCAF financed emissions + TCFD physical-risk metrics ─────────────
def _gar_grid_section(assets: list[dict]) -> dict | None:
    """The full Green Asset Ratio grid (Pillar 3 Templates 6–8 · Del. Reg. 2021/2178) by counterparty
    class — gross carrying amount, Taxonomy-eligible + Taxonomy-aligned, the covered-assets denominator (excl.
    general governments, Art. 7) and the GAR ratio on stock, computed from the per-asset `taxonomy_status`.
    Shared by the bank TCFD and Pillar-3 annexes so both render the same official grid, not a flat summary.
    Returns None where there is no per-asset book to compute it from."""
    if not assets:
        return None
    from services.governance.pillar3_templates import gar_grid
    gg = gar_grid(assets)
    # When the book is classified only to eligibility (nothing carries an 'aligned' status), the aligned figure
    # is a floor, not a determined zero — show it as pending the technical screening, not a bare €0.
    align_pending = gg["aligned"] == 0 and gg["eligible"] > 0

    def _aligned_cell(v):
        return _txt("pending screening") if align_pending else _num(_eur(v))
    gar_rows = []
    for r in gg["rows"]:
        note = " (excluded from covered assets)" if r["counterparty"] == "General governments" else ""
        gar_rows.append({"type": "row", "cells": [
            _txt(r["counterparty"] + note), _num(_eur(r["gross"])), _num(_eur(r["eligible"])), _aligned_cell(r["aligned"])]})
    gar_rows.append({"type": "row", "cells": [
        _txt("Covered assets (GAR denominator · excl. general governments)"),
        _num(_eur(gg["covered_assets"])), _num(_eur(gg["eligible"])), _aligned_cell(gg["aligned"])]})
    gar_rows.append({"type": "row", "cells": [
        _txt("Green Asset Ratio — on stock"), _txt("—"),
        _num(f'{gg["pct_eligible"]}% eligible' if gg["pct_eligible"] is not None else "—"),
        _txt("pending screening") if align_pending else
        _num(f'{gg["gar_stock_pct"]}% GAR' if gg["gar_stock_pct"] is not None else "—")]})
    note = gg["basis"] + " Customer-supplied / not shown: " + " · ".join(gg["customer_columns"]) + "."
    if align_pending:
        note += (" This book is classified to Taxonomy ELIGIBILITY; the aligned figure and GAR await the "
                 "technical-screening-criteria + DNSH confirmation, so both are shown as pending, not zero.")
    # the Pillar 3 annex retitles this from its governing specification; elsewhere it is the Taxonomy Art. 8 KPI
    return {"title": "Green Asset Ratio by counterparty (Delegated Regulation (EU) 2021/2178)", "key": "gar",
            "columns": ["Counterparty class", "Gross carrying amount", "Taxonomy-eligible", "Taxonomy-aligned"],
            "col_sources": ["", "computed", "computed", "integrated"],
            "rows": gar_rows, "note": note}


def _gar_flat_summary_section(dps: dict, total) -> dict | None:
    """Fallback GAR section when there is no per-asset book — the flat eligibility summary."""
    if not any(k in dps for k in ("taxonomy.eligible_value_eur", "taxonomy.not_eligible_value_eur")):
        return None
    gar_rows = []
    for key, label in [("taxonomy.eligible_value_eur", "Taxonomy-eligible exposures"),
                       ("taxonomy.not_eligible_value_eur", "Not eligible"),
                       ("taxonomy.not_assessed_value_eur", "Not assessed / no data")]:
        d = dps.get(key)
        gar_rows.append({"type": "row", "cells": [
            _txt(label), _cell(dps, key), _txt(_pct_text((d or {}).get("value"), total))]})
    gar_rows.append({"type": "row", "cells": [_txt("Total covered assets"), _cell(dps, "book.total_value_eur"), _txt("100%")]})
    return {"title": "EU Taxonomy · Article 8 — Green Asset Ratio (summary)", "key": "gar",
            "columns": ["KPI", "Amount", "% of covered assets"], "rows": gar_rows,
            "note": "Eligibility KPI per Disclosures Delegated Act (EU) 2021/2178. Alignment (DNSH + minimum "
                    "safeguards) additionally needs the technical screening criteria (per-asset book unavailable "
                    "for the full counterparty grid)."}


# EU-Taxonomy Annex VI (Del. Reg. 2021/2178) — the six environmental objectives, in the official order.
_TAXONOMY_OBJECTIVES = [
    ("Climate change mitigation", False),
    ("Climate change adaptation", True),   # the one objective this platform assesses (via the physical-risk book)
    ("Water & marine resources", False),
    ("Circular economy", False),
    ("Pollution prevention & control", False),
    ("Biodiversity & ecosystems", False),
]


def _taxonomy_gar_kpi_sections(assets: list[dict]) -> list[dict]:
    """EU-Taxonomy Art. 8 Annex VI — the T0 Summary of KPIs and the T3 GAR-stock-by-objective template, to sit
    alongside the counterparty-class grid. T0 is fully computed from the book; T3 renders the official
    objective axis with Climate-Change-Adaptation ELIGIBILITY computed (this platform's objective) and the
    per-objective mapping / Turnover-vs-CapEx weighting / alignment (TSC + DNSH) declared customer-supplied —
    the official structure, nothing fabricated."""
    if not assets:
        return []
    from services.governance.pillar3_templates import gar_grid
    gg = gar_grid(assets)
    align_pending = gg["aligned"] == 0 and gg["eligible"] > 0

    # T0 — Summary of KPIs (Annex VI Template 0), computed.
    t0 = {
        "title": "Template 0 — Summary of KPIs (Annex VI · Del. Reg. 2021/2178)",
        "columns": ["KPI", "Amount", "% of covered assets"],
        "col_sources": ["", "computed", "computed"],
        "rows": [
            {"type": "row", "cells": [_txt("Total assets"), _num(_eur(gg["total_assets"])), _txt("")]},
            {"type": "row", "cells": [_txt("Covered assets (GAR denominator · excl. general governments, Art. 7)"),
                                      _num(_eur(gg["covered_assets"])), _txt("100%")]},
            {"type": "row", "cells": [_txt("Taxonomy-eligible"), _num(_eur(gg["eligible"])),
                                      _txt(f'{gg["pct_eligible"]}%' if gg["pct_eligible"] is not None else "—")]},
            {"type": "row", "cells": [_txt("Taxonomy-aligned (GAR numerator)"),
                                      _txt("pending screening") if align_pending else _num(_eur(gg["aligned"])),
                                      _txt("pending screening") if align_pending
                                      else _num(f'{gg["gar_stock_pct"]}%' if gg["gar_stock_pct"] is not None else "—")]},
        ],
        "note": "Green Asset Ratio (on stock) = Taxonomy-aligned ÷ covered assets; covered assets exclude "
                "general governments (Art. 7). " + ("This book is classified to eligibility; alignment awaits "
                "the technical-screening-criteria + DNSH confirmation, shown as pending, not zero." if align_pending else ""),
    }

    # T3 — GAR KPI (stock) by environmental objective (Annex VI Template 3), the official axis.
    t3_rows = []
    for obj, is_cca in _TAXONOMY_OBJECTIVES:
        if is_cca:
            # Climate-Change-Adaptation eligibility IS what our physical-risk classifier assesses.
            elig_cell = _num(_eur(gg["eligible"]))
            aligned_cell = _txt("pending screening") if align_pending else _num(_eur(gg["aligned"]))
        else:
            elig_cell, aligned_cell = _mnum("—", "integrated"), _mnum("—", "integrated")
        t3_rows.append({"type": "row", "cells": [_txt(obj), elig_cell, aligned_cell]})
    t3 = {
        "title": "Template 3 — GAR KPI (stock) by environmental objective",
        "columns": ["Environmental objective", "Taxonomy-eligible", "Taxonomy-aligned"],
        "col_sources": ["", "computed", "integrated"],
        "rows": t3_rows,
        "note": "This platform assesses the Climate-Change-Adaptation objective (from the physical-risk book), "
                "so its eligibility is computed; the other five objectives, the per-activity objective mapping, "
                "the Turnover-KPI vs CapEx-KPI weighting, and alignment (technical screening criteria + DNSH) "
                "are customer-supplied. Full Annex VI additionally has Templates 1–2 (assets/sector), T4 (flow), "
                "and T5 (off-balance-sheet).",
    }
    return [t0, t3]


def _located_annex(dps: dict, payload: dict | None = None) -> list[dict]:
    total = (dps.get("book.total_value_eur") or {}).get("value")
    assets = (payload or {}).get("assets") or []
    sections: list[dict] = []

    # EU-Taxonomy Art. 8 (Annex VI). With a per-asset book: T0 Summary of KPIs, the FULL Templates 6–8 GAR
    # grid by counterparty class, and the T3 GAR-by-objective template. Without a per-asset book, the flat
    # eligibility summary.
    if assets:
        sections += _taxonomy_gar_kpi_sections(assets)
        gar_section = _gar_grid_section(assets)
        if gar_section:
            sections.append(gar_section)
    else:
        flat = _gar_flat_summary_section(dps, total)
        if flat:
            sections.append(flat)

    # PCAF financed emissions
    if any(k in dps for k in ("emissions.scope1", "emissions.total")):
        em_rows = [{"type": "row", "cells": [_txt(label), _cell(dps, key)]} for key, label in [
            ("emissions.scope1", "Scope 1"), ("emissions.scope2", "Scope 2"),
            ("emissions.scope3", "Scope 3 (financed)"), ("emissions.total", "Total financed emissions")]]
        sections.append({"title": "Financed emissions · PCAF (tCO₂e)", "columns": ["Scope", "tCO₂e"],
                         "rows": em_rows, "note": None})

    # TCFD metrics & targets — physical-risk exposure by hazard
    sections += _tcfd_physical_sections(dps)
    # Computed credit-risk analytics from the projected book (expected loss, transition, collateral stranding)
    sections += _bank_analytics_sections(payload or {})
    return sections


def _bank_analytics_sections(payload: dict) -> list[dict]:
    """The bank's computed credit-risk analytics rendered as official-form sections: physical expected loss
    (IFRS-9/ECL-relevant), counterparty transition risk, and real-estate-collateral energy-stranding."""
    sections: list[dict] = []

    el = payload.get("expected_loss") or {}
    if el.get("annual_el_eur") is not None:
        sections.append({
            "title": "Physical climate expected loss (IFRS 9 / ECL-relevant)",
            "columns": ["Measure", "Amount"], "rows": [
                {"type": "row", "cells": [_txt("Exposure at default (EAD)"), _mnum(_eur(el.get("total_ead_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Annual expected loss"), _mnum(_eur(el.get("annual_el_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Annual expected loss (bps of EAD)"), _num(f"{el.get('annual_el_bps')} bps")]},
                {"type": "row", "cells": [_txt("Lifetime expected loss (maturity-matched)"), _mnum(_eur(el.get("lifetime_el_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Lifetime expected loss (bps of EAD)"), _num(f"{el.get('lifetime_el_bps')} bps")]},
            ],
            "note": (f"Scenario {el.get('scenario')}. Physical EL = exposure × P(event/yr) × collateral-impairment "
                     "severity (loss curve × disclosed vulnerability-adjusted haircut schedule). Lifetime EL "
                     f"accumulates annual EL over each loan's residual maturity ({el.get('maturity_fed')}/{el.get('n_assets')} "
                     "maturity-fed). A disclosed relative model, not a fitted PD·LGD.")})

    tr = payload.get("transition") or {}
    if tr.get("available"):
        sections.append({
            "title": "Transition risk — counterparty (financed emissions + carbon-price expected loss)",
            "columns": ["Measure", "Amount"], "rows": [
                {"type": "row", "cells": [_txt("Financed emissions (Scope 1+2, reported + estimated)"), _num(f"{tr.get('financed_emissions_tco2e'):,} tCO₂e")]},
                {"type": "row", "cells": [_txt("Emissions reported (vs NACE-estimated)"), _num(f"{tr.get('emissions_reported_pct')}%")]},
                {"type": "row", "cells": [_txt("Transition expected loss"), _mnum(_eur(tr.get("transition_expected_loss_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Transition EL (% of outstanding)"), _num(f"{tr.get('transition_el_pct_of_outstanding')}%")]},
            ],
            "note": "Financed emissions = counterparty Scope 1+2 (reported or NACE-intensity estimated, flagged); a "
                    "rigorous PCAF attribution additionally needs counterparty EVIC (customer-supplied). Transition EL "
                    "= outstanding × modelled stranded-asset fraction (NGFS carbon price + sector tiers), a disclosed "
                    "relative tier, not a fitted PD model."})

    cs = payload.get("collateral_stranding") or {}
    if cs.get("available"):
        sections.append({
            "title": "Transition risk — real-estate collateral energy-stranding (LGD driver)",
            "columns": ["Measure", "Amount"], "rows": [
                {"type": "row", "cells": [_txt(f"Collateral value at risk (below EPC-{cs.get('floor_epc')} floor)"), _mnum(_eur(cs.get("collateral_value_at_risk_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Exposure-weighted LTV — original → stressed"), _num(f"{cs.get('exposure_weighted_ltv_pct')}% → {cs.get('stressed_ltv_pct')}% (+{cs.get('ltv_uplift_pp')}pp)")]},
                {"type": "row", "cells": [_txt("Loan exposure uncovered (LTV > 100%)"), _mnum(_eur(cs.get("loan_value_at_risk_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Retrofit capex to de-risk"), _mnum(_eur(cs.get("retrofit_capex_to_derisk_eur")), "computed")]},
                {"type": "row", "cells": [_txt("RE loans below floor / assessed"), _num(f"{cs.get('n_below_floor')}/{cs.get('n_re_loans')} · {cs.get('epc_coverage_pct')}% with EPC")]},
            ],
            "note": "Disclosed EPBD-recast policy scenario (rising minimum-EPC-to-let floor), not a market fit. "
                    "Collateral erosion lifts effective LTV and, where the stressed collateral no longer covers the "
                    "loan, puts loan value at risk (an LGD driver). Loans with no EPC excluded and reported as coverage."})

    return sections


def _tcfd_physical_sections(dps: dict) -> list[dict]:
    """TCFD 'Metrics & targets' — physical-climate-risk exposure by hazard. Shared by the bank/insurer
    located annex and the REIT annex (a REIT's property book is scored the same way)."""
    haz_keys = sorted([k for k in dps if k.startswith("hazard.")], key=lambda k: -((dps[k].get("value")) or 0))
    haz_rows = []
    for key in ("book.value_at_risk_eur", "book.pct_value_at_risk", "book.total_discounted_value_eur"):
        if key in dps:
            haz_rows.append({"type": "row", "cells": [_txt(dps[key]["label"]), _cell(dps, key)]})
    if haz_keys:
        haz_rows.append({"type": "subheader", "label": "Value exposed at High+ by hazard"})
        for key in haz_keys:
            haz_rows.append({"type": "row", "cells": [_txt(_pretty_hazard(dps[key].get("label") or key.split(".", 1)[1])), _cell(dps, key)]})
    if not haz_rows:
        return []
    return [{"title": "TCFD · Metrics & targets — physical climate risk",
             "columns": ["Metric", "Value"], "rows": haz_rows, "note": None}]


# ── REIT — EU-Taxonomy Article 8 NON-FINANCIAL KPI templates (Turnover/CapEx/OpEx) + TCFD physical ──────────
# Correctness: a REIT is a NON-FINANCIAL undertaking. It does NOT file a Green Asset Ratio (that is credit-
# institutions only, Del. Reg. 2021/2178 Annex V). It files the three Taxonomy KPIs — Turnover, CapEx, OpEx —
# on the Annex II template. The KPI figures are financial-statement data (customer), so we render the exact
# template row structure and declare them customer-supplied; the property book's eligible activity and our
# physical-climate-risk assessment (which feeds the Climate-Change-Adaptation objective and its DNSH test) are
# surfaced explicitly. Nothing is fabricated.
_TAXONOMY_KPI_ROWS = [
    ("A. Taxonomy-eligible activities", True),
    ("A.1 Environmentally sustainable (Taxonomy-aligned)", False),
    ("       of which enabling", False),
    ("       of which transitional", False),
    ("A.2 Taxonomy-eligible but not environmentally sustainable (not aligned)", False),
    ("Total (A.1 + A.2)", False),
    ("B. Taxonomy-non-eligible activities", True),
    ("Total (A + B)", False),
]


def _reit_annex(dps: dict, payload: dict) -> list[dict]:
    sections: list[dict] = []
    total = (dps.get("book.total_value_eur") or {}).get("value")
    elig = (dps.get("taxonomy.eligible_value_eur") or {}).get("value")

    # The three KPI templates (Annex II). Figures are the undertaking's Turnover/CapEx/OpEx proportions —
    # financial-statement data we do not hold — so every cell is declared customer-supplied ("—").
    kpi_rows = []
    for label, is_header in _TAXONOMY_KPI_ROWS:
        if is_header:
            kpi_rows.append({"type": "subheader", "label": label})
        else:
            kpi_rows.append({"type": "row", "cells": [_txt(label), _txt("—"), _txt("—"), _txt("—")]})
    sections.append({
        "title": "EU Taxonomy · Article 8 — Turnover / CapEx / OpEx KPIs (non-financial undertaking)",
        "columns": ["Proportion of", "Turnover KPI", "CapEx KPI", "OpEx KPI"], "rows": kpi_rows,
        "note": "Del. Reg. (EU) 2021/2178, Annex II. A REIT files these three KPIs — NOT a Green Asset Ratio "
                "(the GAR is for credit institutions only). The proportions are financial-statement figures "
                "(turnover, capital and operating expenditure) supplied by the undertaking. The eligible economic "
                "activity for a property book is 'acquisition and ownership of buildings' (Taxonomy 7.7); alignment "
                "additionally needs the technical screening criteria, DNSH and minimum safeguards.",
    })

    # Where OUR data plugs in: the physical-climate-risk assessment IS the evidence for the Climate-Change-
    # Adaptation objective and its DNSH check. Surfaced on an asset (book-value) basis — informational, clearly
    # NOT the KPI basis — so the preparer sees what we contribute without conflating the two.
    if isinstance(elig, (int, float)) and isinstance(total, (int, float)) and total:
        sections.append({
            "title": "Property book — Taxonomy-eligible activity & adaptation evidence (asset basis, informational)",
            "columns": ["Measure", "Amount", "% of book"], "rows": [
                {"type": "row", "cells": [_txt("Property book eligible for activity 7.7 (acquisition & ownership of buildings)"),
                                          _cell(dps, "taxonomy.eligible_value_eur"), _txt(_pct_text(elig, total))]},
                {"type": "row", "cells": [_txt("Total property book"), _cell(dps, "book.total_value_eur"), _txt("100%")]},
            ],
            "note": "Asset-value basis — informational, NOT the Turnover/CapEx/OpEx KPI basis above. Our physical-"
                    "climate-risk assessment (see TCFD section) is the evidence base for the Climate-Change-"
                    "Adaptation substantial-contribution and the 'do no significant harm to adaptation' criterion.",
        })

    # TCFD physical-risk — the property book scored by hazard (genuinely computed by our engine).
    sections += _tcfd_physical_sections(dps)

    # Computed transition + adaptation analytics from the frozen rollup.
    rollup = (payload or {}).get("rollup") or {}
    es = rollup.get("energy_stranding") or {}
    if es.get("n_assessed"):
        sections.append({
            "title": "Transition risk — energy-performance stranding (rising minimum-EPC floor)",
            "columns": ["Measure", "Amount"], "rows": [
                {"type": "row", "cells": [_txt(f"Value at stranding risk (below EPC-{es.get('floor_epc')})"), _mnum(_eur(es.get("value_at_stranding_risk_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Retrofit capex to de-risk"), _mnum(_eur(es.get("retrofit_capex_to_derisk_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Portfolio value below floor"), _num(f"{es.get('pct_portfolio_value_below_floor')}%")]},
                {"type": "row", "cells": [_txt("Properties below floor / assessed"), _num(f"{es.get('n_below_floor')}/{es.get('n_assessed')} · {es.get('epc_coverage_pct')}% with EPC")]},
            ],
            "note": "Disclosed EPBD-recast policy scenario (rising minimum-to-let EPC floor), not a market fit. "
                    "Properties without an EPC excluded and reported as coverage, never assigned a fabricated number."})

    rc = rollup.get("resilience_capex") or {}
    if rc.get("available"):
        sections.append({
            "title": "Adaptation — resilience capex vs avoided loss (EU-Taxonomy adaptation)",
            "columns": ["Measure", "Amount"], "rows": [
                {"type": "row", "cells": [_txt("Resilience / adaptation capex"), _mnum(_eur(rc.get("total_resilience_capex_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Avoided physical loss"), _mnum(_eur(rc.get("total_avoided_loss_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Portfolio benefit-cost ratio"), _num(f"{rc.get('portfolio_benefit_cost_ratio')}×" if rc.get("portfolio_benefit_cost_ratio") is not None else "—")]},
                {"type": "row", "cells": [_txt("Taxonomy adaptation-aligned capex"), _mnum(_eur(rc.get("taxonomy_adaptation_aligned_capex_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Properties worth retrofitting"), _num(f"{rc.get('n_worth_retrofit')}/{rc.get('n_properties')}")]},
            ],
            "note": "Adaptation capex modelled per hazard against the physical loss it avoids; the Taxonomy-aligned "
                    "portion is the evidence base for the Climate-Change-Adaptation substantial-contribution objective."})

    return sections


# ── Insurer — NatCat / underwriting climate exposure (EIOPA · IFRS S2) ─────────────────────────────────────
# Correctness: an insurer's climate filing is about its UNDERWRITING book, not a bank's loan book. It does NOT
# file a Green Asset Ratio or PCAF financed-emissions on assets (that is the bank located annex); it discloses
# natural-catastrophe exposure — sum insured at risk by peril and geography, and expected annual loss (EAL) /
# NatCat loss ratio by severity band. Every figure is the frozen NatCat-engine snapshot (rollup + by_hazard +
# per-policy), rendered computed; a book without priced policies renders "—", never a fabricated loss.
_INS_BUCKET_LABEL = {"VH": "Very high", "H": "High", "M": "Medium", "L": "Low", "none": "Not scored"}
_INS_BUCKET_ORDER = ["VH", "H", "M", "L", "none"]


def _insurer_annex(dps: dict, payload: dict) -> list[dict]:
    sections: list[dict] = []
    rollup = (payload or {}).get("rollup") or {}
    by_hazard = (payload or {}).get("by_hazard") or {}
    policies = (payload or {}).get("policies") or []
    total_si = rollup.get("total_sum_insured_eur")
    by_bucket = rollup.get("by_bucket") or {}
    si_at_risk = sum((by_bucket.get(b, {}) or {}).get("sum_insured_eur", 0) for b in ("VH", "H"))

    # 1 — Underwriting NatCat exposure summary (the headline EIOPA / IFRS S2 figures).
    summ_rows = [
        {"type": "row", "cells": [_txt("Total sum insured (underwriting book)"), _mnum(_eur(total_si), "computed")]},
        {"type": "row", "cells": [_txt("Sum insured at risk (High + Very high)"), _mnum(_eur(si_at_risk), "computed"),
                                  _txt(_pct_text(si_at_risk, total_si))]},
        {"type": "row", "cells": [_txt("Expected annual loss (NatCat)"), _mnum(_eur(rollup.get("total_expected_annual_loss_eur")), "computed"), _txt("")]},
        {"type": "row", "cells": [_txt("Gross written premium"), _mnum(_eur(rollup.get("total_gross_premium_eur")), "computed"), _txt("")]},
        {"type": "row", "cells": [_txt("Modelled NatCat loss ratio"),
                                  _num(f"{rollup['portfolio_loss_ratio_pct']}%" if rollup.get("portfolio_loss_ratio_pct") is not None else "—"), _txt("")]},
    ]
    sections.append({
        "title": "NatCat underwriting exposure — summary (EIOPA · IFRS S2)",
        "columns": ["Metric", "Amount", "% of sum insured"], "rows": summ_rows,
        "note": "Expected annual loss = probability-weighted scenario loss across the book (mean-damage-ratio × "
                "per-peril occurrence frequency); loss ratio = modelled claims ÷ gross written premium. Computed by "
                "the Tellumen NatCat engine from the frozen snapshot.",
    })

    # 2 — Sum insured at risk by peril (High+), the per-event-type nat-cat table.
    haz_rows = []
    for hz in sorted(by_hazard, key=lambda h: -((by_hazard[h] or {}).get("exposed_value_eur") or 0)):
        h = by_hazard[hz] or {}
        haz_rows.append({"type": "row", "cells": [
            _txt(_pretty_hazard(hz)), _mnum(_eur(h.get("exposed_value_eur")), "computed"),
            _num(str(h.get("n_exposed", 0))), _num(f"{h.get('max_score', 0)}")]})
    if haz_rows:
        sections.append({
            "title": "Sum insured at risk by peril (High+) — per event type",
            "columns": ["Peril", "Sum insured exposed", "Policies exposed", "Max hazard score"],
            "col_sources": ["", "computed", "computed", "computed"], "rows": haz_rows,
            "note": "Sum insured on policies whose peril score is High or Very high, by peril. The 'event type' axis "
                    "of the EIOPA NatCat template (windstorm, flood, earthquake, wildfire, …).",
        })

    # 3 — Exposure & expected annual loss by severity band.
    band_rows = []
    for b in _INS_BUCKET_ORDER:
        v = by_bucket.get(b)
        if not v:
            continue
        band_rows.append({"type": "row", "cells": [
            _txt(_INS_BUCKET_LABEL[b]), _num(str(v.get("count", 0))),
            _mnum(_eur(v.get("sum_insured_eur")), "computed"), _mnum(_eur(v.get("eal_eur")), "computed")]})
    if band_rows:
        sections.append({
            "title": "Exposure & expected annual loss by risk band",
            "columns": ["Risk band", "Policies", "Sum insured", "Expected annual loss"],
            "col_sources": ["", "computed", "computed", "computed"], "rows": band_rows, "note": None})

    # 4 — Sum insured at risk by geography (High+), aggregated from the frozen policy list.
    geo: dict = {}
    for p in policies:
        if (p.get("headline_bucket") or "") in ("H", "VH"):
            region = p.get("region") or "Unspecified"
            g = geo.setdefault(region, {"si": 0.0, "n": 0})
            g["si"] += p.get("sum_insured_eur") or 0
            g["n"] += 1
    if geo:
        geo_rows = [{"type": "row", "cells": [_txt(region), _mnum(_eur(v["si"]), "computed"), _num(str(v["n"]))]}
                    for region, v in sorted(geo.items(), key=lambda kv: -kv[1]["si"])]
        sections.append({
            "title": "Sum insured at risk by geography (High+)",
            "columns": ["Region", "Sum insured exposed", "Policies exposed"],
            "col_sources": ["", "computed", "computed"], "rows": geo_rows,
            "note": "Geographic concentration of NatCat exposure — sum insured on High+ policies aggregated by the "
                    "policy's region."})

    # 5 — Catastrophe accumulation (AEP/OEP exceedance & PML) — the correlated tail the summed EALs hide.
    cat = rollup.get("catastrophe") or {}
    if cat.get("available"):
        aep, oep = cat.get("aep_eur") or {}, cat.get("oep_eur") or {}
        rp_rows = []
        for t in (10, 50, 100, 200, 250):
            a, o = aep.get(f"rp_{t}"), oep.get(f"rp_{t}")
            if a is None and o is None:
                continue
            rp_rows.append({"type": "row", "cells": [_txt(f"1-in-{t} year"), _mnum(_eur(a), "computed"), _mnum(_eur(o), "computed")]})
        if rp_rows:
            sections.append({
                "title": "Catastrophe accumulation — exceedance losses (AEP / OEP)",
                "columns": ["Return period", "Aggregate (AEP)", "Single-event (OEP)"],
                "col_sources": ["", "computed", "computed"], "rows": rp_rows,
                "note": (f"Common-shock Monte-Carlo over {cat.get('n_zones', '—')} (peril × region) accumulation zones "
                         f"({cat.get('n_years', '—'):,} simulated years). PML (1-in-{cat.get('pml_return_period')}) = "
                         f"{_eur(cat.get('pml_eur'))}; simulated mean {_eur(cat.get('mean_annual_loss_eur'))} reconciles "
                         "to the independent EAL sum. Correlation perfect within a zone, independent across zones; not a "
                         "fitted vendor cat model.")})

    # 6 — Solvency II NatCat SCR: internal-model basis (99.5% VaR) side by side with the prescribed
    # standard formula (EIOPA's own per-region factors, computed via services/governance/solvency2_natcat.py
    # and already served on the /solvency-scr endpoint — see api/routers/insurance.py::_scr_from_cat).
    scr = (payload or {}).get("solvency_scr") or {}
    if scr.get("available"):
        sf = scr.get("standard_formula_natcat") or {}
        rows = [
            {"type": "subheader", "label": "Internal model — 99.5% VaR (own common-shock catastrophe accumulation)"},
            {"type": "row", "cells": [_txt("NatCat SCR — 1-in-200 annual aggregate (99.5% VaR)"), _mnum(_eur(scr.get("natcat_scr_eur")), "computed")]},
            {"type": "row", "cells": [_txt("Single largest event — 1-in-200 (OEP)"), _mnum(_eur(scr.get("oep_1_in_200_eur")), "computed")]},
            {"type": "row", "cells": [_txt("Mean annual loss"), _mnum(_eur(scr.get("mean_annual_loss_eur")), "computed")]},
            {"type": "row", "cells": [_txt("Risk load (capital above expected loss)"), _mnum(_eur(scr.get("risk_load_eur")), "computed")]},
            {"type": "row", "cells": [_txt("SCR as % of gross sum insured"), _num(f"{scr.get('scr_pct_of_sum_insured')}%" if scr.get("scr_pct_of_sum_insured") is not None else "—")]},
        ]
        if sf.get("available"):
            rows.append({"type": "subheader", "label": "Standard formula — Del. Reg. (EU) 2015/35, Art. 120-125 (EIOPA's own per-region factors, cited)"})
            rows.append({"type": "row", "cells": [_txt("NatCat SCR — standard formula (√Σ SCR_peril²)"), _mnum(_eur(sf.get("natcat_scr_eur")), "computed")]})
            rows.append({"type": "row", "cells": [_txt("Undiversified sum of peril SCRs"), _mnum(_eur(sf.get("undiversified_sum_eur")), "computed")]})
            rows.append({"type": "row", "cells": [_txt("Cross-peril diversification benefit"), _mnum(_eur(sf.get("cross_peril_diversification_benefit_eur")), "computed")]})
            for pk, v in (sf.get("scr_by_peril_eur") or {}).items():
                rows.append({"type": "row", "cells": [_txt(f"  · {pk.title()}"), _mnum(_eur(v), "computed")]})
        sections.append({
            "title": "Solvency II — NatCat SCR (internal-model basis, 99.5% VaR"
                     + (" · standard formula" if sf.get("available") else "") + ")",
            "columns": ["Component", "Amount"], "rows": rows,
            "note": ("Internal-model-basis NatCat SCR = modelled 1-in-200 (99.5% VaR) annual-aggregate catastrophe "
                     "loss from our own accumulation model. " +
                     ("The prescribed standard-formula NatCat SCR (EIOPA Delegated Reg. (EU) 2015/35, Art. 120-125, "
                      "Annexes V-VIII) is computed above from EIOPA's own per-region factors — a cited regulatory "
                      "calculation, not a platform model — and shown alongside it; both bases are labelled and, at "
                      "country level, both are live (no external ingest pending)."
                      if sf.get("available") else
                      "The prescribed standard-formula NatCat SCR (EIOPA Delegated Reg. (EU) 2015/35, Art. 120-125) "
                      "could not be computed for this book."))})

    # 7 — Net-of-reinsurance retention (the loss that actually hits capital).
    reins = (payload or {}).get("reinsurance") or {}
    net = reins.get("net") or {}
    if reins.get("available") and net:
        prog = reins.get("program") or {}
        sections.append({
            "title": "Net-of-reinsurance retention (illustrative standard program)",
            "columns": ["Measure", "Gross", "Net of reinsurance"], "rows": [
                {"type": "row", "cells": [_txt(f"PML (1-in-{reins.get('pml_return_period')})"), _mnum(_eur(reins.get("gross_pml_eur")), "computed"), _mnum(_eur(net.get("net_pml_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Mean annual loss"), _mnum(_eur(reins.get("gross_mean_annual_loss_eur")), "computed"), _mnum(_eur(net.get("net_mean_annual_loss_eur")), "computed")]},
                {"type": "subheader", "label": f"Program: {prog.get('quota_share_pct')}% quota share · cat XoL {_eur(prog.get('xol_attachment_eur'))} xs {_eur(prog.get('xol_limit_eur'))}"},
            ],
            "note": ("Illustrative standard program — the insurer configures their own on the live workspace. Quota share is "
                     "exact; the per-occurrence cat XoL recovers on the single largest event (exact on the OEP); a within-year "
                     f"aggregate treaty / reinstatements are not modelled. Cession ratio {net.get('cession_ratio_pct')}%.")})

    # 8 — Investment-side climate VaR (the asset half of the insurer's climate exposure — EIOPA / IFRS S2).
    inv = (payload or {}).get("investments") or {}
    if inv.get("available"):
        cv = inv.get("climate_var") or {}
        sections.append({
            "title": "Investment-side climate VaR — asset book (EIOPA · IFRS S2)",
            "columns": ["Measure", "Amount"], "rows": [
                {"type": "row", "cells": [_txt("Investment book value"), _mnum(_eur(inv.get("total_value_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Combined physical + transition expected loss"), _mnum(_eur(cv.get("combined_expected_eur")), "computed")]},
                {"type": "row", "cells": [_txt("99th-percentile climate VaR"), _mnum(_eur(cv.get("var99_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Positions scored (coverage)"), _num(f"{inv.get('n_scored')}/{inv.get('n_holdings')} · {inv.get('coverage_pct')}%")]},
            ],
            "note": "An insurer is an underwriter AND an institutional investor; EIOPA/IFRS S2 require climate risk on both "
                    "sides. This is the ASSET side — the combined physical + transition climate-VaR engine on the insurer's "
                    "own investment book. Unscored positions excluded and reported as coverage."})

    return sections


def _eur(v):
    """Readable money for a computed annex cell, in the currency the filing presents in (money_format.current, set by
    build_annex from the frozen snapshot — '€' only for a EUR filing)."""
    return money_format.money(v)


# ── Pillar 3 ESG: spec-driven templates ─────
_P3_SPEC_BEFORE_SPECS = "its_2022_2453"     # every Pillar 3 filing frozen before specifications was prepared under it


def _p3_spec(payload: dict) -> dict:
    return _frozen_spec("bank_p3esg", payload)


# the version every filing frozen before specifications existed was prepared under, per framework on the route
_BEFORE_SPECS = {"bank_p3esg": _P3_SPEC_BEFORE_SPECS, "sfdr_pai": "rts_2022_1288"}


def _frozen_spec(framework: str, payload: dict) -> dict | None:
    """The specification a filing was prepared under: its frozen _spec, else the version in use before specs existed."""
    import services.regspec as R
    if framework not in R.frameworks():
        return None
    return R.load(framework, ((payload or {}).get("_spec") or {}).get("version") or _BEFORE_SPECS[framework])


def _p3_title(spec: dict, tid: str) -> str:
    import services.regspec as R
    return f"{R.template(spec, tid)['title']} ({R.citation(spec, tid)})"


def _col_head(c: dict) -> str:
    return f"{c['id']} · {c['label'].split(' > ')[-1]}"


def _col_groups(cols: list[dict]) -> str:
    """'c–o: under “Gross carrying amount > of which …”' — the header levels the flat column list cannot show."""
    out, run = [], None
    for c in cols:
        parent = " > ".join(c["label"].split(" > ")[:-1])
        if run and run[0] == parent:
            run[2] = c["id"]
        else:
            run = [parent, c["id"], c["id"]]
            out.append(run)
    return " · ".join(f"{a if a == b else a + '–' + b} under “{p}”" for p, a, b in out if p)


_P3_FMT = {"T1": {"i": "t", "j": "t", "k": "pct", "p": "yrs"}, "T5": {"g": "yrs"}}


def _spec_grid_section(spec: dict, tid: str, grid: dict, key: str, scope: str | None = None) -> dict:
    import services.regspec as R
    from services.governance.pillar3_grids import BINDING
    t = R.template(spec, tid)
    cols = [c for c in t["columns"] if not BINDING[tid]["columns"][c["id"]].startswith("computed:country")]
    fmt = _P3_FMT.get(tid, {})

    def cell(cid, v):
        src = "computed" if BINDING[tid]["columns"][cid].startswith("computed") else "integrated"
        if v is None:
            return _mnum("—", src)
        kind = fmt.get(cid)
        txt = (f"{v:,.0f}" if kind == "t" else f"{v}%" if kind == "pct" else f"{v}y" if kind == "yrs" else _eur(v))
        return _mnum(txt, src)

    rows = [{"type": "row", "cells": [_txt(f"{r['id']} · {r['label']}")] + [cell(c["id"], r["values"].get(c["id"])) for c in cols]}
            for r in grid["rows"]]
    st = grid["stated"]
    supplied = [f"{lbl} stated for {st[k]:,} of {st['all']:,} exposures" if tid == "T1"
                else f"{lbl} stated for {st[k]:,} of {st['sens']:,} physical-risk-sensitive exposures" for k, lbl in
                (("stage", "IFRS 9 stage"), ("mat", "maturity"), ("imp", "impairment"))
                + ((("pab", "Paris-benchmark exclusion"), ("ccm", "CCM sustainability"), ("rep", "company-reported emissions"))
                   if tid == "T1" else ())]
    notes = [_col_groups(t["columns"]),
             "Blank (—) = no exposure in the row states that fact on the loan tape; " + "; ".join(supplied) + ".",
             f"Counterparty sector inferred from the NACE code for {grid['inferred_counterparty']:,} exposures and immovable "
             f"collateral from the asset type for {grid['inferred_collateral']:,} (state them on the loan tape to replace the inference)."]
    if grid["unallocated_no_nace"]:
        notes.append(f"{grid['unallocated_no_nace']:,} non-financial-corporate exposures carry no NACE code and sit in no sector row.")
    if tid == "T5":
        notes.append("Sensitive = a High or Very high climate hazard at the exposure's location; h, i, j are chronic only, "
                     "acute only and both. Rows 1–9 and 13 hold non-financial corporations by sector; rows 10–12 hold loans "
                     "by their immovable-property collateral, whatever the counterparty — separate groups, so there is no total row.")
    if tid == "T1":
        notes.append("Financed emissions (i, j) are the counterparties' reported Scope 1–3 totals. k is the share of the "
                     "row's gross carrying amount whose emissions the company reported itself (EBA Q&A 2024_7225: over all exposures).")
    title = _p3_title(spec, tid) + (f" — {scope}" if scope else "")
    return {"title": title, "key": key, "columns": ["Row"] + [_col_head(c) for c in cols],
            "col_sources": [""] + ["computed" if BINDING[tid]["columns"][c["id"]].startswith("computed") else "integrated" for c in cols],
            "rows": rows, "note": " ".join(n for n in notes if n),
            "spec": {"version": spec["version"], "template": tid, "sha256": spec["_sha256"]}}


# ── EBA Pillar 3 ESG: the templates, titled and cited from the governing specification ─────
def _p3esg_annex(dps: dict, payload: dict) -> list[dict]:
    total = (dps.get("book.total_value_eur") or {}).get("value")
    sections: list[dict] = []
    assets = (payload or {}).get("assets") or []

    # Templates 1 and 5 are built to the specification the filing was prepared under (frozen as _spec; a filing
    # frozen before specifications existed was prepared under ITS 2022/2453). Rows, columns and titles come from it.
    spec = _p3_spec(payload)
    if assets:
        from services.governance.pillar3_grids import build as p3_build
        sections.append(_spec_grid_section(spec, "T1", p3_build(spec, "T1", assets), key="t1"))

    # Template 2 — loans collateralised by immovable property · energy efficiency of the collateral (ITS
    # 2022/2453, Annex XXXIX + Annex XL instructions). Built to the EXACT fixed-format grid: columns (a) total +
    # (b)-(g) EP-score kWh/m² buckets + (h)-(n) EPC labels A-G + (o) without-EPC + (p) % estimated; rows = EU /
    # non-EU area, each split commercial / residential / repossessed / estimated. Every figure is the EPC label
    # + EP-score + collateral-type + location of the collateral — held on the institution's collateral register /
    # EPC feed, NOT computable from the physical-risk engine — so the whole grid is source='integrated'.
    if assets:
        t2_cols = ["Energy efficiency of the collateral", "Total gross carrying amount",
                   "0–≤100", ">100–≤200", ">200–≤300", ">300–≤400", ">400–≤500", ">500",  # (b)-(g) kWh/m²
                   "EPC A", "EPC B", "EPC C", "EPC D", "EPC E", "EPC F", "EPC G",           # (h)-(n)
                   "Without EPC label", "of which est. (%)"]                                 # (o)-(p)
        t2_src = [""] + ["integrated"] * (len(t2_cols) - 1)
        _t2blank = [dict(_mnum("—", "integrated")) for _ in range(len(t2_cols) - 1)]

        def _t2row(label):
            return {"type": "row", "cells": [_txt(label)] + [dict(c) for c in _t2blank]}

        # EPC label (A–G) distribution from the per-loan attributes the institution provides — EPC applies to
        # real-estate collateral, so a loan carrying an EPC label is placed by its label + area (EU vs non-EU
        # from the collateral country). The commercial/residential split and the kWh/m² EP-score buckets aren't
        # in the loan-tape attribute set, so those cells stay '—'.
        _EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
               "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}
        _LABELS = ["A", "B", "C", "D", "E", "F", "G"]
        acc = {"EU": {"total": 0.0, **{lbl: 0.0 for lbl in _LABELS}}, "nonEU": {"total": 0.0, **{lbl: 0.0 for lbl in _LABELS}}}
        n_epc = 0
        for a in assets:
            epc = str(a.get("epc_label") or "").strip().upper()
            if epc not in _LABELS:
                continue
            gross = a.get("outstanding_loan_balance_eur") or a.get("value_eur") or 0
            if not gross:
                continue
            n_epc += 1
            area = "EU" if (a.get("country") or "").upper() in _EU else "nonEU"
            acc[area]["total"] += gross
            acc[area][epc] += gross

        def _t2total_row(area_key):
            d = acc[area_key]
            return {"type": "row", "cells": [_txt("Total — all collateral"),
                    _mnum(_eur(round(d["total"], 2)), "integrated"),                # (a) total
                    *[dict(_mnum("—", "integrated")) for _ in range(6)],            # (b)-(g) kWh EP-score buckets
                    *[_mnum(_eur(round(d[lbl], 2)), "integrated") for lbl in _LABELS],  # (h)-(n) EPC A–G
                    dict(_mnum("—", "integrated")), dict(_mnum("—", "integrated"))]}  # (o) without · (p) % est.

        t2_rows = []
        for area_key, area_label in (("EU", "Total EU area (Union)"), ("nonEU", "Total non-EU area")):
            t2_rows.append({"type": "subheader", "label": area_label})
            t2_rows.append(_t2total_row(area_key) if n_epc else _t2row("Total — all collateral"))
            t2_rows.append(_t2row("of which · loans collateralised by commercial immovable property"))
            t2_rows.append(_t2row("of which · loans collateralised by residential immovable property"))
            t2_rows.append(_t2row("of which · collateral obtained by taking possession"))
            t2_rows.append(_t2row("of which · level of energy efficiency (EP score) estimated"))
        _epc_note = (f" EPC labels A–G are filled from the {n_epc} loans carrying an EPC label in the attributes you "
                     "provided (placed by label and EU/non-EU collateral location); the commercial/residential split "
                     "and kWh/m² EP-score buckets aren't in that attribute set, so they stay '—'." if n_epc else
                     " EPC labels, EP scores, collateral type and location live on the institution's collateral register / "
                     "EPC feed — shown '—' until that feed is connected.")
        sections.append({"title": _p3_title(spec, "T2"),
                         "key": "t2", "columns": t2_cols, "col_sources": t2_src, "rows": t2_rows,
                         "note": "Fixed format per Annex XL. Gross carrying amount of loans collateralised by commercial / "
                                 "residential immovable property and repossessed real estate, distributed by the collateral's "
                                 "energy consumption (kWh/m², cols b–g) and EPC label (A–G, cols h–n), split Union / non-Union." + _epc_note})

    # Template 3 / EU CRFR4 (pending adoption; renamed by EBA/ITS/2026/02, not yet in force — see
    # docs/GO_LIVE_EXTERNAL_DEPENDENCIES.md #10) — transition-risk ALIGNMENT METRICS (ITS 2022/2453, Annex
    # XL §38–41): per IEA sector, the portfolio CO₂-intensity + its distance to the IEA NZE2050 2030 target.
    # Gross amount + benchmark + distance computed by Tellumen; the counterparty intensity is a
    # vendor/counterparty feed (shown 'pending' until fed).
    if assets:
        from services.governance.transition_alignment import template3_grid
        g3 = template3_grid(assets)
        if g3["rows"]:
            t3_rows = []
            for r in g3["rows"]:
                cur = f'{r["current_intensity"]} {r["unit"]}' if r["current_intensity"] is not None else "pending vendor feed"
                tgt = f'{r["iea_2030"]} {r["unit"]}' if r["iea_2030"] is not None else "pending IEA ingest"
                dist = f'{r["distance_pct"]}%' if r["distance_pct"] is not None else "—"
                t3_rows.append({"type": "row", "cells": [
                    _txt(f'{r["label"]} · {r["metric"]}'), _num(_eur(r["gross"])), _num(cur), _num(tgt), _num(dist)]})
            sections.append({"title": _p3_title(spec, "T3"),
                             "columns": ["Sector · IEA metric", "Gross carrying amount", "Portfolio intensity", "IEA NZE2050 2030 target", "Distance"],
                             "col_sources": ["", "computed", "integrated", "computed", "computed"],
                             "rows": t3_rows,
                             "note": g3["formula"] + ". " + g3["source"] + " Customer/vendor input: " + g3["customer_input"]})

    # Template 4 — exposures to the top-20 carbon-intensive firms (ITS 2022/2453, Annex XL §42–44).
    # Per EBA/ITS/2026/02 (pending adoption): DELETED outright, not renamed, in the amended ITS — kept here
    # under its current, in-force name until that ITS is adopted (see docs/GO_LIVE_EXTERNAL_DEPENDENCIES.md #10).
    if assets:
        from services.governance.transition_alignment import template4_top20
        g4 = template4_top20(assets)
        if g4["matched_count"]:
            t4_rows = [{"type": "row", "cells": [_txt(r["firm"]), _num(_eur(r["gross"]))]} for r in g4["rows"]]
        else:
            t4_rows = [{"type": "row", "cells": [_txt("No counterparty matched the top-20 carbon-majors list"), _num(_eur(0))]}]
        sections.append({"title": _p3_title(spec, "T4"),
                         "columns": ["Counterparty (Carbon Majors)", "Gross carrying amount"],
                         "col_sources": ["", "computed"], "rows": t4_rows,
                         "note": f'Matched {g4["matched_count"]} of the {g4["list_size"]}-firm list · total exposure {_eur(g4["total_exposure"])}. ' + g4["source"]})

    if assets:
        from services.governance.pillar3_grids import template5 as p3_t5
        g5 = p3_t5(spec, assets)
        sections.append(_spec_grid_section(spec, "T5", g5, key="t5", scope="All geographies"))
        for geo in g5["geographies"]:           # column a — one instance per geography (Annex XL, Template 5, column a)
            sections.append(_spec_grid_section(spec, "T5", geo, key=f"t5_geo_{geo['geography']}", scope=geo["label"]))
    else:
        # fallback for a snapshot without the per-asset book: the earlier by-hazard summary
        haz_keys = sorted([k for k in dps if k.startswith("hazard.")], key=lambda k: -((dps[k].get("value")) or 0))
        t5_rows = []
        for key in ("book.total_value_eur", "book.value_at_risk_eur", "book.pct_value_at_risk"):
            if key in dps:
                t5_rows.append({"type": "row", "cells": [_txt(dps[key]["label"]), _cell(dps, key)]})
        for key in haz_keys:
            t5_rows.append({"type": "row", "cells": [_txt(_pretty_hazard(dps[key].get("label") or key.split(".", 1)[1])), _cell(dps, key)]})
        if t5_rows:
            sections.append({"title": "Template 5 — Banking book · climate-change physical risk",
                             "columns": ["Exposure metric", f"Amount ({money_format.current.get()})"], "rows": t5_rows,
                             "note": f"Physical-risk exposure per {_p3_title(spec, 'T5')} (per-asset book unavailable for the sector grid)."})

    # GAR (Templates 6–8) — Green Asset Ratio by counterparty class, built to the ITS grid: gross carrying
    # amount, Taxonomy-eligible + Taxonomy-aligned per counterparty, the covered-assets denominator (excl.
    # general governments, Art. 7) and the GAR ratio on stock. Computed from the per-asset taxonomy_status.
    #
    # Pending change (found 2026-09-22, see docs/GO_LIVE_EXTERNAL_DEPENDENCIES.md #10): EBA/ITS/2026/02's
    # Final Report removes Templates 6–9 from the amended Pillar 3 ESG ITS entirely — not renamed, DELETED —
    # because they duplicated the GAR/Taxonomy disclosure that already lives under the Taxonomy Regulation's
    # own Delegated Reg. (EU) 2021/2178, Annex VI (which this platform separately implements in
    # `_taxonomy_art8_annex_vi()` above, T0/T3). Once the amended ITS is adopted, GAR/BTAR should be dropped
    # from THIS Pillar-3 bundle and left solely in the Annex VI section — not duplicated, matching what the
    # EBA itself concluded. Not changed yet: ITS 2022/2453 (which still asks for Templates 6–9 here) remains
    # the current, in-force regulation until the amended ITS is officially published, per the standing rule
    # of running the adopted version, not a still-pending "Final Report".
    gar_section = _gar_grid_section(assets) or _gar_flat_summary_section(dps, total)
    if gar_section:
        import services.regspec as R
        gar_section["title"] = (f"{R.template(spec, 'T7')['title']} · {R.template(spec, 'T8')['title']} "
                                f"({R.citation(spec, 'T7')})")
        sections.append(gar_section)

    # Template 9 — BTAR (banking book taxonomy alignment ratio) · ITS 2022/2453, Annex XXXIX (Templates 9.1/9.2/
    # 9.3) + Annex XL instructions. Also removed (not renamed) by the pending EBA/ITS/2026/02 amendment, same
    # reasoning as Templates 6–8 above — kept here while ITS 2022/2453 remains in force.
    # BTAR extends the GAR to counterparties NOT subject to NFRD disclosure (EU
    # SMEs / non-financial corps + non-EU corporates): the institution "may" disclose it, and must source the
    # alignment by collecting from counterparties bilaterally through loan origination / credit review, or by
    # internal estimates and proxies (Annex XL §9.1). None of that is derivable from our engine — the whole grid
    # is source='integrated' (bilateral collection / estimate), shown '—' until the institution supplies it.
    if assets:
        t9_cols = ["Asset / counterparty class (not subject to NFRD)", "Gross carrying amount",
                   "Taxonomy-eligible", "Taxonomy-aligned"]
        t9_src = ["", "integrated", "integrated", "integrated"]
        def _t9blank():
            return [dict(_mnum("—", "integrated")) for _ in range(3)]
        def _t9row(lbl):
            return {"type": "row", "cells": [_txt(lbl)] + _t9blank()}
        t9_rows = [
            {"type": "subheader", "label": "9.1 — Assets for the calculation of BTAR"},
            _t9row("1 · Total GAR assets (as row 32 of Template 7)"),
            _t9row("2 · EU non-financial corporations (not subject to NFRD)"),
            _t9row("4 · of which · loans collateralised by commercial immovable property"),
            _t9row("5 · of which · building-renovation loans"),
            _t9row("8 · Non-EU non-financial corporations (not subject to NFRD)"),
            _t9row("12 · TOTAL BTAR ASSETS (rows 1 + 2 + 8)"),
            {"type": "subheader", "label": "9.2 / 9.3 — BTAR %"},
            {"type": "row", "cells": [_txt("BTAR — banking book taxonomy alignment ratio (on stock)"),
                                      dict(_mnum("—", "integrated")), dict(_mnum("—", "integrated")),
                                      dict(_mnum("— % BTAR", "integrated"))]},
        ]
        sections.append({"title": _p3_title(spec, "T9"),
                         "key": "t9", "columns": t9_cols, "col_sources": t9_src, "rows": t9_rows,
                         "note": "Voluntary extension of the GAR to counterparties outside the NFRD scope — EU SMEs / "
                                 "non-financial corporates and non-EU corporates. Their Taxonomy alignment is not on any "
                                 "public disclosure, so the institution collects it bilaterally through loan origination and "
                                 "credit review, or uses internal estimates / proxies (Annex XL §9.1) — integrated, never "
                                 "derived from the physical-risk engine. Row 1 carries over the GAR total (Template 7 row 32); "
                                 "TOTAL BTAR = rows 1 + 2 + 8. Shown '—' until the institution supplies the BTAR inputs."})

    # Template 10 — other climate-change-mitigating actions NOT covered by the EU Taxonomy (green/sustainability
    # bonds and specialised green lending) is a preparer-authored register: instrument type is not on the golden-
    # source book, so every field is manual. It is rendered + saved by the editable P3Template10 surface on the
    # official form (endpoint /v1/filings/structured/p3esg-template10), NOT assembled here from the snapshot.

    # Scope-3 financed emissions — only as a fallback when the per-asset book is unavailable (otherwise the
    # Template 1 grid above already carries financed emissions by NACE sector).
    if not assets and any(k in dps for k in ("emissions.scope3", "emissions.total")):
        em_rows = [{"type": "row", "cells": [_txt(label), _cell(dps, key)]} for key, label in [
            ("emissions.scope3", "Scope 3 (financed) emissions"), ("emissions.total", "Total financed emissions")]]
        sections.append({"title": "Transition risk — financed emissions (PCAF, tCO₂e)", "columns": ["Scope", "tCO₂e"],
                         "rows": em_rows, "note": "Counterparty Scope-3 basis for the transition-risk templates (Templates 1–4)."})
    # Computed credit-risk analytics (physical EL, transition EL, collateral stranding) — shared with the bank TCFD annex
    sections += _bank_analytics_sections(payload or {})
    return sections


# ── ESRS / generic — present the reported datapoints in the standard's disclosure-requirement grouping ─────
def _generic_annex(dps: dict, groups: list[dict]) -> list[dict]:
    sections = []
    for g in groups:
        rows = [{"type": "row", "cells": [_txt(d.get("label", "")), {"dp": d}]} for d in g.get("datapoints", [])]
        if rows:
            sections.append({"title": g.get("group", "Disclosure"), "columns": ["Datapoint", "Value"],
                             "rows": rows, "note": None})
    return sections


def _assetmgmt_annex(dps: dict, payload: dict) -> list[dict]:
    """Asset-manager HOLDINGS-book TCFD disclosure: physical-risk exposure by hazard, EU-Taxonomy status, and
    portfolio climate-risk concentration (the diversification lens). Distinct from the fund-level SFDR PAI."""
    sections: list[dict] = []
    rollup = (payload or {}).get("rollup") or {}
    by_hazard = (payload or {}).get("by_hazard") or {}
    tax = (payload or {}).get("taxonomy") or {}
    conc = (payload or {}).get("concentration") or {}

    # 1 — Portfolio physical-risk summary
    total = rollup.get("total_portfolio_value_eur")
    sections.append({
        "title": "Portfolio physical climate-risk — summary (TCFD asset-manager guidance)",
        "columns": ["Metric", "Amount"], "rows": [
            {"type": "row", "cells": [_txt("Total portfolio value"), _mnum(_eur(total), "computed")]},
            {"type": "row", "cells": [_txt("Portfolio climate VaR"), _mnum(_eur(rollup.get("total_climate_var_eur")), "computed")]},
            {"type": "row", "cells": [_txt("Climate VaR (% of portfolio)"), _num(f"{rollup.get('portfolio_climate_var_pct')}%" if rollup.get("portfolio_climate_var_pct") is not None else "—")]},
            {"type": "row", "cells": [_txt("Holdings flagged (High+)"), _num(f"{rollup.get('n_flagged')}/{rollup.get('n_holdings')}")]},
            {"type": "row", "cells": [_txt("Holdings scored (coverage)"), _num(f"{rollup.get('n_scored')}/{rollup.get('n_holdings')}")]},
        ],
        "note": "Value-weighted physical-climate-risk exposure across holdings — the metric TCFD's asset-owner/manager "
                "guidance recommends. Climate VaR = position value − climate-discounted value from the shared engine."})

    # 2 — Physical risk by hazard
    haz_rows = []
    for hz in sorted(by_hazard, key=lambda h: -((by_hazard[h] or {}).get("exposed_value_eur") or 0)):
        h = by_hazard[hz] or {}
        haz_rows.append({"type": "row", "cells": [_txt(_pretty_hazard(hz)), _mnum(_eur(h.get("exposed_value_eur")), "computed"),
                                                   _num(str(h.get("n_exposed", 0))), _num(f"{h.get('max_score', 0)}")]})
    if haz_rows:
        sections.append({"title": "Physical-risk exposure by hazard (High+)",
                         "columns": ["Hazard", "Value exposed", "Holdings exposed", "Max score"],
                         "col_sources": ["", "computed", "computed", "computed"], "rows": haz_rows, "note": None})

    # 3 — EU-Taxonomy status
    if tax:
        tax_rows = [{"type": "row", "cells": [_txt(str(k).replace("_", " ").title()), _mnum(_eur(v.get("value_eur")), "computed"), _num(str(v.get("count", 0)))]}
                    for k, v in sorted(tax.items(), key=lambda kv: -(kv[1].get("value_eur") or 0))]
        sections.append({"title": "EU-Taxonomy status (holdings)", "columns": ["Status", "Value", "Holdings"],
                         "col_sources": ["", "computed", "computed"], "rows": tax_rows,
                         "note": "Taxonomy eligibility classified where the holding's NACE is known; alignment needs the "
                                 "issuer's own Article-8 figures (customer-supplied), never inferred."})

    # 4 — Climate-risk concentration (the diversification diagnostic)
    if conc.get("available"):
        cs = conc.get("common_shock") or {}
        sections.append({
            "title": "Climate-risk concentration — diversification & common-shock",
            "columns": ["Measure", "Value"], "rows": [
                {"type": "row", "cells": [_txt("Effective independent regions (1/HHI)"), _num(str(conc.get("effective_regions") or "—"))]},
                {"type": "row", "cells": [_txt("Effective independent hazards (1/HHI)"), _num(str(conc.get("effective_hazards") or "—"))]},
                {"type": "row", "cells": [_txt(f"Top region — {(conc.get('top_region') or {}).get('region', '—')}"), _num(f"{(conc.get('top_region') or {}).get('pct_of_book', 0)}% of book")]},
                {"type": "row", "cells": [_txt(f"Largest common-shock — {_pretty_hazard(cs.get('hazard', ''))} in {cs.get('region', '—')}"), _mnum(_eur(cs.get("climate_var_eur")), "computed")]},
                {"type": "row", "cells": [_txt("Common-shock share of total climate VaR"), _num(f"{conc.get('common_shock_var_pct_of_total')}%")]},
            ],
            "note": "Concentration decomposes the portfolio's climate VaR by region and hazard; HHI = Herfindahl index, "
                    "effective count = 1/HHI. A common-shock cluster is one hazard in one region — positions a single "
                    "event hits together. Structural definition, not a fitted correlation matrix."})
        clusters = conc.get("clusters") or []
        if clusters:
            cl_rows = [{"type": "row", "cells": [_txt(f"{_pretty_hazard(c.get('hazard', ''))} · {c.get('region', '—')}"),
                                                 _mnum(_eur(c.get("climate_var_eur")), "computed"), _num(str(c.get("n", 0))),
                                                 _num(f"{c.get('pct_of_book')}%")]} for c in clusters[:8]]
            sections.append({"title": "Common-shock clusters — the concentration to diversify",
                             "columns": ["Hazard × region", "Climate VaR", "Holdings", "% of book"],
                             "col_sources": ["", "computed", "computed", "computed"], "rows": cl_rows, "note": None})

    return sections


def build_annex(framework: str, dps: dict, groups: list[dict], payload: dict | None = None) -> dict | None:
    """Assemble the official-form layout for a framework from its merged datapoints. `dps` is key -> merged
    datapoint; `groups` is the datapoint-list grouping (used for the generic/ESRS fallback); `payload` is the
    raw frozen snapshot, used where an official template is a computed GRID (Pillar 3 Template 5) not flat cells.
    Money is written in the currency the snapshot presents in (multi-currency phase 3)."""
    token = money_format.current.set(money_format.presentation_of(payload))
    try:
        return _build_annex(framework, dps, groups, payload)
    finally:
        money_format.current.reset(token)


def _build_annex(framework: str, dps: dict, groups: list[dict], payload: dict | None) -> dict | None:
    if framework == "sfdr_pai":
        sections = _sfdr_annex(dps, payload or {})
    elif framework == "bank_p3esg":
        sections = _p3esg_annex(dps, payload or {})
    elif framework == "reit_tcfd":
        sections = _reit_annex(dps, payload or {})
    elif framework == "insurer_climate":
        sections = _insurer_annex(dps, payload or {})
    elif framework == "assetmgmt_tcfd":
        sections = _assetmgmt_annex(dps, payload or {})
    elif framework == "bank_tcfd":
        sections = _located_annex(dps, payload or {})
    else:
        sections = _generic_annex(dps, groups)
    if not sections:
        return None
    ref = reference(framework) or {}
    frozen = _frozen_spec(framework, payload or {})
    if frozen:                                        # the act the filing was prepared under, from its frozen spec
        from services.governance.reg_reference import REFERENCE, with_spec
        ref = with_spec(REFERENCE[framework], frozen)
    return {
        "official_name": ref.get("official_name", framework),
        "authority": ref.get("authority"),
        "official_form": ref.get("official_form"),
        "legal_basis": ref.get("legal_basis"),
        "form_url": ref.get("form_url"),
        "sections": sections,
    }

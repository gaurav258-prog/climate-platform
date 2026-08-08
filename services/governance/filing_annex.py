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

from services.governance.reg_reference import reference


def _txt(s):
    return {"text": s}


def _num(s):
    """A right-aligned numeric text cell (for computed grid figures like Template 5)."""
    return {"text": s, "num": True}


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


# ── SFDR — RTS 2022/1288 Annex I, Table 1 (the 14 mandatory Principal Adverse Impact indicators) ───────────
# Official indicator wording, grouped by the Annex's own themed headers. Value/coverage come from the
# assembled indicators (indicator.<n>); a missing indicator still shows its mandatory row as "—".
_SFDR_TABLE1 = [
    ("Climate and other environment-related indicators", [
        ("Greenhouse gas emissions", [
            (1, "GHG emissions (Scope 1, 2, 3 and total)"),
            (2, "Carbon footprint"),
            (3, "GHG intensity of investee companies"),
            (4, "Exposure to companies active in the fossil fuel sector"),
            (5, "Share of non-renewable energy consumption and production"),
            (6, "Energy consumption intensity per high-impact climate sector"),
        ]),
        ("Biodiversity", [
            (7, "Activities negatively affecting biodiversity-sensitive areas"),
        ]),
        ("Water", [
            (8, "Emissions to water"),
        ]),
        ("Waste", [
            (9, "Hazardous waste and radioactive waste ratio"),
        ]),
    ]),
    ("Social and employee, respect for human rights, anti-corruption and anti-bribery matters", [
        (None, [
            (10, "Violations of UN Global Compact principles and OECD Guidelines"),
            (11, "Lack of processes to monitor compliance with UN Global Compact / OECD Guidelines"),
            (12, "Unadjusted gender pay gap"),
            (13, "Board gender diversity"),
            (14, "Exposure to controversial weapons"),
        ]),
    ]),
]


def _sfdr_annex(dps: dict) -> list[dict]:
    cols = ["#", "Adverse sustainability indicator", "Metric — impact (reporting period)", "Coverage"]
    rows: list[dict] = []
    for _theme, subgroups in _SFDR_TABLE1:
        for sub, inds in subgroups:
            if sub:
                rows.append({"type": "subheader", "label": sub})
            for n, label in inds:
                dp = dps.get(f"indicator.{n}")
                cov = None
                if dp and isinstance(dp.get("note"), str):
                    cov = dp["note"]
                rows.append({"type": "row", "cells": [
                    _txt(str(n)), _txt(label), _cell(dps, f"indicator.{n}"), _txt(cov or "—"),
                ]})
    sections = [{
        "title": "Table 1 · Mandatory indicators", "columns": cols, "rows": rows,
        "note": "Statement on principal adverse impacts of investment decisions on sustainability factors. "
                "The 'Explanation' and 'Actions taken' narrative columns of the Annex are completed at submission.",
    }]
    # additional (voluntary) indicators, if the snapshot carries them
    def _extra(keys_prefix, title, src_list):
        extra_rows = []
        for k in sorted(dps):
            if k.startswith(keys_prefix):
                d = dps[k]
                extra_rows.append({"type": "row", "cells": [_txt(""), _txt(d.get("label", "")), {"dp": d}, _txt(d.get("note") or "—")]})
        if extra_rows:
            sections.append({"title": title, "columns": cols, "rows": extra_rows, "note": None})
    # (real-estate / sovereign indicators are surfaced in the datapoint list; Table 1 is the headline)
    return sections


# ── EU-Taxonomy Article 8 (GAR summary) + PCAF financed emissions + TCFD physical-risk metrics ─────────────
def _located_annex(dps: dict) -> list[dict]:
    total = (dps.get("book.total_value_eur") or {}).get("value")
    sections: list[dict] = []

    # EU-Taxonomy Art. 8 — Green Asset Ratio summary template
    if any(k in dps for k in ("taxonomy.eligible_value_eur", "taxonomy.not_eligible_value_eur")):
        gar_rows = []
        for key, label in [("taxonomy.eligible_value_eur", "Taxonomy-eligible exposures"),
                           ("taxonomy.not_eligible_value_eur", "Not eligible"),
                           ("taxonomy.not_assessed_value_eur", "Not assessed / no data")]:
            d = dps.get(key)
            gar_rows.append({"type": "row", "cells": [
                _txt(label), _cell(dps, key), _txt(_pct_text((d or {}).get("value"), total)),
            ]})
        gar_rows.append({"type": "row", "cells": [_txt("Total covered assets"), _cell(dps, "book.total_value_eur"), _txt("100%")]})
        sections.append({
            "title": "EU Taxonomy · Article 8 — Green Asset Ratio (summary)",
            "columns": ["KPI", "Amount", "% of covered assets"], "rows": gar_rows,
            "note": "Eligibility KPI per Disclosures Delegated Act (EU) 2021/2178. Alignment (DNSH + minimum "
                    "safeguards) is disclosed in the full GAR templates.",
        })

    # PCAF financed emissions
    if any(k in dps for k in ("emissions.scope1", "emissions.total")):
        em_rows = [{"type": "row", "cells": [_txt(label), _cell(dps, key)]} for key, label in [
            ("emissions.scope1", "Scope 1"), ("emissions.scope2", "Scope 2"),
            ("emissions.scope3", "Scope 3 (financed)"), ("emissions.total", "Total financed emissions")]]
        sections.append({"title": "Financed emissions · PCAF (tCO₂e)", "columns": ["Scope", "tCO₂e"],
                         "rows": em_rows, "note": None})

    # TCFD metrics & targets — physical-risk exposure by hazard
    haz_keys = sorted([k for k in dps if k.startswith("hazard.")], key=lambda k: -((dps[k].get("value")) or 0))
    haz_rows = []
    for key in ("book.value_at_risk_eur", "book.pct_value_at_risk", "book.total_discounted_value_eur"):
        if key in dps:
            haz_rows.append({"type": "row", "cells": [_txt(dps[key]["label"]), _cell(dps, key)]})
    if haz_keys:
        haz_rows.append({"type": "subheader", "label": "Value exposed at High+ by hazard"})
        for key in haz_keys:
            haz_rows.append({"type": "row", "cells": [_txt(_pretty_hazard(dps[key].get("label") or key.split(".", 1)[1])), _cell(dps, key)]})
    if haz_rows:
        sections.append({"title": "TCFD · Metrics & targets — physical climate risk",
                         "columns": ["Metric", "Value"], "rows": haz_rows, "note": None})
    return sections


def _eur(v):
    """Readable euro for a computed annex cell (values are already in EUR)."""
    if not isinstance(v, (int, float)):
        return "—"
    n = float(v)
    return f"€{n / 1e9:.2f}bn" if abs(n) >= 1e9 else f"€{n / 1e6:.1f}m" if abs(n) >= 1e6 else f"€{round(n / 1e3):,}k"


# ── EBA Pillar 3 ESG (ITS 2022/2453): Template 5 physical risk + GAR summary + Scope-3 for transition ─────
def _p3esg_annex(dps: dict, payload: dict) -> list[dict]:
    total = (dps.get("book.total_value_eur") or {}).get("value")
    sections: list[dict] = []
    assets = (payload or {}).get("assets") or []

    # Template 1 — banking-book transition risk by NACE sector (ITS 2022/2453, Annex XXXIX). Computed columns:
    # gross carrying amount + financed emissions (Scope 1–3) + of-which Scope 3; credit-quality/alignment/maturity
    # columns are customer-supplied (declared).
    if assets:
        from services.governance.pillar3_templates import template1_grid
        g1 = template1_grid(assets)
        t1_rows = []
        for r in g1["rows"] + [g1["total"]]:
            lbl = "TOTAL" if r["section"] == "TOTAL" else f"{r['section']} · {r['label']}"
            t1_rows.append({"type": "row", "cells": [
                _txt(lbl), _num(_eur(r["gross"])), _num(f"{r['fin_emissions']:,}"), _num(f"{r['scope3']:,}")]})
        sections.append({"title": "Template 1 — Banking book · climate-change transition risk (ITS 2022/2453, Annex XXXIX)",
                         "columns": ["Sector (NACE)", "Gross carrying amount", "Financed emissions Scope 1–3 (tCO₂e)", "of which Scope 3 (tCO₂e)"],
                         "rows": t1_rows,
                         "note": g1["basis"] + " Customer-supplied columns not shown: " + " · ".join(g1["customer_columns"]) + "."})

    # Template 5 — banking-book physical-risk exposure, built to the ACTUAL ITS 2022/2453 grid:
    # rows = NACE section; columns = gross carrying amount + of-which physical-risk-sensitive + chronic/acute/both.
    if assets:
        from services.governance.pillar3_templates import template5_grid
        grid = template5_grid(assets)
        cols = ["Sector (NACE)", "Gross carrying amount", "of which physical-risk-sensitive",
                "of which chronic", "of which acute", "of which chronic + acute"]
        t5_rows = []
        for r in grid["rows"]:
            t5_rows.append({"type": "row", "cells": [
                _txt(f"{r['section']} · {r['label']}"), _num(_eur(r["gross"])), _num(_eur(r["sensitive"])),
                _num(_eur(r["chronic"])), _num(_eur(r["acute"])), _num(_eur(r["both"]))]})
        t = grid["total"]
        t5_rows.append({"type": "row", "cells": [
            _txt("TOTAL"), _num(_eur(t["gross"])), _num(_eur(t["sensitive"])),
            _num(_eur(t["chronic"])), _num(_eur(t["acute"])), _num(_eur(t["both"]))]})
        sections.append({"title": "Template 5 — Banking book · climate-change physical risk (ITS 2022/2453, Annex XXXIX)",
                         "columns": cols, "rows": t5_rows,
                         "note": grid["basis"] + " Customer-supplied columns not shown: " + " · ".join(grid["customer_columns"]) + "."})
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
                             "columns": ["Exposure metric", "Amount (€)"], "rows": t5_rows,
                             "note": "Physical-risk exposure per ITS (EU) 2022/2453 (per-asset book unavailable for the sector grid)."})

    # GAR (Templates 7–8) — Taxonomy eligibility summary
    if any(k in dps for k in ("taxonomy.eligible_value_eur", "taxonomy.not_eligible_value_eur")):
        gar_rows = []
        for key, label in [("taxonomy.eligible_value_eur", "Taxonomy-eligible exposures"),
                           ("taxonomy.not_eligible_value_eur", "Not eligible"),
                           ("taxonomy.not_assessed_value_eur", "Not assessed / no data")]:
            gar_rows.append({"type": "row", "cells": [_txt(label), _cell(dps, key), _txt(_pct_text((dps.get(key) or {}).get("value"), total))]})
        sections.append({"title": "Green Asset Ratio (Templates 7–8) — eligibility",
                         "columns": ["KPI", "Amount", "% of covered assets"], "rows": gar_rows,
                         "note": "Eligibility numerator; alignment (DNSH + minimum safeguards) is disclosed in the full GAR/BTAR templates."})

    # Scope-3 financed emissions — only as a fallback when the per-asset book is unavailable (otherwise the
    # Template 1 grid above already carries financed emissions by NACE sector).
    if not assets and any(k in dps for k in ("emissions.scope3", "emissions.total")):
        em_rows = [{"type": "row", "cells": [_txt(label), _cell(dps, key)]} for key, label in [
            ("emissions.scope3", "Scope 3 (financed) emissions"), ("emissions.total", "Total financed emissions")]]
        sections.append({"title": "Transition risk — financed emissions (PCAF, tCO₂e)", "columns": ["Scope", "tCO₂e"],
                         "rows": em_rows, "note": "Counterparty Scope-3 basis for the transition-risk templates (Templates 1–4)."})
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


def build_annex(framework: str, dps: dict, groups: list[dict], payload: dict | None = None) -> dict | None:
    """Assemble the official-form layout for a framework from its merged datapoints. `dps` is key -> merged
    datapoint; `groups` is the datapoint-list grouping (used for the generic/ESRS fallback); `payload` is the
    raw frozen snapshot, used where an official template is a computed GRID (Pillar 3 Template 5) not flat cells."""
    if framework == "sfdr_pai":
        sections = _sfdr_annex(dps)
    elif framework == "bank_p3esg":
        sections = _p3esg_annex(dps, payload or {})
    elif framework in ("bank_tcfd", "reit_tcfd", "insurer_climate"):
        sections = _located_annex(dps)
    else:
        sections = _generic_annex(dps, groups)
    if not sections:
        return None
    ref = reference(framework) or {}
    return {
        "official_name": ref.get("official_name", framework),
        "authority": ref.get("authority"),
        "official_form": ref.get("official_form"),
        "legal_basis": ref.get("legal_basis"),
        "form_url": ref.get("form_url"),
        "sections": sections,
    }

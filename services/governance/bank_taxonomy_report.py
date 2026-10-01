"""The credit institution's EU Taxonomy Art. 8 report — report type `bank_tcfd` (the key keeps its historical name:
filings and snapshots reference it). It is governed by the spec family bank_taxonomy (Del. Reg. (EU) 2021/2178 Art. 4,
Annexes V–VI; data/reference/regspec_usage.json) and prints the Annex VI templates, nothing else (E95).

What a filing freezes: the loan book per exposure — the facts the templates read (services.governance.taxonomy_gar),
without the physical-risk engine's per-exposure scores — the book's count and total (the engine run's checks), and the
method record; plus the records every filing carries (_specs, _fx, _consolidation, provided values …). Its form is the
main row of the Summary of KPIs (Template 0); its annex every template of the governing version; its exports JSON and
the templates in a workbook. No XBRL: no official XBRL binding of the Annex VI templates is held (the Tellumen-made
namespace it used to carry was not a filing — E95, as E60 for the ESRS).

Filings frozen before 2026-10-01 carry the earlier report shape — physical-risk, PCAF financed-emission and credit-risk
analytics the templates do not print. They stay readable as frozen: those sections render after the templates, each
marked as from the earlier report shape.
"""
from __future__ import annotations

REPORT = "bank_tcfd"
# the physical-risk engine's per-exposure output: no Annex VI template reads it
ENGINE_FIELDS = ("hazards", "headline_score", "headline_bucket", "headline_hazard", "valuation")
# top-level keys only the earlier report shape froze
EARLIER_KEYS = ("by_hazard", "financed_emissions_tco2e", "financed_emissions_pcaf", "transition", "collateral_stranding",
                "expected_loss", "taxonomy")
EARLIER = "Earlier report shape"
EARLIER_NOTE = ("Frozen under the earlier shape of this report (before 2026-10-01), which also carried figures the EU "
                "Taxonomy Art. 8 templates do not print. Shown as frozen; not part of the Annex VI templates.")


def is_earlier_shape(payload: dict | None) -> bool:
    return any(k in (payload or {}) for k in EARLIER_KEYS)


def freeze(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None, period_end=None) -> dict:
    """The payload a new filing freezes (report_snapshots._BUILDERS)."""
    from api.routers.bank import loan_book
    assets, method = loan_book(session, org_id, scenario, horizon, entity_ids=entity_ids, value_weights=value_weights,
                               translation=translation, period_end=period_end)
    book = [{k: v for k, v in a.items() if k not in ENGINE_FIELDS} for a in assets]
    return {"assets": book,
            "rollup": {"n_assets": len(book), "total_value_eur": round(sum(a.get("value_eur") or 0 for a in book))},
            "method": method.record()}


# ── form ──────────────────────────────────────────────────────────────────────
_KPI = (("turnover", "GAR stock — KPI, turnover-based"), ("capex", "GAR stock — KPI, CapEx-based"),
        ("coverage", "GAR stock — coverage over total assets"))


def form(payload: dict) -> list[dict]:
    """The filing's datapoints: the main row of Template 0 (keys 'taxonomy.gar_stock.<turnover|capex|coverage>'), and the
    frozen book's size. A frozen earlier-shape filing shows what it froze, each group marked as such."""
    from services.governance.filing_form import _dp, _located_book_form
    from services.governance.taxonomy_forms import kpi_summary
    groups = []
    sm = kpi_summary(payload)
    if sm is not None:
        dps = [_dp(f"taxonomy.gar_stock.{k}", label, sm[k], "pct",
                   note=(sm["cells"].get(k) or "") + ("" if sm[k] is not None else " — blank: no exposure states the "
                                                       "facts it needs, or a phase-in leaves it undisclosed"))
               for k, label in _KPI]
        groups.append({"group": "Summary of KPIs (Template 0) — main KPI", "datapoints": dps})
    r = payload.get("rollup") or {}
    groups.append({"group": "Frozen loan book", "datapoints": [
        _dp("book.n_assets", "Exposures in the frozen book", r.get("n_assets", len(payload.get("assets") or [])), "num",
            source="book")]})
    if is_earlier_shape(payload):
        for g in _located_book_form(REPORT, payload):
            groups.append({"group": f"{EARLIER} · {g['group']}", "datapoints": g["datapoints"], "note": EARLIER_NOTE})
    return groups


# ── annex ─────────────────────────────────────────────────────────────────────
def annex(dps: dict, payload: dict) -> list[dict]:
    """Every Annex VI template of the version the filing was frozen under (services.governance.taxonomy_forms); for an
    earlier-shape filing, then the sections it froze, marked."""
    from services.governance import taxonomy_forms
    sections = taxonomy_forms.sections(payload or {}, REPORT)
    if is_earlier_shape(payload):
        sections += [{**s, "title": f"{EARLIER} · {s['title']}",
                      "note": " ".join(n for n in (EARLIER_NOTE, s.get("note")) if n)} for s in _earlier_sections(dps, payload)]
    return sections


def _earlier_sections(dps: dict, payload: dict) -> list[dict]:
    from services.governance.filing_annex import (
        _bank_analytics_sections,
        _cell,
        _gar_flat_summary_section,
        _tcfd_physical_sections,
        _txt,
    )
    out = []
    if not (payload or {}).get("assets"):
        flat = _gar_flat_summary_section(dps, (dps.get("book.total_value_eur") or {}).get("value"))
        if flat:
            out.append(flat)
    if any(k in dps for k in ("emissions.scope1", "emissions.total")):
        out.append({"title": "Financed emissions · PCAF (tCO₂e)", "columns": ["Scope", "tCO₂e"], "note": None, "rows": [
            {"type": "row", "cells": [_txt(label), _cell(dps, key)]} for key, label in (
                ("emissions.scope1", "Scope 1"), ("emissions.scope2", "Scope 2"),
                ("emissions.scope3", "Scope 3 (financed)"), ("emissions.total", "Total financed emissions"))]})
    return out + _tcfd_physical_sections(dps) + _bank_analytics_sections(payload or {})


# ── export ────────────────────────────────────────────────────────────────────
XLSX_HEADERS = ["asset_name", "asset_type", "counterparty_sector", "nace_code", "country", "instrument_type", "loan_purpose",
                "csrd_subject", "outstanding_loan_balance_eur", "value_eur", "taxonomy_status", "taxonomy_objective",
                "taxonomy_contribution"]


def xlsx_rows(payload: dict) -> list[list]:
    """The frozen book as the templates read it, one exposure per row (the templates follow as blocks)."""
    return [[a.get(h) for h in XLSX_HEADERS] for a in payload.get("assets") or []]


# ── confirm-data step ─────────────────────────────────────────────────────────
def preflight(session, org_id, basis: dict, entity_ids=None, value_weights=None, translation=None) -> dict:
    """Over exactly the book the filing will freeze: how many exposures state a gross carrying amount (an exposure that
    states none sits in no template row). No physical-risk figure: the templates print none."""
    from services.governance.pillar3_grids import gross_of
    p = freeze(session, org_id, basis["scenario"], basis["horizon"], entity_ids, value_weights, translation)
    assets = p["assets"]
    done = sum(1 for a in assets if gross_of(a))
    gaps = [f"{len(assets) - done} of {len(assets)} exposures state no gross carrying amount (outstanding balance) — "
            "they sit in no template row"] if done < len(assets) else []
    return {"coverage": {"label": "exposures with a gross carrying amount", "done": done, "total": len(assets),
                         "pct": round(100 * done / len(assets), 1) if assets else 0},
            "total_value_eur": p["rollup"]["total_value_eur"], "value_at_risk_eur": None, "noun": "exposures", "gaps": gaps}


# ── live KPI (the KRI dashboard) ──────────────────────────────────────────────
def live_kpis(session, org_id) -> dict | None:
    """Template 0's main KPIs over today's book, on the version governing the organisation's reporting period."""
    from services.calc_settings import get_calc_settings
    from services.governance.filings import reporting_period_end
    from services.governance.report_snapshots import _spec_record
    from services.governance.reporting_settings import get_settings
    from services.governance.taxonomy_forms import FAMILY, kpi_summary
    s = get_settings(session, org_id)
    pe = reporting_period_end(session, org_id)
    payload = freeze(session, org_id, s["scenario"], s["horizon"], period_end=pe)
    rec = _spec_record(session, FAMILY, pe, get_calc_settings(session, org_id))
    payload["_specs"] = {FAMILY: rec} if rec and rec.get("version") else {}
    payload["_regulation"] = {"period_end": pe.isoformat()}
    return kpi_summary(payload)


# ── prior filings (services.governance.prior_filings) ─────────────────────────
def prior_targets(period_end=None) -> dict[str, str]:
    """The cells a line of a filed Taxonomy report can be mapped to: the Summary of KPIs (Template 0) of the version
    governing its period — key 'T0.<row>.<column>' → the row and column as printed. Only a line whose label is one of
    them is mapped on reading; any other is left for the preparer to map or drop (never guessed)."""
    from datetime import date

    import services.regspec as R
    from services.governance.taxonomy_forms import FAMILY
    spec = R.governing(FAMILY, period_end=period_end or date.today())
    if spec is None:
        return {}
    t0 = R.template(spec, "T0")
    return {f"T0.{r['id']}.{c['id']}": f"{r['label']} — {c['label']}" for r in t0["rows"] for c in t0["columns"]}

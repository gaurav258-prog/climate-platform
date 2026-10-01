"""The credit-institution EU Taxonomy Art. 8 templates on a filing's form — rendered row for row, column for column,
from the specification the filing was frozen under (bank_taxonomy, Annex VI of Delegated Regulation (EU) 2021/2178),
with the values of services.governance.taxonomy_gar over the filing's frozen book.

A template disclosed for both KPI bases appears twice (turnover-based, CapEx-based). A cell is a computed value; a blank
('—': no exposure states the fact it needs); 'not yet disclosed' (a phase-in the specification quotes); or a cell the
institution enters itself (the platform holds no facts for it — the reason is on the form), offered for entry and shown
from the values frozen into this filing.
"""
from __future__ import annotations

from datetime import date

import services.regspec as R
from services.governance import taxonomy_gar as G
from services.governance import taxonomy_vocabulary as V

FAMILY = "bank_taxonomy"
# filings frozen before template specifications existed followed the 2023/2486 layout (six objectives, the KPI summary)
BEFORE_SPECS = "da_2021_2178_as_amended_2023_2486"
_BASIS_TITLE = {"turnover": "turnover-based", "capex": "CapEx-based"}


def _period_end(payload: dict) -> date:
    from services.governance.filing_annex import _period_end as pe
    return pe(payload)


def grids(payload: dict) -> tuple[dict, dict] | None:
    """(the specification the filing was frozen under, taxonomy_gar.build over its frozen book), or None without a book."""
    assets = payload.get("assets") or []
    if not assets:
        return None
    rec = (payload.get("_specs") or {}).get(FAMILY) or {}
    spec = R.load(FAMILY, rec.get("version") or BEFORE_SPECS)
    pe = _period_end(payload)
    from services.governance.filing_annex import _disclosed_on
    prev = payload.get("_previous_period") or {}
    return spec, G.build(spec, assets, pe, previous_assets=prev.get("assets"),
                         previous_period_end=date.fromisoformat(prev["period_end"]) if prev.get("period_end") else None,
                         disclosure_date=_disclosed_on(payload, FAMILY, pe))


def kpi_summary(payload: dict) -> dict | None:
    """The main row of the Summary of KPIs (Template 0) as the filing prints it — the GAR stock, turnover-based and
    CapEx-based, and its coverage over total assets: {'turnover', 'capex', 'coverage': value or None, 'cells': {name:
    'T0 r1 c3'}}. A cell a phase-in leaves undisclosed, or no exposure states the fact for, is None."""
    built = grids(payload)
    if built is None:
        return None
    spec, out = built
    res = V.resolve(spec, "T0")
    row = next((rid for rid, r in res["rows"].items() if r.get("kpi") == "gar_stock"), None)
    vals = ((out.get("T0") or {}).get("all") or {}).get(row) or {}
    got: dict = {"turnover": None, "capex": None, "coverage": None, "cells": {}}
    for cid, c in res["columns"].items():
        name = ("coverage" if c.get("coverage") == "stock" else
                c.get("basis") if c.get("unit") == "pct" and not c.get("measure") and not c.get("share_of_total") else None)
        if name in got and name != "cells":
            v = vals.get(cid)
            got[name] = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
            got["cells"][name] = f"Template 0, row {row}, column {cid}"
    got["version"] = spec["version"]
    return got


def sections(payload: dict, report_type: str = "bank_tcfd") -> list[dict]:
    """Every template of the governing version, in the order the Annex prints them."""
    from services.governance.filing_annex import _supplied
    built = grids(payload)
    if built is None:
        return []
    spec, out = built
    rec = (payload.get("_specs") or {}).get(FAMILY) or {}
    pe = _period_end(payload)
    prev = payload.get("_previous_period") or {}
    supplied = _supplied(payload)
    common = _common_notes(spec, out["counts"], rec, prev, pe)
    result = []
    for t in spec["templates"]:
        tid = t["id"]
        if tid in out["inputs"]:
            result.append(_section(spec, t, None, {}, supplied, report_type,
                                   [f"Entered by the institution: {out['inputs'][tid]}."] + common))
            continue
        for basis, grid in out[tid].items():
            result.append(_section(spec, t, None if basis == "all" else basis, grid, supplied, report_type, common))
    return result


def _common_notes(spec: dict, counts: dict, rec: dict, prev: dict, pe: date) -> list[str]:
    notes = []
    if not rec.get("version"):
        notes.append(f"Frozen before template specifications existed: rendered to {spec['act'].get('short') or spec['version']}, "
                     "the layout the platform followed then.")
    if counts.get("phase_in"):
        ph = counts["phase_in"]
        notes.append(f"Not yet disclosed where marked — {ph['ref']}: “{ph['quote']}” {ph.get('note') or ''}".strip())
        if counts.get("phased"):
            notes.append(f"{counts['phased']:,} specific-purpose exposures ({counts['phased_gross']:,.0f} gross) finance an "
                         "activity disclosed for eligibility only in this period: counted as eligible, left out of every "
                         "aligned figure.")
        notes += [f"{u['cited']}: {u['finding']} {u['reading']}" for u in ph.get("unmatched") or []]
    if counts["general_purpose_without_kpi"]:
        notes.append(f"{counts['general_purpose_without_kpi']:,} general-purpose exposures to undertakings in the numerator "
                     "have no counterparty KPIs on file: their eligible and aligned amounts are blank, not zero "
                     "(Annex V values them by the counterparty's own turnover / CapEx KPIs).")
    if counts["subject_unstated"]:
        notes.append(f"{counts['subject_unstated']:,} exposures to undertakings do not state whether the counterparty is "
                     f"subject to the {counts['regime'].upper()} disclosure obligations, which decides where they belong.")
    if counts["unclassified"]:
        notes.append(f"{counts['unclassified']:,} exposures ({counts['unclassified_gross']:,.0f} gross) could not be placed in "
                     "any row of this template and are outside every total.")
    rules = V.vocabulary().get("basis_rules", {})
    if rules.get("capex_general_lending_quote"):
        notes.append(f"CapEx-based figures of general lending use the counterparty's turnover KPI — "
                     f"{rules['capex_general_lending_ref']}: “{rules['capex_general_lending_quote']}”")
    notes.append(f"Previous disclosure reference date (T-1): from the filing for the period ending {prev['period_end']}."
                 if prev.get("period_end") else
                 f"Previous disclosure reference date (T-1): no filing for the period ending {pe.replace(year=pe.year - 1)} — blank.")
    return notes


def _fmt(v, fc: dict, kind: str) -> str:
    from services.governance.filing_annex import _eur
    if kind in ("gar_ratio_stock", "gar_ratio_flow") or fc.get("unit") == "pct":
        return f"{v:.2f}%"
    if fc.get("unit") == "meur":
        return f"{v:,.1f}"
    return _eur(v)


def _head(c: dict, fc: dict) -> str:
    """The column as printed (its printed letter); where the basis is only in a printed footnote ('KPI'), say it."""
    last = c["label"].split(" > ")[-1]
    basis = _BASIS_TITLE.get(fc.get("basis") or "")
    if basis and "based" not in c["label"].lower():
        last += f" ({basis})"
    return f"{c.get('printed_id', c['id'])} · {last}"


def _section(spec: dict, t: dict, basis: str | None, grid: dict, supplied: dict, report_type: str, notes: list[str]) -> dict:
    from services.governance.filing_annex import _col_groups, _mnum, _readings, _txt
    tid = t["id"]
    res = V.resolve(spec, tid)
    key_tid = f"{tid}@{basis}" if basis else tid
    cols = t["columns"]
    rows = []
    for r in t["rows"]:
        fr = res["rows"][r["id"]]
        if fr.get("elided"):
            rows.append({"type": "subheader", "label": "… (further rows as needed)"})
            continue
        vals = grid.get(r["id"]) or {}
        label = r["label"].split(" > ")[-1] if not r.get("unlabelled") else ""
        cells = [_txt(f"{r['id']} · {label}" if label else r["id"])]
        for c in cols:
            fc = res["columns"][c["id"]]
            v = vals.get(c["id"])
            key = f"{key_tid}.{r['id']}.{c['id']}"
            if fr.get("input") or fc.get("input") or (isinstance(v, dict) and "_input" in v) or "_input" in vals:
                got = supplied.get(key)
                shown = "—" if got is None else (_fmt(got, fc, res["kind"]) if isinstance(got, (int, float)) else str(got))
                cells.append({**_mnum(shown, "manual"), "key": key, "frozen_value": got,
                              "supply": {"framework": report_type, "key": key}})
            elif fc.get("sector"):
                cells.append(_txt(vals.get("_sector") or "—"))
            elif v == G.NOT_REQUIRED:
                cells.append(_txt("not yet disclosed"))
            elif v is None:
                cells.append(_mnum("—", "computed"))
            else:
                cells.append(_mnum(_fmt(v, fc, res["kind"]), "computed"))
        rows.append({"type": "row", "cells": cells})
    title = f"{t['title']}{' — ' + _BASIS_TITLE[basis] if basis else ''} ({R.citation(spec, tid)})"
    body_notes = [n for n in (_col_groups(cols), t.get("note"), *_readings(spec, tid)) if n] + notes
    return {"title": title, "key": f"taxonomy_{key_tid.lower().replace('@', '_')}",
            "columns": ["Row"] + [_head(c, res["columns"][c["id"]]) for c in cols],
            "col_sources": [""] + ["manual" if res["columns"][c["id"]].get("input") else "computed" for c in cols],
            "rows": rows, "note": " ".join(body_notes),
            "spec": {"framework": FAMILY, "version": spec["version"], "template": tid, "sha256": spec["_sha256"],
                     "basis": basis}}

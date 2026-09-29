"""The non-financial EU Taxonomy Art. 8 templates on a building owner's filing — Annex II of Delegated Regulation (EU)
2021/2178 in the version the filing was frozen under (nonfin_taxonomy), row for row, with the values of
services.governance.taxonomy_nonfin over the filing's frozen property book.

An activity template's illustrative rows ('Activity 1', …) are replaced by the undertaking's own activities. A
template disclosed per KPI appears once per KPI. The CapEx and OpEx figures come from the undertaking's ledger: they
are cells it enters (keyed '<template>[@kpi].<row>.<column>'), shown from the values frozen into this filing.
"""
from __future__ import annotations

from datetime import date

import services.regspec as R
from services.governance import taxonomy_nonfin as N
from services.governance import taxonomy_vocabulary as V

FAMILY = "nonfin_taxonomy"
BEFORE_SPECS = "da_2021_2178_as_amended_2023_2486"      # pre-spec filings followed the 2023/2486-era Annex II layout
_KPI = {"turnover": "turnover", "capex": "CapEx", "opex": "OpEx"}


def sections(payload: dict, report_type: str = "reit_taxonomy") -> list[dict]:
    from services.governance.filing_annex import _period_end, _supplied
    props = payload.get("properties") or []
    if not props:
        return []
    rec = (payload.get("_specs") or {}).get(FAMILY) or {}
    spec = R.load(FAMILY, rec.get("version") or BEFORE_SPECS)
    prev = payload.get("_previous_period") or {}
    out = N.build(spec, props, _period_end(payload), previous_properties=prev.get("assets"))
    supplied = _supplied(payload)
    notes = _notes(spec, out["counts"], rec, prev, _period_end(payload))
    result = []
    for t in spec["templates"]:
        tid = t["id"]
        if tid in out["inputs"]:
            result.append(_section(spec, t, None, {"_input": out["inputs"][tid]}, supplied, report_type,
                                   [f"Entered by the undertaking: {out['inputs'][tid]}."] + notes, multi=False))
            continue
        kpis = V.kpis_of(spec, tid)
        for kpi, grid in out[tid].items():
            result.append(_section(spec, t, None if kpi == "all" else kpi, grid, supplied, report_type, notes,
                                   multi=len(kpis) > 1 and kpi != "all"))
    return result


def _notes(spec: dict, c: dict, rec: dict, prev: dict, pe: date) -> list[str]:
    import json
    from pathlib import Path
    notes = []
    if not rec.get("version"):
        notes.append(f"Frozen before template specifications existed: rendered to {spec['act'].get('short') or spec['version']}.")
    if c["noi_proxy"]:
        notes.append(f"{c['noi_proxy']:,} buildings have no gross rental revenue on file: their net operating income "
                     f"({c['noi_proxy_turnover']:,.0f}) stands in for turnover, which understates it (Annex I §1.1.1: turnover "
                     "is revenue before operating expenses).")
    if c["alignment_unknown"]:
        why = "; ".join(f"{r} ({n})" for r, n in c["unknown_reasons"])
        notes.append(f"{c['alignment_unknown']:,} eligible buildings ({c['alignment_unknown_turnover']:,.0f} of turnover) have "
                     f"facts missing to decide alignment and sit in neither A.1 nor A.2 — {why}.")
    crit = json.loads((Path(__file__).resolve().parents[2] / "data/reference/taxonomy/criteria/ccm_7_7.json").read_text())
    notes += [f"Declared reading ({i['declared_by']}): {i['reading']}" for i in crit.get("interpretations") or []]
    notes.append("Declared reading (Tellumen): an aligned building is aligned under climate change mitigation (the "
                 "criteria evaluated, Annex I §7.7); eligibility counts under every objective the activity is eligible for.")
    notes.append(f"Previous year (N-1): from the filing for the period ending {prev['period_end']}." if prev.get("period_end")
                 else f"Previous year (N-1): no filing for the period ending {pe.replace(year=pe.year - 1)} — blank.")
    return notes


def _fmt(v, fc: dict) -> str:
    from services.governance.filing_annex import _eur
    if isinstance(v, str):
        return v
    return f"{v:.2f}%" if fc.get("measure") in ("proportion", "aligned_in_eligible") else _eur(v)


def _section(spec, t, kpi, grid, supplied, report_type, notes, *, multi) -> dict:
    from services.governance.filing_annex import _col_groups, _readings
    tid = t["id"]
    res = V.resolve(spec, tid)
    key_tid = f"{tid}@{kpi}" if multi and kpi else tid
    whole_input = "_input" in grid
    rows = []
    for r in t["rows"]:
        fr = res["rows"][r["id"]]
        label = r["label"].split(" > ")[-1]
        if not fr.get("activity_slot") and (fr.get("heading") or (fr.get("group") and not fr.get("total"))):
            rows.append({"type": "subheader", "label": label})
            continue
        if fr.get("activity_slot") and not whole_input:
            first = grid.get(r["id"]) or {}
            if first.get("_first_of_group"):               # the group's own activities, in place of the illustrative rows
                acts = [v for k, v in grid.items() if k.startswith(f"{r['id']}:")]
                rows += [_row(res, t, v.get("_activity", ""), v, key_tid, r["id"], supplied, report_type, False) for v in acts]
                if not acts:
                    rows.append({"type": "subheader", "label": "— no activity in this group —"})
            continue
        rows.append(_row(res, t, f"{r['id']} · {label}", grid.get(r["id"]) or {}, key_tid, r["id"], supplied, report_type,
                         whole_input or "_input" in (grid.get(r["id"]) or {})))
    title = f"{t['title']}{' — ' + _KPI[kpi] if multi and kpi else ''} ({R.citation(spec, tid)})"
    return {"title": title, "key": f"taxonomy_{key_tid.lower().replace('@', '_')}",
            "columns": ["Row"] + [f"{c.get('printed_id', c['id'])} · {c['label'].split(' > ')[-1]}" for c in t["columns"]],
            "col_sources": [""] + ["manual" if whole_input or res["columns"][c["id"]].get("input") else "computed" for c in t["columns"]],
            "rows": rows, "note": " ".join([n for n in (_col_groups(t["columns"]), t.get("note"), *_readings(spec, tid)) if n] + notes),
            "spec": {"framework": FAMILY, "version": spec["version"], "template": tid, "sha256": spec["_sha256"], "kpi": kpi}}


def _row(res, t, label, vals, key_tid, rid, supplied, report_type, entered) -> dict:
    from services.governance.filing_annex import _mnum, _txt
    cells = [_txt(label)]
    for c in t["columns"]:
        fc = res["columns"][c["id"]]
        v = vals.get(c["id"])
        if fc.get("label") and isinstance(v, str):          # the row's name (activity, code, KPI) — never an input
            cells.append(_txt(v))
        elif entered or fc.get("input") or isinstance(v, dict):
            key = f"{key_tid}.{rid}.{c['id']}"
            got = supplied.get(key)
            cells.append({**_mnum("—" if got is None else _fmt(got, fc), "manual"), "key": key,
                          "supply": {"framework": report_type, "key": key}})
        elif v is None:
            cells.append(_mnum("—", "computed"))
        else:
            cells.append(_mnum(_fmt(v, fc), "computed"))
    return {"type": "row", "cells": cells}


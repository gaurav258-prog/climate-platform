"""S.27.01.01 on a filing's official form — the natural-catastrophe part, block by block as Annex I prints it, from the
specification the filing was frozen under (sii_qrt_natcat) and the standard-formula result frozen with it.

A cell is: a computed value; blank ('—': reportable, nothing to report); greyed (no Annex II instruction names it); or a
premium the undertaking enters (the other-region rows), offered for entry and shown as frozen.
"""
from __future__ import annotations

import services.regspec as R
from services.governance import s2701

_ORDER = ("Summary", "Windstorm", "Earthquake", "Flood", "Hail", "Subsidence")


def _fmt(v) -> str:
    from services.governance.filing_annex import _eur
    if isinstance(v, str):
        return v
    if isinstance(v, float) and abs(v) < 1:
        return f"{v * 100:.4f}%"                       # a charge factor
    return _eur(v)


def sections(payload: dict, report_type: str = "insurer_solvency") -> list[dict]:
    from services.governance.filing_annex import _mnum, _supplied, _txt
    from services.governance.insurer_solvency import natcat_block
    nb = natcat_block(payload or {})
    sf = nb.get("standard_formula_natcat") or {}
    rec = ((payload or {}).get("_specs") or {}).get(s2701.FAMILY) or {}
    if not rec.get("version") or "version" not in sf:
        return []                                      # frozen before the template was on the route
    spec = R.load(s2701.FAMILY, rec["version"])
    t = R.template(spec, s2701.TID)
    supplied = _supplied(payload)
    values = s2701.grid(spec, sf, supplied)
    ok = s2701.reportable(spec)
    src = s2701.binding(spec)[s2701.TID]
    blocks: dict[str, tuple[list, list]] = {}
    for r in t["rows"]:
        name = next((b for b in _ORDER[1:] if r["section"].rstrip().endswith(b)), "Summary")
        blocks.setdefault(name, ([], []))[0].append(r)
    for c in t["columns"]:
        name = next((b for b in _ORDER[1:] if c["section"].rstrip().endswith(b)), "Summary")
        blocks.setdefault(name, ([], []))[1].append(c)
    out = []
    for name in _ORDER:
        rows, cols = blocks.get(name, ([], []))
        body = []
        for r in rows:
            if not any((r["id"], c["id"]) in ok for c in cols):
                continue
            cells = [_txt(f"{r['id']} · {r['label']}")]
            for c in cols:
                key = f"{s2701.TID}.{r['id']}.{c['id']}"
                if (r["id"], c["id"]) not in ok:
                    cells.append({"text": "", "greyed": True})
                elif src["columns"][c["id"]].startswith("input") and src["rows"][r["id"]].startswith("input"):
                    got = supplied.get(key)
                    cells.append({**_mnum("—" if got is None else _fmt(got), "manual"), "key": key,
                                  "supply": {"framework": report_type, "key": key}})
                else:
                    v = (values.get(r["id"]) or {}).get(c["id"])
                    cells.append(_mnum("—" if v is None else _fmt(v), "computed"))
            body.append({"type": "row", "cells": cells})
        if not body:
            continue
        notes = []
        if name == "Summary":
            notes.append(f"Standard formula: {sf.get('version')} ({sf.get('version_source')}). Reinsurance: "
                         f"{'the attested treaty' if sf.get('treaty_basis') == 'attested' else 'none attested — no mitigation'}.")
            notes += [f"Incomplete: {x}" for x in sf.get("incomplete") or []]
            notes += [f"Declared reading — {x['subject']}: {x['reading']}" for x in sf.get("readings") or []]
            notes += [f"No row in {t['code']} for {x}: a region added by Delegated Regulation (EU) 2026/269 after this "
                      "template; its charge is inside the peril total." for x in s2701.unrepresented(sf)]
        elif name != "Subsidence":
            notes.append("Other-region rows: enter the premiums to be earned in the following 12 months by Annex III "
                         "region; DIV and the charge on the total row follow from them (Annex III(1), regions 5 to 18).")
        out.append({"title": f"{t['code']} — {name if name != 'Summary' else 'natural catastrophe risk'} "
                             f"({R.citation(spec, s2701.TID)})",
                    "key": f"s2701_{name.lower()}", "columns": ["Row"] + [f"{c['id']} · {c['label']}" for c in cols],
                    "col_sources": [""] + ["manual" if src["columns"][c["id"]].startswith("input") else "computed" for c in cols],
                    "rows": body, "note": " ".join(notes) or None,
                    "spec": {"framework": s2701.FAMILY, "version": spec["version"], "template": s2701.TID,
                             "sha256": spec["_sha256"]}})
    return out

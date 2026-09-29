"""Reading the credit-institution Taxonomy templates (Annex VI to Delegated Regulation (EU) 2021/2178, every version).

Each printed row and column is resolved into facts through one declared vocabulary
(data/reference/taxonomy/gar_vocabulary.json): a row's label chain ('parent > child') is read segment by segment and the
fragments combine into the filter over exposures it holds; a column's header chain combines into what it measures
(period, objective, measure, basis, unit). Nothing about a version is typed in code — a new version resolves or names
exactly which printed segment the vocabulary does not know (tests/unit/test_taxonomy_vocabulary.py).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).resolve().parents[2] / "data" / "reference" / "taxonomy"
_FILES = {"bank_taxonomy": "gar_vocabulary.json", "nonfin_taxonomy": "nonfin_vocabulary.json"}


def _norm(s: str) -> str:
    s = s.replace(" ", " ").replace("­", "")
    s = re.sub(r"[‐-―−]", "-", s)
    s = re.sub(r"[‘’´`]", "'", s)
    s = re.sub(r"[“”]", '"', s)
    return re.sub(r"\s+", " ", s).strip().lower()


@lru_cache(maxsize=4)
def vocabulary(family: str = "bank_taxonomy") -> dict:
    """The declared vocabulary of a template family: credit institutions (Annex VI) or non-financial undertakings
    (Annex II)."""
    v = json.loads((_DIR / _FILES[family]).read_text())
    return {"templates": v["templates"], "inputs": v["inputs"], "basis_rules": v.get("basis_rules", {}),
            "kpis": v.get("kpis", {}),
            "column_notes": {_norm(k): f for k, f in v.get("column_notes", {}).items()},
            "rows": {_norm(k): f for k, f in v["rows"].items()},
            "columns": {_norm(k): f for k, f in v["columns"].items()}}


class Unresolved(ValueError):
    pass


def _combine(chain: str, table: dict, where: str) -> dict:
    out: dict = {}
    for seg in chain.split(" > "):
        frag = table.get(_norm(seg))
        if frag is None:
            raise Unresolved(f"{where}: the vocabulary does not know the printed segment '{seg}'")
        out.update(frag)                                     # a child narrows its parent: the later segment wins
    return out


def kind(template_id: str, family: str = "bank_taxonomy", rows: dict | None = None) -> str:
    """What a template is: declared by id where the Annex keeps its numbering (Annex VI, Annex XII); otherwise read
    from its printed rows — activity rows, KPI rows or objective rows (Annex II, whose numbering changed by version)."""
    k = vocabulary(family)["templates"].get(template_id)
    if k is None and rows is not None:
        frags = list(rows.values())
        k = ("activities" if any(f.get("activity_slot") for f in frags) else
             "kpi_summary" if any(f.get("kpi") for f in frags) else
             "per_objective" if any(f.get("objective") for f in frags) else None)
    if k is None:
        raise Unresolved(f"{template_id}: no template kind declared or readable from its rows")
    return k


def kpis_of(spec: dict, template_id: str) -> list[str]:
    """The KPIs a non-financial template reports, from its printed title ('Proportion of turnover …' → ['turnover'];
    '… turnover, CapEx, OpEx …' → all three, disclosed once per KPI)."""
    import services.regspec as R
    title = _norm(R.template(spec, template_id)["title"])
    return [k for k, words in vocabulary("nonfin_taxonomy")["kpis"].items() if any(w in title for w in words)]


def resolve(spec: dict, template_id: str) -> dict:
    """{'kind', 'rows': {row_id: fragment}, 'columns': {col_id: fragment}} for one template of one version."""
    import services.regspec as R
    t = R.template(spec, template_id)
    family = spec.get("framework") or "bank_taxonomy"
    voc = vocabulary(family)
    k = voc["templates"].get(template_id)
    if k in voc["inputs"]:                                   # a template the loan tape holds no facts for: every cell entered
        return {"kind": k, "rows": {r["id"]: {"input": k} for r in t["rows"]},
                "columns": {c["id"]: {"input": k} for c in t["columns"]}}
    where = f"{spec['version']} {template_id}"
    rows: dict[str, dict] = {}
    parents: dict[str, str | None] = {}
    last_seg: list[tuple[str, str]] = []                      # (row id, its last printed segment), in printed order
    for r in t["rows"]:
        if r.get("unlabelled"):
            rows[r["id"]], parents[r["id"]] = {}, None
            continue
        segs = r["label"].split(" > ")
        own = _combine(segs[-1], voc["rows"], f"{where} row {r['id']}")
        parent = None
        if len(segs) > 1:
            # the printed tree: a row's parent is the nearest row above it whose own label is this row's parent segment
            parent = next((rid for rid, seg in reversed(last_seg) if _norm(seg) == _norm(segs[-2])), None)
        base = rows[parent] if parent else (_combine(" > ".join(segs[:-1]), voc["rows"], f"{where} row {r['id']}")
                                              if len(segs) > 1 else {})
        rows[r["id"]], parents[r["id"]] = {**base, **own}, parent
        last_seg.append((r["id"], segs[-1]))
    cols = {}
    for c in t["columns"]:
        f = {} if c.get("unlabelled") else _combine(c["label"], voc["columns"], f"{where} column {c['id']}")
        # a printed footnote the spec records in the column's note can say what the column measures ("based on the
        # Turnover KPI of the counterparty")
        note = _norm(c.get("note") or "")
        for phrase, frag in voc["column_notes"].items():
            if phrase in note:
                f = {**f, **frag}
        cols[c["id"]] = f
    # where the text is silent, the spec's declared readings (signed off with it) say how a column reads
    for i in spec.get("interpretations") or []:
        rv = i.get("resolves") or {}
        if rv.get("template") == template_id:
            for cid in rv.get("columns", []):
                cols[cid] = {**cols[cid], **rv["as"]}
    k = k or kind(template_id, family, rows)
    return {"kind": k, "rows": rows, "columns": cols, "parents": parents}


def input_reason(fragment: dict, family: str = "bank_taxonomy") -> str | None:
    key = fragment.get("input")
    return vocabulary(family)["inputs"].get(key) if key else None

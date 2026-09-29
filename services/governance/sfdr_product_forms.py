"""The SFDR product templates on a fund's filing — the annex of the governing sfdr_product version for the fund's SFDR
classification (Art. 8: Annex II / IV, Art. 9: Annex III / V), as a document: every printed item in reading order,
with the frozen values of services.governance.sfdr_product. Also the checks and the data tab of the same filing.
"""
from __future__ import annotations

import services.regspec as R
from services.governance import product_filings as P
from services.governance import sfdr_product as S

FAMILY = S.FAMILY
BEFORE_SPECS = "rts_2022_1288_as_amended_2023_363"


def _spec(payload: dict) -> dict:
    rec = (payload.get("_specs") or {}).get(FAMILY) or {}
    return R.load(FAMILY, rec.get("version") or BEFORE_SPECS)


def template_id(payload: dict, report_type: str) -> str:
    return P.annex(report_type, payload["fund"]["sfdr_classification"])


def items(payload: dict, report_type: str) -> tuple[dict, str, list[dict]]:
    spec = _spec(payload)
    tid = template_id(payload, report_type)
    return spec, tid, S.build(spec, tid, payload)


def missing(built: list[dict]) -> list[dict]:
    """What the document still lacks: an unanswered question, field, chart or table, and a set of tick-boxes none of
    which is answered (a single tick-box is part of its set, not a gap of its own)."""
    out = [i for i in built if i["status"] == "missing" and i["kind"] != "choice"]
    sets: dict = {}
    for i in built:
        if i["kind"] == "choice" and i["source"] != "fixed":
            sets.setdefault(i["parent"], []).append(i)
    for parent, group in sets.items():
        if all(c["status"] == "missing" for c in group) and not any(m["id"] == parent for m in out):
            out.append({**group[0], "id": parent, "label": f"tick-boxes under {parent}"})
    return out


def sections(payload: dict, report_type: str) -> list[dict]:
    if not payload.get("fund"):
        return []
    spec, tid, built = items(payload, report_type)
    t = R.template(spec, tid)
    rec = (payload.get("_specs") or {}).get(FAMILY) or {}
    notes = [] if rec.get("version") else [f"Frozen before template specifications existed: rendered to {spec['act']['short']}."]
    if S.document_of(tid) == "periodic":
        tax = S.taxonomy(payload)
        cov = tax["incl"]["turnover"]["kpi_coverage"]
        notes.append(f"Taxonomy alignment from each investee's own KPIs; investments stating them: {cov if cov is not None else '—'}% "
                     "of value (turnover basis). An investee without KPIs on file is not counted as aligned.")
        n = len(payload.get("position_dates") or [])
        notes.append(f"Top investments and sectors: averaged over the {n} position date{'s' if n != 1 else ''} held in the "
                     f"reference period {payload['period']['start']} – {payload['period']['end']}.")
    gaps = missing(built)
    if gaps:
        notes.append(f"{len(gaps)} items still need an answer — enter them on the fund's disclosure page and refresh this draft.")
    notes += [f"Declared reading ({i['declared_by']}): {i['reading']}" for i in spec.get("interpretations") or []
              if i.get("resolves", {}).get("template") == tid]
    return [{"title": f"{t['title']} ({R.citation(spec, tid)})", "key": f"sfdr_{tid.lower()}", "kind": "document",
             "columns": [], "rows": [], "items": built, "note": " ".join(notes),
             "spec": {"framework": FAMILY, "version": spec["version"], "template": tid, "sha256": spec["_sha256"]}}]


def checks(payload: dict, report_type: str) -> list[dict]:
    """Pre-submission findings for the document (see filing_validation): items still unanswered, and the data the
    computed items rest on."""
    from services.governance.filing_validation import _f
    if not payload.get("fund"):
        return [_f("fund_frozen", "completeness", "blocking", False, "the filing froze no fund")]
    spec, tid, built = items(payload, report_type)
    gaps = missing(built)
    out = [_f("items_answered", "completeness", "warning", not gaps,
              "every item of the template is answered" if not gaps else
              f"{len(gaps)} items have no answer yet: " + "; ".join(g["id"] for g in gaps[:8]) + ("…" if len(gaps) > 8 else ""))]
    if not payload.get("holdings"):
        out.append(_f("holdings", "completeness", "blocking", False, "no holdings on file for the reference period"))
    if S.document_of(tid) == "periodic":
        cov = S.taxonomy(payload)["incl"]["turnover"]["kpi_coverage"]
        out.append(_f("investee_kpis", "completeness", "warning", bool(cov),
                      f"investee Taxonomy KPIs on file for {cov if cov is not None else 0}% of value (turnover basis)"))
    return out

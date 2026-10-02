"""The regulatory lineage of a filing — from the law to the filed record, read from what the filing froze:

  act            each specification family the filing was prepared under: the act (CELEX), its legal basis as quoted,
                 whether that act's official text is held in the legal store and the quote is found in it word for word
  specification  the version frozen with the filing (its file's sha256), whether the file has changed since, and its
                 four-eyes sign-off for that exact file (as it stood, and the sign-off still holds or not)
  templates      every template of that version the filing prints, with how each row / column / item is filled
                 (computed by the platform, input the undertaking provides, not applicable) — the binding the change
                 route checks for coverage
  filing         the frozen record: its hash and whether it still verifies, the interpretations the organisation stated
                 (payload '_elections'), and the readings the specification itself declares

The data-side trace (a cell → its exposures → the golden source → the feeds) is services.governance.filing_lineage.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

import services.regspec as R
from services.reference import legal_texts as L


class LineageError(ValueError):
    pass


def _act(spec: dict) -> dict:
    celex = (spec.get("act") or {}).get("celex")
    lb = spec.get("legal_basis") or {}
    held = bool(celex) and celex in L.manifest()
    found = L.contains(lb.get("quote") or "") if lb.get("quote") else None
    return {"celex": celex, "title": (spec.get("act") or {}).get("short") or (spec.get("act") or {}).get("title"),
            "status": spec.get("status"), "article": lb.get("article"), "templates_in": lb.get("templates_in"),
            "instructions_in": lb.get("instructions_in"), "quote": lb.get("quote"), "text_held": held,
            "quote_found_in": found}


def _filled(spec: dict, binding: dict | None, tid: str) -> dict:
    """How one template is filled: counts per source kind, per axis (rows / columns, or items)."""
    t = R.template(spec, tid)
    b = (binding or {}).get(tid) or {}
    out = {"id": tid, "code": t.get("code"), "title": t["title"], "ref": t["ref"], "structure": t["structure"]}
    axes = ("items",) if t["structure"] == "document" else ("rows", "columns")
    for axis in axes:
        ids = [i["id"] for i in (R.items_to_fill(t) if axis == "items" else t.get(axis) or [])]
        mapped = b.get(axis) or {}
        kinds: dict[str, int] = {}
        for i in ids:
            k = str(mapped.get(i, "unbound")).split(":", 1)[0]
            kinds[k] = kinds.get(k, 0) + 1
        out[axis] = {"n": len(ids), "by_source": kinds}
    return out


def template_detail(spec: dict, binding: dict | None, tid: str) -> list[dict]:
    """Each row / column / item of one template with its printed wording and how it is filled."""
    t = R.template(spec, tid)
    b = (binding or {}).get(tid) or {}
    if t["structure"] == "document":
        return [{"axis": "items", "id": i["id"], "label": i.get("label") or i.get("note") or "", "kind": i["kind"],
                 "source": (b.get("items") or {}).get(i["id"], "unbound")} for i in R.items_to_fill(t)]
    return [{"axis": axis, "id": i["id"], "label": i.get("label") or "", "source": (b.get(axis) or {}).get(i["id"], "unbound")}
            for axis in ("rows", "columns") for i in t.get(axis) or []]


def build(session: Session, org_id: str, filing_id: str, template: str | None = None) -> dict:
    """The regulatory lineage of one filing (template: also the rows / columns / items of that template)."""
    from services.governance.filings import get_filing
    from services.regspec.bindings import binding_for
    from services.regspec.signoff import signed_on
    f = get_filing(session, org_id, filing_id, with_payload=True)
    if not f:
        raise LineageError("filing not found")
    snap = f.get("snapshot") or {}
    payload = snap.get("payload") or {}
    printed = {}                                            # family → templates the filing's form prints
    try:
        from services.governance.filings import form_view
        for sec in ((form_view(session, org_id, filing_id) or {}).get("annex") or {}).get("sections") or []:
            sp = sec.get("spec") or {}
            if sp.get("template"):
                printed.setdefault(sp.get("framework"), set()).add(sp["template"])
    except Exception:  # noqa: BLE001 — a form that cannot be rendered still has its frozen record
        printed = {}
    families = []
    specs = dict(payload.get("_specs") or {})
    before = False
    if not specs:                                   # frozen before specifications were stamped: the version the form uses
        from services.governance.filing_annex import _frozen_spec
        sp = _frozen_spec(f["framework"], payload)
        if sp is not None:
            specs, before = {sp["framework"]: {"version": sp["version"], "sha256": None}}, True
    for family, rec in specs.items():
        if not (rec or {}).get("version"):
            families.append({"family": family, "version": None, "note": (rec or {}).get("note")})
            continue
        spec = R.load(family, rec["version"])
        binding = binding_for(family, spec)
        frozen_sha = rec.get("sha256")
        prints = printed.get(family) or printed.get(None) or set()
        tids = [t["id"] for t in spec["templates"] if t["id"] in prints] or \
               [t["id"] for t in spec["templates"] if t["structure"] in ("full", "document")]
        entry = {
            "family": family, "version": rec["version"], "act": _act(spec), "frozen_before_specs": before,
            "spec": {"sha256_frozen": frozen_sha, "sha256_now": spec["_sha256"], "changed_since": None if frozen_sha is None else frozen_sha != spec["_sha256"],
                     "applies": spec.get("applies"), "signoff_at_freeze": {"approved": rec.get("approved"),
                                                                            "one_person": rec.get("one_person"),
                                                                            "needs": rec.get("needs")},
                     "signoff_of_frozen_file": signed_on(session, family, rec["version"], frozen_sha) if frozen_sha else None},
            "templates": [_filled(spec, binding, tid) for tid in tids],
            "interpretations": [{"subject": i.get("subject"), "reading": i.get("reading"), "basis": i.get("basis")}
                                for i in spec.get("interpretations") or []],
        }
        if template and template in tids:
            entry["template_detail"] = {"id": template, "rows": template_detail(spec, binding, template)}
        families.append(entry)
    return {"filing": {"filing_id": filing_id, "framework": f["framework"], "period_label": f.get("period_label"),
                       "status": f["status"], "payload_sha256": snap.get("payload_sha256"),
                       "hash_verified": snap.get("hash_verified")},
            "families": families, "elections": payload.get("_elections") or [],
            "regulation": payload.get("_regulation")}

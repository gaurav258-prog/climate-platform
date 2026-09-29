"""Regulatory specifications — each version of a regulation's templates as a versioned file (the change route, step 3).

A spec file (data/reference/regspec/<framework>/<version>.json) is the regulation, captured from the official text:
the act, its status (adopted / draft), when it applies, the legal basis and every template — for a template built
to the letter ("structure": "full") every row and column exactly as printed, with the instruction paragraphs quoted.
Nothing about our implementation lives in it; how each cell is filled is a separate binding (coverage() checks the
binding covers every row and column of the spec, and names anything stale).

  load / versions        read and validate the files; a file that fails validation is never used
  diff                   what changed between two versions — the only work a new version creates
  governing              which adopted version governs a date (per the spec's own application basis)
  coverage               spec rows / columns the implementation does not map, and mappings the spec no longer has
  sign-off               see signoff.py: two different people sign the file's exact sha256; any edit voids it
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "data" / "reference" / "regspec"
STATUSES = ("adopted", "draft")
BASES = ("disclosure_date", "period_end")


class SpecError(ValueError):
    pass


def _iso(v) -> str | None:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)).isoformat()
    except ValueError:
        return "invalid"


def validate(doc: dict) -> list[str]:
    """Every reason this document cannot be used as a spec (empty = valid)."""
    errs: list[str] = []
    for k in ("framework", "version", "act", "status", "legal_basis", "applies", "templates"):
        if not doc.get(k):
            errs.append(f"missing '{k}'")
    if errs:
        return errs
    if doc["status"] not in STATUSES:
        errs.append(f"status must be one of {STATUSES}")
    ap = doc["applies"]
    if _iso(ap.get("from")) == "invalid" or (ap.get("from") is None and doc["status"] != "draft"):
        errs.append("applies.from must be a date (a draft may leave it unset until adopted)")
    if _iso(ap.get("until")) == "invalid":
        errs.append("applies.until must be a date or null")
    if ap.get("basis") not in BASES:
        errs.append(f"applies.basis must be one of {BASES}")
    if doc["status"] == "adopted" and not (doc["act"] or {}).get("celex"):
        errs.append("an adopted act needs its CELEX number")
    ids = [t.get("id") for t in doc["templates"]]
    if len(ids) != len(set(ids)) or not all(ids):
        errs.append("template ids must be present and unique")
    for t in doc["templates"]:
        tid = t.get("id")
        if not t.get("title") or not t.get("ref"):
            errs.append(f"{tid}: title and ref are required")
        if t.get("structure") not in ("full", "listed"):
            errs.append(f"{tid}: structure must be 'full' or 'listed'")
        if t.get("structure") == "full":
            for axis in ("rows", "columns"):
                items = t.get(axis) or []
                if not items:
                    errs.append(f"{tid}: a full template needs its {axis}")
                keys = [i.get("id") for i in items]
                if len(keys) != len(set(keys)) or not all(keys) or not all(i.get("label") or i.get("unlabelled") for i in items):
                    errs.append(f"{tid}: {axis} need unique ids and labels")
    if doc["status"] == "adopted" and "UNVERIFIED" in json.dumps(doc):
        errs.append("an adopted spec may not contain UNVERIFIED fields")
    return errs


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path(framework: str, version: str) -> Path:
    if not framework.replace("_", "").isalnum() or not version.replace("_", "").isalnum():
        raise SpecError("framework and version are plain keys")
    return ROOT / framework / f"{version}.json"


@lru_cache(maxsize=64)
def _load_cached(path: str, mtime: float) -> dict:
    p = Path(path)
    doc = json.loads(p.read_text())
    errs = validate(doc)
    if errs:
        raise SpecError(f"{p.name}: " + "; ".join(errs))
    return {**doc, "_sha256": sha256_of(p)}


def load(framework: str, version: str) -> dict:
    """The validated spec, with its file's sha256 as `_sha256`. Raises SpecError if absent or invalid."""
    p = _path(framework, version)
    if not p.exists():
        raise SpecError(f"no spec {framework}/{version}")
    doc = _load_cached(str(p), p.stat().st_mtime)
    if doc["framework"] != framework or doc["version"] != version:
        raise SpecError(f"{p.name}: framework/version inside the file do not match its path")
    return doc


def versions(framework: str) -> list[dict]:
    """Every spec of a framework, oldest application date first."""
    d = ROOT / framework
    out = [load(framework, p.stem) for p in sorted(d.glob("*.json"))] if d.is_dir() else []
    return sorted(out, key=lambda s: s["applies"]["from"] or "9999-12-31")      # an undated draft sorts last


def frameworks() -> list[str]:
    return sorted(p.name for p in ROOT.iterdir() if p.is_dir()) if ROOT.is_dir() else []


def governing(framework: str, *, period_end: date | str, disclosure_date: date | str | None = None) -> dict | None:
    """The adopted spec that governs a filing. Each spec says which date decides (applies.basis): the reference date
    of the figures, or the date the disclosure is made (defaults to today). Drafts never govern."""
    pe = _iso(period_end)
    dd = _iso(disclosure_date) or date.today().isoformat()
    for s in reversed(versions(framework)):
        if s["status"] != "adopted":
            continue
        on = dd if s["applies"]["basis"] == "disclosure_date" else pe
        if s["applies"]["from"] <= on and (not s["applies"].get("until") or on <= s["applies"]["until"]):
            return s
    return None


def template(spec: dict, template_id: str) -> dict:
    t = next((t for t in spec["templates"] if t["id"] == template_id), None)
    if t is None:
        raise SpecError(f"{spec['version']} has no template {template_id}")
    return t


def citation(spec: dict, template_id: str | None = None) -> str:
    """How a template is cited on the form: its printed location in the governing act."""
    act = spec["act"].get("short") or spec["act"]["title"]
    if template_id is None:
        return act
    return f"{act}, {template(spec, template_id)['ref']}"


# ───────────────────────────── diff: the only work a new version creates ─────────────────────────────

def _unnumbered(label: str) -> str:
    """A label without its printed numbering ('11. Lack of …' / 'a) Scope 1' → 'Lack of …' / 'Scope 1'), case-folded."""
    import re
    return " > ".join(re.sub(r"^\s*(\d+\.|[a-z]\))\s*", "", seg).strip().casefold() for seg in label.split(" > "))


def _axis_diff(old: list[dict], new: list[dict]) -> dict:
    """By id, then by wording: an item whose exact wording reappears under another id has moved (renumbered), not
    been removed, added or relabelled — so a renumbering reads as what it is."""
    o, n = {i["id"]: i["label"] for i in old or []}, {i["id"]: i["label"] for i in new or []}
    o_by_label, n_by_label = {_unnumbered(v): k for k, v in o.items()}, {_unnumbered(v): k for k, v in n.items()}
    moved = [{"label": lbl, "from": o_by_label[lbl], "to": n_by_label[lbl]}
             for lbl in n_by_label if lbl in o_by_label and o_by_label[lbl] != n_by_label[lbl]]
    moved_from, moved_to = {m["from"] for m in moved}, {m["to"] for m in moved}
    return {"added": [k for k in n if k not in o and k not in moved_to],
            "removed": [k for k in o if k not in n and k not in moved_from],
            "relabelled": [{"id": k, "from": o[k], "to": n[k]} for k in n
                           if k in o and o[k] != n[k] and k not in moved_to and k not in moved_from],
            "moved": moved}


def diff(old: dict, new: dict) -> dict:
    """What changed from `old` to `new`: act and legal basis, templates added / removed, and per template kept: title,
    location, rows and columns added / removed / relabelled, and a changed axis. `unchanged` lists templates that carry
    over as they are."""
    ot, nt = {t["id"]: t for t in old["templates"]}, {t["id"]: t for t in new["templates"]}
    changed, unchanged = [], []
    for tid in (k for k in nt if k in ot):
        a, b = ot[tid], nt[tid]
        c: dict = {"id": tid}
        for f in ("title", "ref", "structure", "z_axis"):
            if a.get(f) != b.get(f):
                c[f] = {"from": a.get(f), "to": b.get(f)}
        for axis in ("rows", "columns"):
            d = _axis_diff(a.get(axis), b.get(axis))
            if any(d.values()):
                c[axis] = d
        (changed if len(c) > 1 else unchanged).append(c if len(c) > 1 else tid)
    legal = {f: {"from": old["legal_basis"].get(f), "to": new["legal_basis"].get(f)}
             for f in ("article", "templates_in", "instructions_in") if old["legal_basis"].get(f) != new["legal_basis"].get(f)}
    structural = bool([k for k in nt if k not in ot] or [k for k in ot if k not in nt]
                      or any(set(c) & {"structure", "z_axis"} for c in changed)
                      or any((c.get(a) or {}).get(k) for c in changed for a in ("rows", "columns") for k in ("added", "removed", "moved")))
    wording = any("title" in c or (c.get("rows") or {}).get("relabelled") or (c.get("columns") or {}).get("relabelled")
                  for c in changed)
    return {"from": old["version"], "to": new["version"],
            "act": {"from": old["act"].get("celex"), "to": new["act"].get("celex")},
            "legal_basis": legal,
            "templates_added": [k for k in nt if k not in ot], "templates_removed": [k for k in ot if k not in nt],
            "changed": changed, "unchanged": unchanged,
            "kind": ("template change" if structural else "wording" if wording
                     else "references only" if changed or legal or old["act"].get("celex") != new["act"].get("celex") else "no impact")}


# ───────────────────────────── coverage: every spec cell is mapped, nothing stale ─────────────────────────────

SOURCES = ("computed", "input", "n/a")


def coverage(spec: dict, binding: dict) -> dict:
    """binding = {template_id: {"rows": {row_id: source}, "columns": {col_id: source}}}, source one of SOURCES
    (a prefix: 'computed:gross'). Returns what the spec has that the binding does not map, what the binding maps
    that the spec no longer has, and sources that are not one of the three kinds."""
    missing, stale, bad = [], [], []
    for t in spec["templates"]:
        if t["structure"] != "full":
            continue
        b = binding.get(t["id"]) or {}
        for axis in ("rows", "columns"):
            ids = {i["id"] for i in t[axis]}
            mapped = b.get(axis) or {}
            missing += [f"{t['id']}.{axis}.{i}" for i in sorted(ids - set(mapped))]
            stale += [f"{t['id']}.{axis}.{i}" for i in sorted(set(mapped) - ids)]
            bad += [f"{t['id']}.{axis}.{i}={s}" for i, s in mapped.items() if str(s).split(":", 1)[0] not in SOURCES]
    full = {t["id"] for t in spec["templates"] if t["structure"] == "full"}
    stale += [f"{tid} (template)" for tid in binding if tid not in full]
    return {"complete": not (missing or stale or bad), "missing": missing, "stale": stale, "invalid": bad}


# ───────────────────────────── supplied cells: a template cell the institution provides ─────────────────────────────

def supplied_cell(framework: str, key: str, period_end) -> dict:
    """A spec cell key '<template id>.<row id>.<column id>' (e.g. 'T10.3.c') that the governing spec for `period_end`
    has and the implementation's binding marks as supplied (input). Raises SpecError otherwise — a supplied value can
    only ever target a real, suppliable cell."""
    from services.regspec.bindings import binding_for
    parts = key.split(".")
    if len(parts) != 3:
        raise SpecError(f"'{key}' is not a template cell key (<template>.<row>.<column>)")
    tid, rid, cid = parts
    spec = governing(framework, period_end=period_end, disclosure_date=period_end)
    if spec is None:
        raise SpecError(f"no adopted {framework} specification governs {period_end}")
    t = template(spec, tid)
    row = next((r for r in t.get("rows") or [] if r["id"] == rid), None)
    col = next((c for c in t.get("columns") or [] if c["id"] == cid), None)
    if row is None or col is None:
        raise SpecError(f"{t.get('code') or tid} has no row {rid} / column {cid}")
    b = (binding_for(framework) or {}).get(tid) or {}
    if not str(b.get("columns", {}).get(cid, "")).startswith("input") or str(b.get("rows", {}).get(rid, "")) == "n/a":
        raise SpecError(f"{t.get('code') or tid} row {rid}, column {cid} is not a value the institution supplies")
    return {"template": tid, "row": rid, "column": cid, "spec": spec["version"],
            "label": f"{t.get('code') or tid}, row {rid}, column {cid} — {(row['label'].split(' > ')[-1] or '')[:60]} · "
                     f"{col['label'].split(' > ')[-1][:60]}"}

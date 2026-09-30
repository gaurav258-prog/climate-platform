"""Regulatory specifications — each version of a regulation's templates as a versioned file (the change route, step 3).

A spec file (data/reference/regspec/<framework>/<version>.json) is the regulation, captured from the official text:
the act, its status (adopted / draft), when it applies, the legal basis and every template — for a template built
to the letter ("structure": "full") every row and column exactly as printed, with the instruction paragraphs quoted;
for a template printed as a document to complete (questions, tick boxes, fill-in blanks, charts: "structure":
"document") every printed item in reading order, with its kind and its parent.
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
STRUCTURES = ("full", "listed", "document")
# what a printed item of a document template is (see the capture brief): the kinds a binding fills are FILLED
ITEM_KINDS = ("heading", "field", "question", "choice", "chart", "chart_label", "table", "table_column", "definition", "text")
FIXED_KINDS = ("heading", "definition", "text", "chart_label", "table_column")
# which date chooses the governing version: the date the disclosure is made, the reference date of the figures, or the
# first day of the financial year the figures are for ('applies to financial years beginning on or after …', ESRS)
BASES = ("disclosure_date", "period_end", "financial_year_start")


class SpecError(ValueError):
    pass


def _iso(v) -> str | None:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)).isoformat()
    except ValueError:
        return "invalid"


# the parts of a phase-in's eligibility_only the engines apply (services.reference.taxonomy_activities.eligibility_only
# for activities, the objectives also by taxonomy_gar): a spec may carry only these
PHASE_IN_READ = frozenset({"objectives", "activities"})


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
    opt = doc.get("transitional_option")
    if opt is not None:
        need = ("ref", "quote", "switch", "elected_value", "financial_year_starts", "then_governed_by")
        if any(not opt.get(k) for k in need):
            errs.append(f"transitional_option needs {need}")
        elif any(_iso((opt["financial_year_starts"] or {}).get(k)) in (None, "invalid") for k in ("from", "until")):
            errs.append("transitional_option.financial_year_starts needs from and until dates")
    for ph in doc.get("phase_in") or []:
        if not (ph.get("ref") and ph.get("quote") and ph.get("eligibility_only")) or any(
                _iso((ph.get("disclosures") or {}).get(k)) in (None, "invalid") for k in ("from", "until")):
            errs.append("each phase_in needs ref, quote, eligibility_only and disclosures from / until dates")
        elif set(ph["eligibility_only"]) - PHASE_IN_READ:
            # every part of a phase-in must have a reader (E32): an unread part would be quoted but not applied
            errs.append(f"phase_in.eligibility_only has parts no engine reads: {sorted(set(ph['eligibility_only']) - PHASE_IN_READ)}")
    ids = [t.get("id") for t in doc["templates"]]
    if len(ids) != len(set(ids)) or not all(ids):
        errs.append("template ids must be present and unique")
    for t in doc["templates"]:
        tid = t.get("id")
        if not t.get("title") or not t.get("ref"):
            errs.append(f"{tid}: title and ref are required")
        if t.get("structure") not in STRUCTURES:
            errs.append(f"{tid}: structure must be one of {STRUCTURES}")
        if t.get("structure") == "document":
            errs += _document_errors(t)
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


def _document_errors(t: dict) -> list[str]:
    tid, items = t["id"], t.get("items") or []
    if not items:
        return [f"{tid}: a document template needs its items"]
    errs = []
    ids = [i.get("id") for i in items]
    # an element printed without a title (a table, a tree, a free-standing instruction) says so: a note or its instruction
    if len(ids) != len(set(ids)) or not all(ids) or not all(i.get("label") or i.get("instruction") or i.get("note") for i in items):
        errs.append(f"{tid}: items need unique ids and labels (an untitled item carries its instruction or a note)")
    bad = sorted({str(i.get("kind")) for i in items} - set(ITEM_KINDS))
    if bad:
        errs.append(f"{tid}: unknown item kinds {bad}")
    orphans = [i["id"] for i in items if i.get("parent") and i["parent"] not in set(ids)]
    if orphans:
        errs.append(f"{tid}: items whose parent is not an item: {orphans[:5]}")
    return errs


def items_to_fill(t: dict) -> list[dict]:
    """The items of a document template a binding must say how it fills (not fixed printed wording)."""
    return [i for i in t.get("items") or [] if i["kind"] not in FIXED_KINDS]


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


def fy_start(period_end: date | str) -> date:
    """The first day of the twelve-month financial year ending on period_end (a year ending 29 February starts 1 March)."""
    from datetime import timedelta
    pe = date.fromisoformat(str(period_end)[:10])
    try:
        return date(pe.year - 1, pe.month, pe.day) + timedelta(days=1)
    except ValueError:                                      # 29 February has no counterpart a year earlier
        return date(pe.year - 1, 3, 1)


def governing(framework: str, *, period_end: date | str, disclosure_date: date | str | None = None,
              elections: dict | None = None, financial_year_start: date | str | None = None) -> dict | None:
    """The adopted spec that governs a filing. Each spec says which date decides (applies.basis): the reference date
    of the figures, or the date the disclosure is made (defaults to today). Drafts never govern.

    A spec may let an undertaking keep the previous rules for some financial years (its transitional_option, e.g.
    Art. 4 of Delegated Regulation 2026/73 for the year starting in 2025): when the organisation has made that election
    (`elections[switch] == elected_value`, a governed methodology switch) and the filing's financial year starts in the
    window, the version the option names governs instead."""
    pe = _iso(period_end)
    dd = _iso(disclosure_date) or date.today().isoformat()
    fys = _iso(financial_year_start) or fy_start(pe).isoformat()   # a 12-month year when not given
    for s in reversed(versions(framework)):
        if s["status"] != "adopted":
            continue
        on = {"disclosure_date": dd, "financial_year_start": fys}.get(s["applies"]["basis"], pe)
        if s["applies"]["from"] <= on and (not s["applies"].get("until") or on <= s["applies"]["until"]):
            opt = s.get("transitional_option")
            fy = fys
            if (opt and fy and (elections or {}).get(opt["switch"]) == opt["elected_value"]
                    and opt["financial_year_starts"]["from"] <= fy <= opt["financial_year_starts"]["until"]):
                return load(framework, opt["then_governed_by"])
            return s
    return None



def phase_in(spec: dict, disclosure_date: date | str) -> dict | None:
    """The phase-in of this spec that covers a disclosure made on this date (its eligibility_only part says what is
    disclosed for eligibility only), or None."""
    on = _iso(disclosure_date)
    return next((ph for ph in spec.get("phase_in") or []
                 if ph["disclosures"]["from"] <= on <= ph["disclosures"]["until"]), None)


_USAGE = Path(__file__).resolve().parents[2] / "data" / "reference" / "regspec_usage.json"


def report_types() -> list[str]:
    """The report types a specification family governs (data/reference/regspec_usage.json)."""
    return list(json.loads(_USAGE.read_text())["report_types"])


def families_for(report_type: str) -> list[str]:
    """The specification families that govern a report type (data/reference/regspec_usage.json)."""
    return list(json.loads(_USAGE.read_text())["report_types"].get(report_type, []))


def embeds_previous_period(report_type: str) -> str | None:
    """The key a filing of this report type freezes its book under, when it carries the previous period's book (its
    templates print T-1 / N-1); None otherwise."""
    pp = json.loads(_USAGE.read_text()).get("previous_period", {})
    return pp.get("book_key", {}).get(report_type) if report_type in pp.get("report_types", []) else None


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
        for axis in ("rows", "columns", "items"):
            d = _axis_diff(a.get(axis), b.get(axis))
            if any(d.values()):
                c[axis] = d
        (changed if len(c) > 1 else unchanged).append(c if len(c) > 1 else tid)
    legal = {f: {"from": old["legal_basis"].get(f), "to": new["legal_basis"].get(f)}
             for f in ("article", "templates_in", "instructions_in") if old["legal_basis"].get(f) != new["legal_basis"].get(f)}
    structural = bool([k for k in nt if k not in ot] or [k for k in ot if k not in nt]
                      or any(set(c) & {"structure", "z_axis"} for c in changed)
                      or any((c.get(a) or {}).get(k) for c in changed for a in ("rows", "columns", "items")
                             for k in ("added", "removed", "moved")))
    wording = any("title" in c or any((c.get(a) or {}).get("relabelled") for a in ("rows", "columns", "items"))
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
    """binding = {template_id: {"rows": {row_id: source}, "columns": {col_id: source}}} ({"items": {item_id: source}}
    for a document template), source one of SOURCES
    (a prefix: 'computed:gross'). Returns what the spec has that the binding does not map, what the binding maps
    that the spec no longer has, and sources that are not one of the three kinds."""
    missing, stale, bad = [], [], []
    for t in spec["templates"]:
        b = binding.get(t["id"]) or {}
        if t["structure"] == "document":              # every item to fill is mapped; fixed wording is printed as is
            ids = {i["id"] for i in items_to_fill(t)}
            mapped = b.get("items") or {}
            missing += [f"{t['id']}.items.{i}" for i in sorted(ids - set(mapped))]
            stale += [f"{t['id']}.items.{i}" for i in sorted(set(mapped) - ids)]
            bad += [f"{t['id']}.items.{i}={s}" for i, s in mapped.items() if str(s).split(":", 1)[0] not in SOURCES]
            continue
        if t["structure"] != "full":
            continue
        for axis in ("rows", "columns"):
            ids = {i["id"] for i in t[axis]}
            mapped = b.get(axis) or {}
            missing += [f"{t['id']}.{axis}.{i}" for i in sorted(ids - set(mapped))]
            stale += [f"{t['id']}.{axis}.{i}" for i in sorted(set(mapped) - ids)]
            bad += [f"{t['id']}.{axis}.{i}={s}" for i, s in mapped.items() if str(s).split(":", 1)[0] not in SOURCES]
    full = {t["id"] for t in spec["templates"] if t["structure"] in ("full", "document")}
    stale += [f"{tid} (template)" for tid in binding if tid not in full]
    return {"complete": not (missing or stale or bad), "missing": missing, "stale": stale, "invalid": bad}


# ───────────────────────────── supplied cells: a template cell the institution provides ─────────────────────────────

def supplied_cell(framework: str, key: str, period_end, *, elections: dict | None = None,
                  disclosure_date=None) -> dict:
    """A spec cell key '<template id>.<row id>.<column id>' (e.g. 'T10.3.c') that the governing spec for the period has
    and the implementation's binding marks as supplied (input). `framework` is a report type or a spec family: a report
    type's cells are those of the family governing it (regspec_usage.json). A template disclosed once per KPI basis
    names it: 'T1@capex.54.c'. The version is the one governing a disclosure made now (or on disclosure_date), with
    the organisation's elections. Raises SpecError otherwise — a supplied value only ever targets a real, suppliable
    cell."""
    from services.regspec.bindings import binding_for
    parts = key.split(".")
    if len(parts) != 3:
        raise SpecError(f"'{key}' is not a template cell key (<template>.<row>.<column>)")
    tid, rid, cid = parts
    tid, _, basis = tid.partition("@")
    family = (families_for(framework) or [framework])[0]
    pe = date.fromisoformat(str(period_end)[:10])
    spec = governing(family, period_end=pe, disclosure_date=disclosure_date, elections=elections,
                     financial_year_start=date(pe.year, 1, 1) if (pe.month, pe.day) == (12, 31) else None)
    if spec is None:
        raise SpecError(f"no adopted {family} specification governs {period_end}")
    t = template(spec, tid)
    row = next((r for r in t.get("rows") or [] if r["id"] == rid), None)
    col = next((c for c in t.get("columns") or [] if c["id"] == cid), None)
    if row is None or col is None:
        raise SpecError(f"{t.get('code') or tid} has no row {rid} / column {cid}")
    b = (binding_for(family, spec) or {}).get(tid) or {}
    if basis and basis not in (b.get("bases") or []):
        raise SpecError(f"{t.get('code') or tid} is not disclosed per KPI basis '{basis}'")
    if b.get("bases") and not basis:
        raise SpecError(f"{t.get('code') or tid} is disclosed turnover-based and CapEx-based: name the basis ('{tid}@turnover.{rid}.{cid}')")
    row_src, col_src = str(b.get("rows", {}).get(rid, "")), str(b.get("columns", {}).get(cid, ""))
    entered_basis = bool(basis) and basis in (b.get("input_bases") or [])      # e.g. a CapEx copy the undertaking enters
    if row_src == "n/a" or not (entered_basis or col_src.startswith("input") or row_src.startswith("input")):
        raise SpecError(f"{t.get('code') or tid} row {rid}, column {cid} is not a value the institution supplies")
    unit = next((src.split("|", 1)[1] for src in (col_src, row_src) if src.startswith("input") and "|" in src), None)
    return {"template": tid, "row": rid, "column": cid, "spec": spec["version"], "basis": basis or None, "unit": unit,
            "label": f"{t.get('code') or tid}, row {rid}, column {cid} — {(row['label'].split(' > ')[-1] or '')[:60]} · "
                     f"{col['label'].split(' > ')[-1][:60]}"}

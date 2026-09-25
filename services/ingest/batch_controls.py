"""Intake controls — the reconciliation gates between "a customer's file arrived" and "rows reach the engine".

Row-level validation (upload_validation.validate_table) answers "is each row acceptable?". It does not answer the
questions a controller asks of any data feed:

  1. RECEIPT      did everything arrive, and nothing extra?   row count / control totals vs what the customer says
                  they sent, duplicate rows, a file we have already imported.
  2. TRANSFORM    did parsing keep the values right?           every money field ties: raw total = accepted + rejected;
                  every accepted value is typed correctly (a number, a valid coordinate, an ISO date), and the
                  value EXCLUDED by rejections is stated, not hidden.
  3. GATE         is the batch fit to enter the engine?        a reject share (by count and by value) above the
                  limit, or any failed control, needs a named person's sign-off with a reason; nothing else lands.
  4. LANDING      did what passed actually land?               rows validated == rows stored (+ value), after the
                  sector's own ingestion rules; anything dropped there is reported, not silent.

Pure functions only (no database) so every sector calls the same code; batches.py persists the outcome.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Optional

import pandas as pd

DEFAULT_THRESHOLDS = {
    "max_reject_pct": 5.0,          # rejected rows above this share of the file need sign-off
    "max_reject_value_pct": 2.0,    # rejected VALUE above this share of the file's total needs sign-off
    "tie_tolerance_pct": 0.01,      # raw = accepted + rejected must hold to within this (rounding only)
    "control_total_tolerance_pct": 0.1,   # a declared control total may differ by this much (rounding in the source)
}

_MAX_LISTED = 10   # cap on row numbers quoted in a message


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


_US_GROUPED = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")
_PLAIN = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def parse_money(v: Any) -> Optional[float]:
    """The one money parser. Accepts a plain number ("1250000.5"), or thousands-grouped in the English form
    ("1,250,000.50"); spaces / underscores as separators are stripped. Anything with a comma that is NOT a clean
    thousands grouping ("1.234,5", "1,5") is refused — a European decimal comma is ambiguous, and silently
    reading "1.234,5" as 1.2345 would be a thousand-fold error inside a filing. Blank / NaN → None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    s = str(v).strip().replace(" ", "").replace("_", "")
    if not s:
        return None
    if "," in s:
        if not _US_GROUPED.match(s):
            return None
        s = s.replace(",", "")
    if not _PLAIN.match(s):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def _blank(v: Any) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(v, str) and not v.strip()


def _rel_diff_pct(a: float, b: float) -> float:
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom * 100.0


def _check(check: str, label: str, status: str, expected=None, actual=None, detail: str = "") -> dict:
    return {"check": check, "label": label, "status": status, "expected": expected, "actual": actual, "detail": detail}


# ───────────────────────────────────────── 1. receipt ─────────────────────────────────────────

def receipt_check(df: pd.DataFrame, *, declared: Optional[dict] = None, duplicate_of: Optional[dict] = None,
                  thresholds: Optional[dict] = None) -> dict:
    """Did everything arrive, and nothing extra? `declared` = what the customer says they sent:
    {"row_count": int, "control_totals": {"appraised_value_eur": 1.2e9, ...}}. Declaring is optional; when given,
    a mismatch is a failed control (needs sign-off), never a silent pass."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    declared = declared or {}
    checks: list[dict] = []
    n = int(len(df))

    checks.append(_check("file_has_rows", "The file contains data rows", "pass" if n > 0 else "fail",
                         expected=">= 1 row", actual=n, detail="" if n > 0 else "The file has a header but no data rows."))

    dup_mask = df.astype(str).duplicated(keep="first") if n else pd.Series([], dtype=bool)
    dup_rows = [int(i) + 2 for i in dup_mask[dup_mask].index]
    checks.append(_check("no_duplicate_rows", "No row appears twice", "fail" if dup_rows else "pass",
                         expected=0, actual=len(dup_rows),
                         detail=(f"Exact duplicate rows at spreadsheet rows {dup_rows[:_MAX_LISTED]}"
                                 f"{' …' if len(dup_rows) > _MAX_LISTED else ''} — importing would double-count them.") if dup_rows else ""))

    if duplicate_of:
        checks.append(_check("file_not_already_imported", "This exact file has not been imported before", "fail",
                             expected="new file", actual="already imported",
                             detail=f"An identical file was imported on {duplicate_of.get('imported_at') or duplicate_of.get('received_at')}. "
                                    "Importing it again would double-count the whole book."))
    else:
        checks.append(_check("file_not_already_imported", "This exact file has not been imported before", "pass",
                             expected="new file", actual="new file"))

    if declared.get("row_count") is not None:
        exp = int(declared["row_count"])
        checks.append(_check("declared_row_count", "Row count matches what you said you sent",
                             "pass" if exp == n else "fail", expected=exp, actual=n,
                             detail="" if exp == n else f"You declared {exp} rows; the file has {n}."))

    for field, exp in (declared.get("control_totals") or {}).items():
        label = f"{field} total matches what you said you sent"
        if field not in df.columns:
            checks.append(_check(f"declared_total:{field}", label, "fail", expected=exp, actual=None,
                                 detail=f"The file has no column '{field}' to total."))
            continue
        try:
            exp_f = float(exp)
        except (TypeError, ValueError):
            checks.append(_check(f"declared_total:{field}", label, "fail", expected=exp, actual=None,
                                 detail="The declared total is not a number."))
            continue
        vals = [parse_money(v) for v in df[field]]
        unparseable = sum(1 for raw, p in zip(df[field], vals) if p is None and not _blank(raw))
        actual = float(sum(v for v in vals if v is not None))
        ok = _rel_diff_pct(exp_f, actual) <= th["control_total_tolerance_pct"] and unparseable == 0
        detail = ""
        if not ok:
            detail = f"Declared {exp_f:,.2f}; the file totals {actual:,.2f} (difference {actual - exp_f:,.2f})."
            if unparseable:
                detail += f" {unparseable} cell(s) in this column are not readable as numbers."
        checks.append(_check(f"declared_total:{field}", label, "pass" if ok else "fail", expected=exp_f, actual=actual, detail=detail))

    return {"status": "fail" if any(c["status"] == "fail" for c in checks) else "pass",
            "n_rows": n, "declared": bool(declared.get("row_count") is not None or declared.get("control_totals")),
            "checks": checks}


# ───────────────────────────────────────── normalise ─────────────────────────────────────────

def normalise_rows(rows: list[dict], specs: list[dict]) -> list[dict]:
    """Turn validated rows into the exact typed form the ingestion cores expect — so "what passed validation" and
    "what the engine reads" are the same values. Without this a cell such as "1,250,000" passes validation (the
    validator strips the commas) but the ingestion core's float() would read it as missing and drop the row."""
    by_name = {s["name"]: s for s in specs}
    out = []
    for r in rows:
        n: dict = {}
        for k, v in r.items():
            if _blank(v):
                n[k] = None
                continue
            kind = (by_name.get(k) or {}).get("kind")
            if kind == "money":
                n[k] = parse_money(v)
            elif kind in ("lat", "lon"):
                n[k] = parse_money(v)
            elif kind == "int":
                f = parse_money(v)
                n[k] = int(f) if f is not None and f == int(f) else None
            elif kind == "date":
                n[k] = str(v).strip()[:10]
            elif kind == "iso2":
                n[k] = str(v).strip().upper()
            elif kind == "enum":
                allowed = (by_name.get(k) or {}).get("allowed") or []
                m = next((a for a in allowed if str(a).upper() == str(v).strip().upper()), None)
                n[k] = m if m is not None else str(v).strip()
            elif isinstance(v, str):
                n[k] = v.strip()
            else:
                n[k] = v
        out.append(n)
    return out


# ───────────────────────────────────────── 2. transformation ─────────────────────────────────────────

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def transformation_check(df: pd.DataFrame, specs: list[dict], report: dict, normalised: list[dict], *,
                         value_field: Optional[str] = None, thresholds: Optional[dict] = None) -> dict:
    """Did parsing keep the values right? For every money column: raw total = accepted + rejected (within rounding);
    every accepted value has the right type/range; and the value carried by rejected rows is stated."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    n_total = int(report.get("n_total", len(df)))
    n_error = int(report.get("n_error", 0))
    rejected_idx = {int(e["row"]) - 2 for e in report.get("errors", [])}
    records = df.where(pd.notnull(df), None).to_dict("records")

    tie_outs: list[dict] = []
    for s in specs:
        name, kind = s["name"], s.get("kind")
        if kind != "money" or name not in df.columns:
            continue
        raw_vals = [parse_money(r.get(name)) for r in records]
        unparseable = sum(1 for r, p in zip(records, raw_vals) if p is None and not _blank(r.get(name)))
        raw_total = float(sum(v for v in raw_vals if v is not None))
        rejected = float(sum(v for i, v in enumerate(raw_vals) if v is not None and i in rejected_idx))
        accepted = float(sum(v for v in (n.get(name) for n in normalised) if isinstance(v, (int, float))))
        diff_pct = _rel_diff_pct(raw_total, accepted + rejected)
        # unparseable cells sit in REJECTED rows (the validator refuses them), so they add to neither side
        ok = diff_pct <= th["tie_tolerance_pct"]
        tie_outs.append({"field": name, "raw_total": raw_total, "accepted_total": accepted, "rejected_total": rejected,
                         "unparseable_cells": unparseable, "status": "pass" if ok else "fail",
                         "detail": "" if ok else f"raw {raw_total:,.2f} ≠ accepted {accepted:,.2f} + rejected {rejected:,.2f}"})

    form_violations: list[dict] = []
    n_form = 0
    for n_i, n in enumerate(normalised):
        for s in specs:
            name, kind, v = s["name"], s.get("kind"), n.get(s["name"])
            if v is None:
                continue
            bad = None
            if kind == "money" and not isinstance(v, (int, float)):
                bad = "not a number"
            elif kind == "lat" and not (isinstance(v, (int, float)) and -90 <= v <= 90):
                bad = "not a valid latitude"
            elif kind == "lon" and not (isinstance(v, (int, float)) and -180 <= v <= 180):
                bad = "not a valid longitude"
            elif kind == "int" and not isinstance(v, int):
                bad = "not a whole number"
            elif kind == "date" and not (isinstance(v, str) and _DATE_RE.match(v)):
                bad = "not an ISO date"
            if bad:
                n_form += 1
                if len(form_violations) < 25:   # counted in full, listed up to 25
                    form_violations.append({"accepted_row_index": n_i, "field": name, "problem": bad})

    excluded_value = excluded_value_pct = None
    if value_field and value_field in df.columns:
        vals = [parse_money(r.get(value_field)) for r in records]
        total_v = float(sum(v for v in vals if v is not None))
        excluded_value = float(sum(v for i, v in enumerate(vals) if v is not None and i in rejected_idx))
        excluded_value_pct = (excluded_value / total_v * 100.0) if total_v else 0.0
    coord_ok = None
    if any(s.get("kind") == "lat" for s in specs) and n_total:
        coord_ok = round(100.0 * sum(1 for n in normalised if n.get("latitude") is not None and n.get("longitude") is not None)
                         / n_total, 1)

    status = "pass" if all(t["status"] == "pass" for t in tie_outs) and n_form == 0 else "fail"
    return {"status": status, "tie_outs": tie_outs, "form_violations": form_violations, "n_form_violations": n_form,
            "excluded": {"n_rows": n_error, "pct_rows": round(100.0 * n_error / n_total, 2) if n_total else 0.0,
                         "value_field": value_field, "value": excluded_value,
                         "pct_value": round(excluded_value_pct, 2) if excluded_value_pct is not None else None},
            "coordinates_usable_pct": coord_ok}


# ───────────────────────────────────────── 3. gate ─────────────────────────────────────────

def evaluate_gate(receipt: dict, transform: dict, n_valid: int, thresholds: Optional[dict] = None) -> dict:
    """pass  — the batch may land. needs_signoff — it may land only when a named person accepts the listed reasons.
    blocked — there is nothing valid to land, so there is nothing to sign off."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    if n_valid == 0:
        return {"status": "blocked", "reasons": ["No row passed validation, so nothing can be imported."], "thresholds": th}
    reasons: list[str] = []
    for c in receipt["checks"]:
        if c["status"] == "fail":
            reasons.append(f"Receipt: {c['label']} — {c['detail'] or 'failed'}")
    for t in transform["tie_outs"]:
        if t["status"] == "fail":
            reasons.append(f"Transformation: {t['field']} does not tie — {t['detail']}")
    if transform["n_form_violations"]:
        reasons.append(f"Transformation: {transform['n_form_violations']} accepted value(s) are not in the required form.")
    ex = transform["excluded"]
    if ex["pct_rows"] > th["max_reject_pct"]:
        reasons.append(f"{ex['n_rows']} rows ({ex['pct_rows']}%) were rejected — above the {th['max_reject_pct']}% limit.")
    if ex["pct_value"] is not None and ex["pct_value"] > th["max_reject_value_pct"]:
        reasons.append(f"Rejected rows carry {ex['pct_value']}% of the file's {ex['value_field']} — above the "
                       f"{th['max_reject_value_pct']}% limit.")
    return {"status": "needs_signoff" if reasons else "pass", "reasons": reasons, "thresholds": th}


# ───────────────────────────────────────── 4. landing ─────────────────────────────────────────

def landing_check(*, n_valid: int, n_landed: int, value_valid: Optional[float] = None,
                  value_landed: Optional[float] = None, thresholds: Optional[dict] = None) -> dict:
    """Did what passed validation actually land? Rows can be dropped AFTER validation by a sector's own rules
    (a missing valuation, an unknown commodity); those are reported here so nothing vanishes silently."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    dropped = max(0, int(n_valid) - int(n_landed))
    value_ok = True
    if value_valid is not None and value_landed is not None:
        value_ok = _rel_diff_pct(value_valid, value_landed) <= th["tie_tolerance_pct"]
    return {"status": "pass" if dropped == 0 and value_ok else "attention", "n_validated": int(n_valid), "n_landed": int(n_landed),
            "n_dropped_after_validation": dropped, "value_validated": value_valid, "value_landed": value_landed,
            "detail": "" if dropped == 0 and value_ok else
            f"{dropped} validated row(s) did not land" + ("" if value_ok else "; the landed value does not tie to the validated value") + "."}

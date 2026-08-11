"""Validate an uploaded book (CSV or Excel) BEFORE anything is saved — so a preparer sees exactly which rows
are ready and which need fixing, with a plain-language reason per problem row, and nothing lands in the golden
source until they confirm. Reusable across sectors: the caller passes the column spec for its template.

Two entry points share one validator:
  • a dry-run (validate only) that returns the report for the upload preview, and
  • the real import, which re-validates and ingests only the rows that pass.
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Optional

import pandas as pd

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_table(raw: bytes, filename: Optional[str]) -> pd.DataFrame:
    """Read an uploaded CSV or Excel file into a dataframe. Raises ValueError (→ a clean 400) on anything else."""
    name = (filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xlsm", ".xls")):
            return pd.read_excel(io.BytesIO(raw))
        if name.endswith((".csv", ".txt")):
            return pd.read_csv(io.BytesIO(raw))
    except Exception as e:  # noqa: BLE001 — surface a readable parse error to the user
        raise ValueError(f"We couldn't read that file — please check it opens as a table. ({e})")
    raise ValueError("Please upload a CSV or Excel (.xlsx) file.")


def _clean(v) -> Optional[str]:
    if v is None:
        return None
    try:
        if pd.isna(v):   # a blank cell arrives as NaN in a numeric column — treat it as empty, not "nan"
            return None
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    return s or None


def _check_kind(kind: Optional[str], label: str, raw) -> Optional[str]:
    """Return a plain-language problem message, or None if the value is acceptable for its kind."""
    v = _clean(raw)
    if v is None:
        return None  # emptiness is handled by the required-check upstream
    if kind in ("lat", "lon"):
        try:
            f = float(v)
        except ValueError:
            return f"{label} must be a number (got “{v}”)"
        if kind == "lat" and not -90 <= f <= 90:
            return f"{label} must be between −90 and 90 (got {f})"
        if kind == "lon" and not -180 <= f <= 180:
            return f"{label} must be between −180 and 180 (got {f})"
    elif kind == "money":
        try:
            f = float(str(v).replace(",", ""))
        except ValueError:
            return f"{label} must be a number (got “{v}”)"
        if f < 0:
            return f"{label} can't be negative (got {f})"
    elif kind == "date":
        if not _DATE_RE.match(v):
            return f"{label} must be a date as YYYY-MM-DD (got “{v}”)"
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            return f"{label} isn't a valid calendar date (got “{v}”)"
    elif kind == "iso2":
        if not re.fullmatch(r"[A-Za-z]{2}", v):
            return f"{label} must be a 2-letter country code (got “{v}”)"
    return None


def validate_table(df: pd.DataFrame, specs: list[dict]) -> dict:
    """Validate every row against the column spec. `specs` items: {name, required, kind?, label?}.

    Returns a preview report — never writes anything:
      { ok, missing_columns, n_total, n_valid, n_error,
        errors: [{row, problems:[str]}],   # row = 1-based spreadsheet row (header = row 1)
        valid_rows: [ {...} ] }             # the rows that passed, ready to ingest
    """
    present = set(df.columns)
    missing_columns = [s["name"] for s in specs if s.get("required") and s["name"] not in present]
    if missing_columns:
        return {"ok": False, "missing_columns": missing_columns, "n_total": int(len(df)),
                "n_valid": 0, "n_error": 0, "errors": [], "valid_rows": []}

    records = df.where(pd.notnull(df), None).to_dict("records")
    valid_rows: list[dict] = []
    errors: list[dict] = []
    for i, row in enumerate(records):
        problems: list[str] = []
        for s in specs:
            label = s.get("label") or s["name"]
            val = row.get(s["name"])
            if s.get("required") and _clean(val) is None:
                problems.append(f"{label} is required")
                continue
            msg = _check_kind(s.get("kind"), label, val)
            if msg:
                problems.append(msg)
        if problems:
            errors.append({"row": i + 2, "problems": problems})   # +2: 1 header row + 1-based
        else:
            valid_rows.append(row)

    return {"ok": True, "missing_columns": [], "n_total": len(records),
            "n_valid": len(valid_rows), "n_error": len(errors), "errors": errors, "valid_rows": valid_rows}

"""Column-mapping profiles: how one customer source's file maps onto a Tellumen template.

A profile says, per template field, which source column feeds it, and optionally how to transform it:
    {"multiply": 1000}                      values given in thousands
    {"currency": "USD"}                     whole column in USD → EUR at the ECB rate for the book date
    {"currency_column": "Ccy"}              currency per row, read from another source column
    {"values": {"Concrete": "fire_resistive", "n/a": ""}}   the customer's values → ours ("" = leave blank, on purpose)
Profiles are versioned and immutable (DB trigger): editing saves a new version, and every batch records the exact
version that produced its values. Unmapped source columns are reported, never silently used. A profile remembers
the layout (column names) it was confirmed on: a later file with the same layout uses it automatically.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingest.batch_controls import parse_money
from services.ingest.fields import norm_token
from services.intake.values import is_blank


class MappingError(ValueError):
    pass


def fingerprint(columns: list[str]) -> str:
    """The file's layout: its column names, ignoring case, spacing, separators and order."""
    return hashlib.sha256("|".join(sorted(norm_token(c) for c in columns)).encode()).hexdigest()[:32]


def validate_profile(column_map: dict, transforms: dict, specs: list[dict]) -> None:
    names = {s["name"] for s in specs}
    kinds = {s["name"]: s.get("kind") for s in specs}
    if not isinstance(column_map, dict) or not column_map:
        raise MappingError("The mapping must name at least one source column.")
    bad = [t for t in column_map if t not in names]
    if bad:
        raise MappingError(f"Not fields of this template: {', '.join(bad)}")
    srcs = [v for v in column_map.values() if v]
    if len(srcs) != len(set(srcs)):
        raise MappingError("One source column is mapped to two fields.")
    for t, spec in (transforms or {}).items():
        if t not in names:
            raise MappingError(f"Transform for unknown field '{t}'.")
        if not isinstance(spec, dict) or not set(spec) <= {"multiply", "currency", "currency_column", "values"}:
            raise MappingError(f"Transform for '{t}' is not recognised.")
        if ("currency" in spec or "currency_column" in spec or "multiply" in spec) and kinds.get(t) != "money":
            raise MappingError(f"'{t}' is not a money field, so it can't be scaled or converted.")
        if "multiply" in spec and not isinstance(spec["multiply"], (int, float)):
            raise MappingError(f"Scale for '{t}' must be a number.")


def save(session: Session, org_id: str, template: str, name: str, column_map: dict, transforms: dict,
         user_id: str, specs: list[dict], source_columns: Optional[list[str]] = None) -> dict:
    name = (name or "").strip()
    if not name:
        raise MappingError("Give the mapping a name (for example the source system).")
    validate_profile(column_map, transforms or {}, specs)
    v = (session.execute(text("""SELECT COALESCE(MAX(version), 0) FROM intake_mapping_profiles
                                 WHERE org_id = CAST(:o AS uuid) AND template = :t AND name = :n"""),
                         {"o": org_id, "t": template, "n": name}).scalar() or 0) + 1
    pid = session.execute(text("""
        INSERT INTO intake_mapping_profiles (org_id, template, name, version, column_map, transforms, created_by,
                                             source_fingerprint, source_columns)
        VALUES (CAST(:o AS uuid), :t, :n, :v, CAST(:c AS jsonb), CAST(:x AS jsonb), CAST(:u AS uuid), :fp, CAST(:sc AS jsonb))
        RETURNING profile_id::text
    """), {"o": org_id, "t": template, "n": name, "v": v, "c": json.dumps(column_map), "x": json.dumps(transforms or {}),
           "u": user_id, "fp": fingerprint(source_columns) if source_columns else None,
           "sc": json.dumps(source_columns) if source_columns else None}).scalar()
    return {"profile_id": pid, "name": name, "version": v}


def get(session: Session, org_id: str, profile_id: str) -> dict:
    try:
        r = session.execute(text("""SELECT profile_id::text, template, name, version, column_map, transforms FROM intake_mapping_profiles
                                    WHERE org_id = CAST(:o AS uuid) AND profile_id = CAST(:p AS uuid)"""),
                            {"o": org_id, "p": profile_id}).mappings().first()
    except Exception:
        r = None
    if not r:
        raise MappingError("Mapping not found.")
    return dict(r)


def for_layout(session: Session, org_id: str, template: str, columns: list[str]) -> Optional[dict]:
    """The confirmed mapping for exactly this layout: the latest version of the ONE named mapping whose latest version
    was confirmed on these columns. Two different mappings claiming the same layout → None (ask, don't guess)."""
    fp = fingerprint(columns)
    rows = [r for r in latest(session, org_id, template) if r.get("source_fingerprint") == fp]
    return get(session, org_id, rows[0]["profile_id"]) if len(rows) == 1 else None


def closest(session: Session, org_id: str, template: str, columns: list[str]) -> Optional[dict]:
    """A saved mapping whose columns mostly still exist in this file — the starting point when a layout changed."""
    have = {norm_token(c) for c in columns}
    best, score = None, 0.0
    for r in latest(session, org_id, template):
        src = [s for s in (r["column_map"] or {}).values() if s]
        if not src:
            continue
        s = sum(1 for c in src if norm_token(c) in have) / len(src)
        if s > score:
            best, score = r, s
    return {**best, "overlap": round(score, 2)} if best and score >= 0.5 else None


def latest(session: Session, org_id: str, template: Optional[str] = None) -> list[dict]:
    rows = session.execute(text("""
        SELECT DISTINCT ON (template, name) profile_id::text, template, name, version, column_map, transforms, created_at,
               source_fingerprint, source_columns
        FROM intake_mapping_profiles WHERE org_id = CAST(:o AS uuid) AND (CAST(:t AS text) IS NULL OR template = :t)
        ORDER BY template, name, version DESC
    """), {"o": org_id, "t": template}).mappings().all()
    return [{**dict(r), "created_at": str(r["created_at"])[:19]} for r in rows]


def apply(session: Session, df: pd.DataFrame, profile: dict, as_of: Optional[date] = None) -> tuple[pd.DataFrame, dict]:
    """Rename and transform source columns into template columns. Returns (canonical dataframe, report).
    A currency transform does NOT convert here: it says which currency a field's amounts are in — a fixed code
    (report['field_currency']) or a per-row column (carried as a hidden column) — and services/intake/money.py
    converts every amount in one place, at the book date and by the rate policy. (`as_of` is unused, kept for callers.)"""
    from services.intake.money import hidden_column
    cmap, tr = profile["column_map"], profile.get("transforms") or {}
    missing_src = [s for s in list(cmap.values()) + [x.get("currency_column") for x in tr.values()] if s and s not in df.columns]
    if missing_src:
        raise MappingError(f"The file has no column(s) {', '.join(missing_src)} that this mapping expects.")
    out = pd.DataFrame({t: df[s] for t, s in cmap.items() if s})
    report: dict = {"profile_id": profile["profile_id"], "profile": f"{profile['name']} v{profile['version']}",
                    "mapped": {t: s for t, s in cmap.items() if s},
                    "unmapped_source_columns": [c for c in df.columns if c not in set(cmap.values()) and
                                                c not in {x.get("currency_column") for x in tr.values()}],
                    "conversions": [], "field_currency": {}}
    for t, spec in tr.items():
        if t not in out.columns:
            continue
        col = out[t]
        if "values" in spec:
            vm = {norm_token(k): v for k, v in spec["values"].items()}
            out[t] = [(vm[norm_token(v)] or None) if not is_blank(v) and norm_token(v) in vm else v for v in col]
            report["conversions"].append({"field": t, "kind": "vocabulary", "n_values": len(vm)})
            col = out[t]
        if "multiply" in spec:
            m = float(spec["multiply"])
            out[t] = [(parse_money(v) * m if parse_money(v) is not None else v) for v in col]
            report["conversions"].append({"field": t, "kind": "scale", "factor": m})
        if "currency" in spec:
            report["field_currency"][t] = str(spec["currency"]).upper()
            report["conversions"].append({"field": t, "kind": "currency", "currency": report["field_currency"][t]})
        elif "currency_column" in spec:
            out[hidden_column(t)] = df[spec["currency_column"]].values
            report["conversions"].append({"field": t, "kind": "currency", "currency_column": spec["currency_column"]})
    return out, report

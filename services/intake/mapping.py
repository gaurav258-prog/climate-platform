"""Column-mapping profiles: how one customer source's file maps onto a Tellumen template.

A profile says, per template field, which source column feeds it, and optionally how to transform it:
    {"multiply": 1000}                      values given in thousands
    {"currency": "USD"}                     whole column in USD → EUR at the ECB rate for the book date
    {"currency_column": "Ccy"}              currency per row, read from another source column
    {"values": {"Concrete": "fire_resistive"}}   the customer's vocabulary → ours
Profiles are versioned and immutable (DB trigger): editing saves a new version, and every batch records the exact
version that produced its values. Unmapped source columns are reported, never silently used.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingest.batch_controls import parse_money

_SYNONYMS = {
    "latitude": ["lat", "y", "latitude_dd"], "longitude": ["lon", "lng", "long", "x", "longitude_dd"],
    "external_ref": ["id", "asset_id", "loan_id", "policy_id", "property_id", "holding_id", "plot_id", "reference", "ref", "your_asset_id"],
    "asset_name": ["name", "asset", "property", "borrower_name", "collateral_name"],
    "policy_name": ["name", "location_name", "location", "site_name", "risk_name"],
    "property_name": ["name", "property", "building", "asset_name"],
    "holding_name": ["name", "issuer", "security_name", "company"],
    "plot_name": ["name", "farm", "farm_name", "plot"],
    "appraised_value_eur": ["value", "appraised_value", "collateral_value", "market_value"],
    "sum_insured_eur": ["tiv", "total_insured_value", "sum_insured", "insured_value"],
    "building_value_eur": ["building_value", "buildings"], "contents_value_eur": ["contents_value", "contents"],
    "business_interruption_value_eur": ["bi_value", "business_interruption", "bi"],
    "property_value_eur": ["value", "market_value", "property_value", "valuation"],
    "position_value_eur": ["value", "market_value", "position_value", "exposure"],
    "annual_noi_eur": ["noi", "net_operating_income"], "annual_spend_eur": ["spend", "annual_spend", "purchases"],
    "country": ["country_code", "iso2", "ctry"], "year_built": ["built", "year_of_construction", "yearbuilt"],
    "number_of_stories": ["stories", "storeys", "floors", "number_of_floors"],
    "counterparty_evic_eur": ["evic", "enterprise_value"], "construction_type": ["construction", "construction_class"],
}


STALE_RATE_DAYS = 7   # an FX rate older than this, relative to the book date, needs a person to accept it


class MappingError(ValueError):
    pass


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def suggest(columns: list[str], specs: list[dict]) -> dict[str, str]:
    """Best-guess source column per template field (exact name, then known synonyms). Only unambiguous guesses."""
    keyed = {_key(c): c for c in columns}
    out: dict[str, str] = {}
    used: set[str] = set()
    for s in specs:
        f = s["name"]
        for cand in [f, f.removesuffix("_eur"), *_SYNONYMS.get(f, [])]:
            k = _key(cand)
            if k in keyed and keyed[k] not in used:
                out[f] = keyed[k]
                used.add(keyed[k])
                break
    return out


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
         user_id: str, specs: list[dict]) -> dict:
    name = (name or "").strip()
    if not name:
        raise MappingError("Give the mapping a name (for example the source system).")
    validate_profile(column_map, transforms or {}, specs)
    v = (session.execute(text("""SELECT COALESCE(MAX(version), 0) FROM intake_mapping_profiles
                                 WHERE org_id = CAST(:o AS uuid) AND template = :t AND name = :n"""),
                         {"o": org_id, "t": template, "n": name}).scalar() or 0) + 1
    pid = session.execute(text("""
        INSERT INTO intake_mapping_profiles (org_id, template, name, version, column_map, transforms, created_by)
        VALUES (CAST(:o AS uuid), :t, :n, :v, CAST(:c AS jsonb), CAST(:x AS jsonb), CAST(:u AS uuid)) RETURNING profile_id::text
    """), {"o": org_id, "t": template, "n": name, "v": v, "c": json.dumps(column_map), "x": json.dumps(transforms or {}),
           "u": user_id}).scalar()
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


def latest(session: Session, org_id: str, template: Optional[str] = None) -> list[dict]:
    rows = session.execute(text("""
        SELECT DISTINCT ON (template, name) profile_id::text, template, name, version, column_map, transforms, created_at
        FROM intake_mapping_profiles WHERE org_id = CAST(:o AS uuid) AND (CAST(:t AS text) IS NULL OR template = :t)
        ORDER BY template, name, version DESC
    """), {"o": org_id, "t": template}).mappings().all()
    return [{**dict(r), "created_at": str(r["created_at"])[:19]} for r in rows]


def apply(session: Session, df: pd.DataFrame, profile: dict, as_of: Optional[date] = None) -> tuple[pd.DataFrame, dict]:
    """Rename and transform source columns into template columns. Returns (canonical dataframe, report)."""
    from services.reference.fx import FxError, to_eur
    cmap, tr = profile["column_map"], profile.get("transforms") or {}
    missing_src = [s for s in cmap.values() if s and s not in df.columns]
    if missing_src:
        raise MappingError(f"The file has no column(s) {', '.join(missing_src)} that this mapping expects.")
    out = pd.DataFrame({t: df[s] for t, s in cmap.items() if s})
    report: dict = {"profile_id": profile["profile_id"], "profile": f"{profile['name']} v{profile['version']}",
                    "mapped": {t: s for t, s in cmap.items() if s},
                    "unmapped_source_columns": [c for c in df.columns if c not in set(cmap.values()) and
                                                c not in {x.get("currency_column") for x in tr.values()}],
                    "conversions": []}
    as_of = as_of or date.today()
    for t, spec in tr.items():
        if t not in out.columns:
            continue
        col = out[t]
        if "values" in spec:
            vm = {str(k).strip().lower(): v for k, v in spec["values"].items()}
            out[t] = [vm.get(str(v).strip().lower(), v) if v is not None and not (isinstance(v, float) and pd.isna(v)) else v for v in col]
            report["conversions"].append({"field": t, "kind": "vocabulary", "n_values": len(vm)})
            col = out[t]
        if "multiply" in spec:
            m = float(spec["multiply"])
            out[t] = [(parse_money(v) * m if parse_money(v) is not None else v) for v in col]
            report["conversions"].append({"field": t, "kind": "scale", "factor": m})
            col = out[t]
        if "currency" in spec or "currency_column" in spec:
            ccys = ([spec["currency"]] * len(col) if "currency" in spec else list(df[spec["currency_column"]]))
            rates: dict = {}
            conv = []
            for v, c in zip(col, ccys):
                amt = parse_money(v)
                if amt is None or c is None or (isinstance(c, float) and pd.isna(c)):
                    conv.append(v)   # left as-is: validation reports it
                    continue
                try:
                    r = to_eur(session, amt, str(c), as_of)
                except FxError:
                    conv.append(f"unknown currency {c}")   # becomes a clear row error, never a guessed rate
                    continue
                rates[r["currency"]] = {"rate": r["rate"], "rate_date": r["rate_date"], "source": r["source"]}
                conv.append(r["eur"])
            out[t] = conv
            report["conversions"].append({"field": t, "kind": "currency", "rates": rates})
            for ccy, r in rates.items():
                if not r.get("rate_date"):
                    continue
                age = (as_of - date.fromisoformat(str(r["rate_date"])[:10])).days
                if age > STALE_RATE_DAYS:
                    report.setdefault("warnings", []).append(
                        f"{t}: the latest {ccy}→EUR rate we hold is from {r['rate_date']}, {age} days before the book date")
    return out, report

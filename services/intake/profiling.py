"""Column profiling: propose, for any sector's template, which of the customer's columns feeds each field — from the
column NAMES and the column VALUES — with a confidence and the reasons, for the customer to confirm or correct.

Driven entirely by the field catalogue (kind, aliases, vocabulary, range), so it works for every sector unchanged.

Confidence:
  high    the name matches the field (or a known alias) AND the values fit the field
  medium  the name only partly matches but the values fit — or the values alone are unmistakable (coordinates,
          ISO country codes, a known value list, GeoJSON)
  low     the name matches but the values do NOT fit — shown so the customer looks, never silently used
Money is never proposed from values alone: a column of numbers could be any amount in any unit.
"""
from __future__ import annotations

import json
import re
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from services.ingest.batch_controls import parse_money
from services.ingest.fields import norm_token
from services.intake import values as V
from services.reference.iso_country import ISO_ALPHA2

_RANK = {"high": 3, "medium": 2, "low": 1}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_CCY = re.compile(r"^[A-Z]{3}$")
_VALUE_ONLY_KINDS = {"lat", "lon", "iso2", "vocab", "geojson", "date"}


def profile_column(s: pd.Series) -> dict:
    vals = [v for v in s.tolist() if not V.is_blank(v)]
    n = len(vals)
    strs = [str(v).strip() for v in vals]
    nums = [x for x in (parse_money(v) for v in vals) if x is not None]
    out = {"n": int(len(s)), "n_filled": n, "n_distinct": len(set(strs)), "samples": list(dict.fromkeys(strs))[:5],
           "numeric_share": len(nums) / n if n else 0.0}
    if nums:
        ser = pd.Series(nums)
        out.update({"min": float(ser.min()), "max": float(ser.max()), "median": float(ser.median()),
                    "int_share": sum(1 for x in nums if float(x).is_integer()) / n})
    if n:
        out["iso2_share"] = sum(1 for x in strs if x.upper() in ISO_ALPHA2 and len(x) == 2) / n
        out["date_share"] = sum(1 for x in strs if _DATE.match(x)) / n
        out["ccy_share"] = sum(1 for x in strs if _CCY.match(x)) / n
        out["unique_ratio"] = len(set(strs)) / n
        out["geojson_share"] = sum(1 for x in strs[:50] if _is_geojson(x)) / min(n, 50)
    return out


def _is_geojson(x: str) -> bool:
    if not x.startswith("{"):
        return False
    try:
        return json.loads(x).get("type") in ("Polygon", "MultiPolygon", "Point")
    except (ValueError, AttributeError):
        return False


def _header_forms(col: str) -> set[str]:
    """The ways a column name can be read: as written; without unit words ('Value (k USD)' → 'value'); with a
    trailing No / Nr / Number read as an ID ('Facility No' → 'facility_id')."""
    toks = [x for x in re.split(r"[^a-z0-9]+", str(col).lower()) if x]
    bare = [x for x in toks if x not in _SCALE_TOKENS and x not in _CURRENCIES] or toks
    forms = {"_".join(toks), "_".join(bare)}
    for f in list(forms):
        parts = f.split("_")
        if len(parts) > 1 and parts[-1] in ("no", "nr", "num", "number"):
            forms.add("_".join(parts[:-1] + ["id"]))
    return forms


def _header_fit(spec: dict, col: str) -> float:
    forms = _header_forms(col)
    names = {spec["name"], spec["name"].removesuffix("_eur"), norm_token(spec.get("label", ""))}
    if forms & names:
        return 1.0
    if forms & {norm_token(a) for a in spec.get("aliases", [])}:
        return 0.9
    c = max(forms, key=len)
    toks = set(c.split("_")) - {"", "eur", "the", "of"}
    ftoks = set(spec["name"].removesuffix("_eur").split("_"))
    return 0.5 if toks and ftoks and (toks <= ftoks or ftoks <= toks) and len(toks & ftoks) >= 1 else 0.0


def _content_fit(spec: dict, p: dict, vocab_lookup: Optional[dict]) -> tuple[float, str]:
    kind, n = spec.get("field_kind", spec.get("kind")), p["n_filled"]
    if not n:
        return 0.3, "column is empty"
    num = p["numeric_share"]
    lo, hi = p.get("min"), p.get("max")
    if kind == "lat":
        return (0.9, "numbers between −90 and 90") if num > 0.95 and lo >= -90 and hi <= 90 else (0.0, "values are not latitudes")
    if kind == "lon":
        if num > 0.95 and lo >= -180 and hi <= 180:
            return (0.95 if max(abs(lo), abs(hi)) > 90 else 0.8), "numbers between −180 and 180"
        return 0.0, "values are not longitudes"
    if kind in ("money", "number", "fraction", "int"):
        if num < 0.95:
            return 0.0, "values are not numbers"
        rng = spec.get("range")
        if rng and not (rng[0] <= lo and hi <= rng[1]):
            return 0.1, f"values run {lo:g}–{hi:g}, outside {rng[0]:g}–{rng[1]:g}"
        if kind == "int" and p.get("int_share", 0) < 0.95:
            return 0.1, "values are not whole numbers"
        if kind == "money" and lo < 0:
            return 0.2, "some values are negative"
        return (0.7 if rng else 0.5), "numbers" + (f" within {rng[0]:g}–{rng[1]:g}" if rng else "")
    if kind == "date":
        return (0.85, "dates as YYYY-MM-DD") if p.get("date_share", 0) > 0.9 else (0.1, "values are not YYYY-MM-DD dates")
    if kind == "iso2":
        return (0.9, "ISO-2 country codes") if p.get("iso2_share", 0) > 0.9 else (0.05, "values are not 2-letter country codes")
    if kind == "geojson":
        return (0.95, "GeoJSON shapes") if p.get("geojson_share", 0) > 0.9 else (0.0, "values are not GeoJSON")
    if kind == "vocab" and vocab_lookup is not None:
        share = _vocab_share(p, vocab_lookup)
        if share >= 0.6:
            return 0.9 * share, f"{round(100 * share)}% of the values are on our list"
        return 0.35, "few values are on our list yet — map them below"
    if kind == "id":
        return (0.6, "a unique value on every row") if p.get("unique_ratio", 0) > 0.98 else (0.2, "values repeat")
    if kind == "name":
        return (0.5, "text, mostly unique") if num < 0.5 and p.get("unique_ratio", 0) > 0.5 else (0.2, "does not look like names")
    return (0.4, "text") if num < 0.95 else (0.2, "numbers")


def _vocab_share(p: dict, lookup: dict) -> float:
    vals = p.get("_all_distinct") or p["samples"]
    return sum(1 for v in vals if norm_token(v) in lookup) / len(vals) if vals else 0.0


def suggest(session: Optional[Session], df: pd.DataFrame, specs: list[dict]) -> dict:
    cols = [str(c) for c in df.columns]
    profiles: dict[str, dict] = {}
    for c in cols:
        p = profile_column(df[c])
        p["_all_distinct"] = list(dict.fromkeys(str(v).strip() for v in df[c].tolist() if not V.is_blank(v)))[:200]
        profiles[c] = p
    lookups = {s["vocab"]: V.lookup(session, s["vocab"]) for s in specs if s.get("vocab")}

    cands = []
    for s in specs:
        for c in cols:
            h = _header_fit(s, c)
            fit, why = _content_fit(s, profiles[c], lookups.get(s.get("vocab")))
            kind = s.get("field_kind", s.get("kind"))
            if h >= 0.9:
                conf = "high" if fit >= 0.3 else "low"
                reasons = [f"column named “{c}”", why]
            elif h >= 0.5 and fit >= 0.5:
                conf, reasons = "medium", [f"column name “{c}” is close", why]
            elif h == 0 and kind in _VALUE_ONLY_KINDS and (fit >= 0.8 or (kind == "vocab" and fit >= 0.5)):
                conf, reasons = "medium", [f"recognised from the values in “{c}”", why]
            else:
                continue
            cands.append((_RANK[conf], h + fit, s["name"], c, conf, reasons))

    fields: dict[str, dict] = {}
    used: set[str] = set()
    for _, _, f, c, conf, reasons in sorted(cands, key=lambda x: (-x[0], -x[1])):
        if f in fields or c in used:
            continue
        fields[f] = {"column": c, "confidence": conf, "reasons": reasons}
        used.add(c)

    # latitude and longitude told apart by values alone only when the longitudes go beyond ±90
    la, lo_ = fields.get("latitude"), fields.get("longitude")
    if la and lo_ and la["confidence"] == lo_["confidence"] == "medium":
        lo_max = max(abs(profiles[lo_["column"]].get("min", 0)), abs(profiles[lo_["column"]].get("max", 0)))
        if lo_max <= 90:
            for m in (la, lo_):
                m["confidence"] = "low"
                m["reasons"].append("latitude and longitude can't be told apart from these values — check which is which")

    hints: dict[str, list[str]] = {}
    units = {c: header_units(c) for c in cols}
    ccy_cols = [c for c in cols if profiles[c].get("ccy_share", 0) > 0.9 and c not in used]
    for s in specs:
        m = fields.get(s["name"])
        if not m or s.get("kind") != "money":
            continue
        u = units.get(m["column"]) or {}
        if u:
            m["transform"] = u
            m["reasons"].append("column name says " + " and ".join(
                [f"× {u['multiply']:,.0f}"] * ("multiply" in u) + [u["currency"]] * ("currency" in u)))
        med = profiles[m["column"]].get("median")
        if med is not None and 0 < med < 1000 and "multiply" not in u:
            hints.setdefault(s["name"], []).append(f"values are small (typical {med:,.0f}) — are they in thousands or millions?")
        if ccy_cols:
            hints.setdefault(s["name"], []).append(f"column “{ccy_cols[0]}” looks like a currency code per row")

    # for every value-list field and every column with few distinct values: their value → ours (None = not recognised),
    # so whichever column the customer picks, the editor can show which values match and which need mapping
    categorical = [c for c in cols if 0 < profiles[c]["n_distinct"] <= 50]
    value_suggestions = {s["name"]: {c: V.suggest(session, s["vocab"], profiles[c]["_all_distinct"]) for c in categorical}
                         for s in specs if s.get("vocab")}

    for p in profiles.values():
        p.pop("_all_distinct", None)
    return {"fields": fields, "columns": profiles, "hints": hints, "values": value_suggestions,   # field → column → their → ours
            "currency_columns": ccy_cols, "units": {c: u for c, u in units.items() if u}}


_SCALE_TOKENS = {"k": 1e3, "000": 1e3, "000s": 1e3, "thousand": 1e3, "thousands": 1e3, "ks": 1e3, "tsd": 1e3,
                 "m": 1e6, "mn": 1e6, "mm": 1e6, "mio": 1e6, "million": 1e6, "millions": 1e6, "bn": 1e9, "billion": 1e9}
_CURRENCIES = {"eur", "usd", "gbp", "chf", "jpy", "sek", "nok", "dkk", "pln", "czk", "huf", "cad", "aud", "cny", "brl", "inr", "zar", "sgd", "hkd"}


def header_units(col: str) -> dict:
    """Units stated in a column name: 'Value (k USD)' → {multiply: 1000, currency: 'USD'}; 'TIV EUR m' → ×1e6.
    Only explicit tokens count; a bare 'Value' says nothing."""
    toks = [t for t in re.split(r"[^a-z0-9]+", str(col).lower()) if t]
    out: dict = {}
    for tok in toks[1:] if len(toks) > 1 else []:     # the first token is the field's own name, never a unit
        if tok in _SCALE_TOKENS and "multiply" not in out:
            out["multiply"] = _SCALE_TOKENS[tok]
        elif tok in _CURRENCIES and "currency" not in out:
            out["currency"] = tok.upper()
    if out.get("currency") == "EUR":
        out.pop("currency")
    return out


def column_map(suggestion: dict, min_conf: str = "medium") -> dict[str, str]:
    """The proposed field → column map (only suggestions at or above `min_conf`)."""
    return {f: m["column"] for f, m in suggestion["fields"].items() if _RANK[m["confidence"]] >= _RANK[min_conf]}

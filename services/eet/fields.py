"""The European ESG Template (EET) field list and the check each field's value must pass.

The list is FinDatEx's own (data/reference/eet/eet_fields.json, built by scripts/build_eet_fields.py from the official
Excel) — every field in its fixed order, with its format ("codification") and whether it is Mandatory / Conditional /
Optional for each use. A value — computed by Tellumen or typed by the manager — is checked against the format before
it can enter a file: a proportion is a decimal between 0 and 1 (0.5 = 50%), a Y/N field is Y or N, a closed list takes
only its codes. Nothing is coerced silently.
"""
from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "eet" / "eet_fields.json"
USES = ("periodic", "precontractual", "entity", "mifid", "idd", "look_through")
USE_LABEL = {"periodic": "SFDR periodic", "precontractual": "SFDR pre-contractual", "entity": "SFDR entity (PAI)",
             "mifid": "MiFID products", "idd": "IDD products", "look_through": "Funds of funds / look-through"}
# the data-set flags (00060–00100) that say which uses a file carries
USE_FLAG = {"precontractual": "00060_EET_Data_Reporting_SFDR_Pre_Contractual",
            "periodic": "00070_EET_Data_Reporting_SFDR_Periodic",
            "entity": "00080_EET_Data_Reporting_SFDR_Entity_Level",
            "mifid": "00090_EET_Data_Reporting_MiFID", "idd": "00100_EET_Data_Reporting_IDD"}


class EETValueError(ValueError):
    pass


@lru_cache(maxsize=1)
def registry() -> dict:
    return json.loads(_FILE.read_text())


def version() -> str:
    return registry()["version"]


def fields() -> list[dict]:
    return registry()["fields"]


@lru_cache(maxsize=1)
def by_name() -> dict[str, dict]:
    return {f["name"]: f for f in fields()}


def requirement(f: dict, uses: tuple[str, ...]) -> Optional[str]:
    """The strictest requirement across the chosen uses: M > C > O > None."""
    got = {f["req"].get(u) for u in uses}
    for level in ("M", "C", "O"):
        if level in got:
            return level
    return None


def _first(cod: Optional[str]) -> str:
    return (cod or "").split("\n")[0].strip()


def kind(f: dict) -> str:
    c = _first(f["codification"]).lower()
    if c.startswith("floating decimal") and "0.5 = 50%" in c.replace("  ", " "):
        return "proportion"
    if c.startswith(("floating decimal", "number with decimal")):
        return "number"
    if c.startswith("integer"):
        return "integer"
    if c.startswith("yyyy-mm-dd") and "hh:mm" in c:
        return "datetime"
    if c.startswith("yyyy-mm-dd /"):
        return "dates"
    if c.startswith("yyyy-mm-dd"):
        return "date"
    if c.startswith("code iso 4217"):
        return "currency"
    if re.fullmatch(r"[A-Z]{2}(;[A-Z]{2})+", _first(f["codification"])):
        return "codes2"                       # ISO country / language lists: MM;IQ, EN;FR;DE
    if " / " in c or " or " in c or " ; " in c:
        return "choice"
    return "text"


def choices(f: dict) -> tuple[set[str], bool]:
    """(allowed codes, multi-select) for a closed-list field."""
    c = _first(f["codification"])
    multi = ";" in c
    toks = re.split(r"\s*/\s*|\s+or\s+|\s*;\s*", c)
    allowed = {t.strip() for t in toks if t.strip() and len(t.strip()) <= 8}
    return allowed, multi


def check(name: str, value) -> str:
    """The value as it goes into the file, or EETValueError saying what the field takes."""
    f = by_name().get(name)
    if f is None:
        raise EETValueError(f"'{name}' is not an EET {version()} field")
    s = str(value).strip() if value is not None else ""
    if not s:
        raise EETValueError("empty")
    k = kind(f)
    try:
        if k == "proportion":
            v = float(s.replace(",", "."))
            if not 0 <= v <= 1:
                raise EETValueError("a proportion is a decimal from 0 to 1 (0.5 = 50%)")
            return _num(v)
        if k == "number":
            return _num(float(s.replace(",", ".")))
        if k == "integer":
            v = int(s)
            if v < 0:
                raise EETValueError("must not be negative")
            return str(v)
        if k == "date":
            return date.fromisoformat(s[:10]).isoformat()
        if k == "dates":
            return ";".join(date.fromisoformat(x.strip()[:10]).isoformat() for x in s.split(";") if x.strip())
        if k == "currency":
            if not re.fullmatch(r"[A-Z]{3}", s.upper()):
                raise EETValueError("an ISO 4217 code, e.g. EUR")
            return s.upper()
        if k == "codes2":
            codes = [x.strip().upper() for x in s.split(";") if x.strip()]
            if not all(re.fullmatch(r"[A-Z]{2}", x) for x in codes):
                raise EETValueError("two-letter codes separated by ';' (e.g. FR;DE)")
            return ";".join(codes)
        if k == "choice":
            allowed, multi = choices(f)
            picked = [x.strip() for x in (s.split(";") if multi else [s]) if x.strip()]
            letters = {t for a in allowed for t in a.split(";")}
            bad = [x for x in picked if x not in allowed and x not in letters]
            if bad or not picked:
                raise EETValueError(f"one of {' / '.join(sorted(allowed))}" + (" (several separated by ';')" if multi else ""))
            return ";".join(picked)
    except ValueError as e:
        if isinstance(e, EETValueError):
            raise
        raise EETValueError(f"expected {_first(f['codification'])}") from e
    limit = 255 if "max 255" in (f["codification"] or "") else 500 if "max 500" in (f["codification"] or "") else 2000
    if len(s) > limit:
        raise EETValueError(f"at most {limit} characters")
    return s


def _num(v: float) -> str:
    return f"{v:.10g}"

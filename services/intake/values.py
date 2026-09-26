"""Value matching: every field with a fixed list of values (construction class, EPC grade, commodity…) is matched to
our list for every file, every sector, before validation.

    their value ─► the customer's own value mapping (applied earlier, recorded on the mapping profile)
               ─► exact match to our list, ignoring case / spaces / separators, or a catalogue synonym
               ─► otherwise NOT RECOGNISED: reported with its count, never guessed.

An unrecognised value in an optional field is left blank — and the batch says so, as a failed check a second person
must accept (or the customer maps the value and re-checks). In a required field the row is refused with the reason.
Nothing is dropped silently.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingest.fields import VOCABS, norm_token


def is_blank(v) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(v, str) and not v.strip()


def lookup(session: Optional[Session], vocab: str) -> dict[str, str]:
    """norm_token(value) → our value, for one vocabulary."""
    v = VOCABS[vocab]
    if not v.dynamic:
        return v.lookup()
    if vocab == "commodity" and session is not None:
        return {norm_token(r[0]): r[0] for r in session.execute(text("SELECT name FROM sc_commodities")).all()}
    if vocab == "country":
        # ISO alpha-2 codes are always recognised (as before the country reference existed); names, alpha-3 and
        # numeric codes come from the CLDR reference once loaded (feed `reference_countries`)
        from services.reference.countries import lookup as country_lookup
        from services.reference.iso_country import ISO_ALPHA2
        return {**{c.lower(): c for c in ISO_ALPHA2}, **(country_lookup(session) if session is not None else {})}
    return {}


def allowed(session: Optional[Session], vocab: str) -> list[str]:
    return sorted(set(lookup(session, vocab).values()))


def normalise(session: Optional[Session], df: pd.DataFrame, specs: list[dict]) -> tuple[pd.DataFrame, dict]:
    """Match every vocabulary field to our values. Returns (dataframe with our values, report per field)."""
    out = df.copy()
    report: dict[str, dict] = {}
    for s in specs:
        name, vocab = s["name"], s.get("vocab")
        if not vocab or name not in out.columns:
            continue
        lk = lookup(session, vocab)
        unknown: dict[str, int] = {}
        n_recognised = 0
        vals = []
        for v in out[name]:
            if is_blank(v):
                vals.append(None)
                continue
            hit = lk.get(norm_token(v))
            if hit is not None:
                n_recognised += 1
                vals.append(hit)
                continue
            key = str(v).strip()
            unknown[key] = unknown.get(key, 0) + 1
            vals.append(key if s.get("required") else None)   # required: the row is refused with the reason
        out[name] = pd.Series(vals, index=out.index, dtype=object)
        top = dict(sorted(unknown.items(), key=lambda kv: -kv[1])[:25])
        report[name] = {"label": s.get("label", name), "required": bool(s.get("required")), "n_recognised": n_recognised,
                        "n_unknown": sum(unknown.values()), "n_unknown_values": len(unknown), "unknown": top}
    return out, report


def gate_reason(report: dict) -> Optional[str]:
    """Optional fields whose values we could not recognise — they were left blank, so a person must accept it."""
    parts = []
    for name, r in report.items():
        if r["n_unknown"] and not r["required"]:
            eg = ", ".join(f"“{k}” ×{c}" for k, c in list(r["unknown"].items())[:3])
            parts.append(f"{r['label']}: {r['n_unknown_values']} value(s) not recognised ({eg}{', …' if r['n_unknown_values'] > 3 else ''})")
    if not parts:
        return None
    return "Values: " + "; ".join(parts) + " — left blank unless you map them to ours."


def suggest(session: Optional[Session], vocab: str, their_values: list[str]) -> dict[str, Optional[str]]:
    """For the mapping editor: each of the customer's values → our value when it is an exact equivalent, else None."""
    lk = lookup(session, vocab)
    return {v: lk.get(norm_token(v)) for v in their_values}

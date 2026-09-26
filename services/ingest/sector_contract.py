"""The sector contract and the row rules every sector shares (split out of sector_ingest to keep each file small).

A row rule either returns a clean value or raises RowIssue with a message the customer can act on; nothing is guessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

import h3
import pandas as pd
from sqlalchemy.orm import Session

from services.ingest.fields import VOCABS, norm_token


class RowIssue(Exception):
    """This row cannot become an asset; the message is shown to the customer."""


# ───────────────────────────── value helpers ─────────────────────────────

def _blank(v) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(v, str) and not v.strip()


def _s(row: dict, k: str) -> Optional[str]:
    v = row.get(k)
    return None if _blank(v) else str(v).strip()


def _f(row: dict, k: str) -> Optional[float]:
    v = row.get(k)
    if _blank(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        raise RowIssue(f"{k} is not a number")


def _i(row: dict, k: str) -> Optional[int]:
    f = _f(row, k)
    return None if f is None else int(f)


def _vocab(row: dict, k: str, vocab: str) -> Optional[str]:
    """Our value for a fixed-list field. In the intake pipeline values are already matched (and anything
    unrecognised reported) by services/intake/values.py; this is the same lookup, so the two cannot disagree."""
    v = _s(row, k)
    return None if v is None else VOCABS[vocab].lookup().get(norm_token(v))


def _bool(row: dict, k: str) -> Optional[bool]:
    v = _vocab(row, k, "boolean")
    return None if v is None else v == "true"


def _location(row: dict) -> tuple[float, float, str]:
    lat, lon = _f(row, "latitude"), _f(row, "longitude")
    if lat is None or lon is None:
        raise RowIssue("location is missing")
    if abs(lat) < 1e-6 and abs(lon) < 1e-6:
        raise RowIssue("location is 0,0 (a placeholder, not a real place)")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise RowIssue("location is out of range")
    return lat, lon, h3.latlng_to_cell(lat, lon, 8)


def _m(row: dict, k: str, dp: int = 2) -> Optional[float]:
    v = _f(row, k)
    return None if v is None else round(v, dp)


def _positive(row: dict, k: str, label: str) -> float:
    v = _m(row, k)
    if v is None:
        raise RowIssue(f"{label} is missing")
    if v <= 0:
        raise RowIssue(f"{label} must be greater than zero")
    return v


def _plausible_building(rec: dict) -> None:
    yb = rec.get("year_built")
    if yb is not None and not (1800 <= yb <= date.today().year + 1):
        raise RowIssue(f"year_built {yb} is not plausible")
    ns = rec.get("number_of_stories")
    if ns is not None and not (0 <= ns <= 200):
        raise RowIssue(f"number_of_stories {ns} is not plausible")


# ───────────────────────────── the sector contract ─────────────────────────────

@dataclass
class Sector:
    key: str
    name_field: str                         # record key holding the asset's name
    value_field: str                        # record key holding the value that ties to the file
    compare: tuple[str, ...]                # record keys a customer file may change on an existing asset
    prepare: Callable[[Session, str], dict]
    build: Callable[[dict, dict], dict]     # (ctx, canonical row) → record  | raises RowIssue
    existing: Callable[[Session, str], list[dict]]
    insert: Callable[[Session, str, dict, list[dict]], None]
    update: Callable[[Session, str, dict, list[dict]], None]
    table: str = "portfolio_entities"       # where the sector's assets live, and their id column — used to record
    id_column: str = "entity_id"            # where each stored amount came from (money_source)
    notes: dict = field(default_factory=dict)

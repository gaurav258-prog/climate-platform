"""Issuers' real sites from public registers of facilities (the product owner's decisions of 2026-10-23).

A fund issuer located only by its head office (services.reference.footprint) has no physical site; registers of
facilities name each site's owner. This module ties register sites to issuers only where the register itself states
the tie, and records each site with its source, how it was tied, and what the register states of it:

  Climate TRACE   ownership files (one row per owner along each source's ownership chain) state the owner's LEI —
                  'parent_lei: GLEIF Legal Entity Identifier for parent entity' (the package's data guide) — and its
                  share of the source (overall_share_percent). A source whose owner LEI is an issuer's LEI is that
                  issuer's site: match_basis 'register_lei'.
  EEA register    names the parent company only (services.reference.register_matching): a site there becomes an
                  issuer's only after a person confirms the name match: match_basis 'reviewed_name'.

No register states a site's share of the company's value, so every register site carries weight basis 'not_stated'
(weight 0) — a named gap in the loss look-through, never a number (decided 2026-10-23). The site's own facts (the
register's id, activity, capacity with its unit, emissions, the owner's share, the ownership path) are kept in
site_facts, as the register states them.

The register files are read from data/datasets/<register> (git-ignored, fetched by scripts/fetch_climate_trace.py), each
checked against the size and sha-256 recorded in data/reference/supply_datasets.json before it is read.

  climate_trace_sites(session)    the sites Climate TRACE ties to an issuer by its LEI (no database writes)
  record(session, sites)          write sites as issuer facilities (one per issuer, register and register id); returns
                                  the new cells to score
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import defaultdict
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.loss.registry import ROOT

log = logging.getLogger(__name__)
MANIFEST = ROOT / "data" / "reference" / "supply_datasets.json"
H3_RESOLUTION = 8
NOT_STATED = "not_stated"
GAS = "co2e_100yr"


class RegisterError(ValueError):
    pass


def manifest(key: str) -> dict:
    entry = json.loads(MANIFEST.read_text(encoding="utf-8")).get(key)
    if not entry:
        raise RegisterError(f"the register '{key}' is not recorded in {MANIFEST.name}: fetch it first")
    return entry


def checked_files(key: str, pattern: str) -> list:
    """The register's recorded files whose name matches `pattern`, each checked against its recorded size and
    sha-256 — a file that differs is refused, never read."""
    out = []
    for f in manifest(key)["files"]:
        p = ROOT / f["file"]
        if not re.search(pattern, p.name):
            continue
        if not p.exists() or p.stat().st_size != f["bytes"]:
            raise RegisterError(f"{p.name}: missing or not the size recorded when it was fetched")
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != f["sha256"]:
            raise RegisterError(f"{p.name}: differs from the file recorded when it was fetched (its checksum)")
        out.append(p)
    return out


def issuers_by_lei(session: Session) -> dict[str, list[str]]:
    by: dict[str, list[str]] = defaultdict(list)
    for lei, issuer_id in session.execute(text("SELECT lei, issuer_id::text FROM issuers WHERE lei IS NOT NULL")).all():
        by[lei.strip().upper()].append(issuer_id)
    return by


def iso2_by_iso3(session: Session) -> dict[str, str]:
    return {r[0].strip(): r[1].strip() for r in session.execute(text(
        "SELECT iso3, iso2 FROM ref_countries WHERE iso3 IS NOT NULL AND is_country")).all()}


def _share(v) -> Optional[float]:
    """The owner's share of the source as the register states it, 0..1; None where it states none (or zero)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x / 100.0, 6) if 0 < x <= 100 else None


def _year_facts(rows) -> dict:
    """What the register states of a source over its latest year: emissions and activity summed over the year's
    periods (CO2e, 100-year), the capacity of its latest period, each with its unit as stated."""
    import pandas as pd
    rows = rows.assign(year=pd.to_datetime(rows["start_time"]).dt.year).sort_values("start_time")
    y = int(rows["year"].max())
    yr = rows[rows["year"] == y]
    last = yr.iloc[-1]

    def num(v):
        try:
            f = float(v)
            return None if f != f else f
        except (TypeError, ValueError):
            return None
    em = [num(v) for v in yr["emissions_quantity"]]
    act = [num(v) for v in yr["activity"]]
    return {"year": y, "periods": int(len(yr)), "granularity": str(last["temporal_granularity"]),
            "emissions_t_co2e_100yr": sum(v for v in em if v is not None) if any(v is not None for v in em) else None,
            "activity": sum(v for v in act if v is not None) if any(v is not None for v in act) else None,
            "activity_units": None if pd.isna(last["activity_units"]) else str(last["activity_units"]),
            "capacity": num(last["capacity"]),
            "capacity_units": None if pd.isna(last["capacity_units"]) else str(last["capacity_units"]),
            "capacity_period": str(last["start_time"])[:10],
            "source_type": None if pd.isna(last["source_type"]) else str(last["source_type"])}


def climate_trace_sites(session: Session) -> dict:
    """{sites: [...], counts: {...}} — every Climate TRACE source whose ownership chain names an issuer's LEI, with its
    coordinates and facts; a source without coordinates is counted, never placed."""
    import pandas as pd
    leis = issuers_by_lei(session)
    iso2 = iso2_by_iso3(session)
    release = None
    sites, counts = [], defaultdict(int)
    for own_path in checked_files("climate_trace_assets", r"_emissions_sources_ownership_v\d+_\d+_\d+\.csv$"):
        sub, release = re.match(r"^(.+)_emissions_sources_ownership_(v\d+_\d+_\d+)\.csv$", own_path.name).groups()
        own = pd.read_csv(own_path, dtype=str)
        own = own[own["parent_lei"].str.upper().isin(leis)]
        if own.empty:
            continue
        ids = set(own["source_id"])
        src_path = own_path.with_name(f"{sub}_emissions_sources_{release}.csv")
        src = pd.concat(chunk[(chunk["source_id"].isin(ids)) & (chunk["gas"] == GAS)]
                        for chunk in pd.read_csv(src_path, dtype=str, chunksize=500_000))
        by_source = {k: g for k, g in src.groupby("source_id")}
        for r in own.itertuples(index=False):
            g = by_source.get(r.source_id)
            lat = lon = None
            if g is not None:
                la, lo = pd.to_numeric(g["lat"], errors="coerce").dropna(), pd.to_numeric(g["lon"], errors="coerce").dropna()
                lat, lon = (float(la.iloc[-1]), float(lo.iloc[-1])) if len(la) and len(lo) else (None, None)
            if lat is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                counts["no_coordinates"] += 1
                continue
            for issuer_id in leis[r.parent_lei.upper()]:
                sites.append({
                    "issuer_id": issuer_id, "source": "climate_trace", "source_ref": f"climate_trace:{r.source_id}",
                    "name": (r.source_name or f"Climate TRACE source {r.source_id}")[:200], "facility_type": sub[:40],
                    "latitude": lat, "longitude": lon, "country": iso2.get(str(r.iso3_country)),
                    "owner_share": _share(r.overall_share_percent), "match_basis": "register_lei",
                    "site_facts": {"register": "Climate TRACE", "release": release.replace("_", "."),
                                   "source_id": r.source_id, "subsector": sub, "owner_named": r.parent_name,
                                   "owner_lei": r.parent_lei.upper(), "ownership_path": r.ownership_path,
                                   "owner_share_percent": None if pd.isna(r.overall_share_percent)
                                   else r.overall_share_percent,
                                   "operator": None if pd.isna(r.source_operator) else r.source_operator,
                                   **_year_facts(g)}})
                counts[sub] += 1
    return {"sites": sites, "counts": dict(counts), "release": release}


def record(session: Session, sites: Iterable[dict]) -> dict:
    """Write register sites as issuer facilities — weight not stated (0) — skipping one already held for the same
    issuer, register and register id. Returns {added, held, cells: {h3 cell: (lat, lon)} of the added sites}."""
    import h3
    added, held, cells = 0, 0, {}
    for s in sites:
        cell = h3.latlng_to_cell(s["latitude"], s["longitude"], H3_RESOLUTION)
        got = session.execute(text("""
            INSERT INTO issuer_facilities (issuer_id, name, facility_type, latitude, longitude, h3_cell, country,
                                           materiality_weight, weight_basis, source, source_ref, match_basis,
                                           owner_share, site_facts)
            VALUES (CAST(:issuer_id AS uuid), :name, :facility_type, :latitude, :longitude, :cell, :country, 0,
                    :basis, :source, :source_ref, :match_basis, :owner_share, CAST(:facts AS jsonb))
            ON CONFLICT (issuer_id, source, source_ref) WHERE match_basis IS NOT NULL DO NOTHING
            RETURNING facility_id"""),
            {**s, "cell": cell, "basis": NOT_STATED, "facts": json.dumps(s["site_facts"])}).first()
        if got:
            added += 1
            cells[cell] = (s["latitude"], s["longitude"])
        else:
            held += 1
    return {"added": added, "held": held, "cells": cells}

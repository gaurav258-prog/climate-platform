"""Shared ingestion core for the banking loan book.

ONE implementation of "rows → located, stored, scored assets", called by BOTH input surfaces:
  * the CSV upload  (api/routers/bank.py, JWT session), and
  * the direct-integration API (api/routers/ingest.py, ingest token).

Keeping it here means the validation gate, the H3 geocoding, the golden-source scoring, and the honesty
rules (skip a bad row with a reason; never silently default a missing field) are identical however the data
arrives — no parallel pipeline to drift. Callers own their own audit entry (the actor differs: a user vs a
token).
"""
from __future__ import annotations

import uuid
from typing import Iterable

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.scoring.on_demand import process_new_cells

# Mirrors bank.py ASSET_TEMPLATE_FIELDS required set — the fields a loan-tape row must carry.
BANK_REQUIRED = ["asset_name", "asset_type", "latitude", "longitude", "appraised_value_eur", "sector"]
_SAFEGUARDS = {"compliant", "non_compliant"}


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _str(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def ingest_bank_assets(session: Session, org_id: str, rows: Iterable[dict]) -> dict:
    """Land loan-tape rows into portfolio_entities + ext_banking, then score the new H3 cells against the
    golden source (process_new_cells) — the same path an any-address lookup takes. Returns a coverage-style
    result: how many landed, how many were skipped, and why (a sample), plus the scoring summary. A row
    missing a required field or with an out-of-range coordinate is skipped with a reason, never fatal to the
    batch and never guessed."""
    records: list[dict] = []
    cell_coords: dict = {}
    skipped: list[dict] = []

    for idx, row in enumerate(rows):
        lat, lon, value = _num(row.get("latitude")), _num(row.get("longitude")), _num(row.get("appraised_value_eur"))
        name, atype, sector = _str(row.get("asset_name")), _str(row.get("asset_type")), _str(row.get("sector"))
        missing = [k for k, v in (("asset_name", name), ("asset_type", atype), ("sector", sector),
                                  ("latitude", lat), ("longitude", lon), ("appraised_value_eur", value)) if v is None]
        if missing:
            if len(skipped) < 25:
                skipped.append({"row": idx, "reason": "missing required field(s)", "fields": missing})
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            if len(skipped) < 25:
                skipped.append({"row": idx, "reason": "coordinate out of range", "fields": ["latitude", "longitude"]})
            continue

        cell = h3.latlng_to_cell(lat, lon, 8)
        cell_coords[cell] = (lat, lon)
        safeguards = (_str(row.get("minimum_safeguards_status")) or "").lower() or None
        if safeguards and safeguards not in _SAFEGUARDS:
            safeguards = None
        origination = _str(row.get("loan_origination_date"))
        records.append({
            "entity_id": str(uuid.uuid4()), "org_id": org_id,
            "entity_name": name, "entity_type": atype,
            "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": _str(row.get("region")), "country": _str(row.get("country")),
            "primary_value_eur": value, "sector": sector,
            "outstanding_loan_balance_eur": _num(row.get("outstanding_loan_balance_eur")),
            "loan_origination_date": origination[:10] if origination else None,
            "borrower_entity_id": _str(row.get("borrower_entity_id")),
            "minimum_safeguards_status": safeguards,
            # No nace_code on intake yet, so EU Taxonomy classification can't run — honest "not_assessed".
            "taxonomy_status": "not_assessed",
        })

    if records:
        session.execute(text("""
            INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type, latitude, longitude,
                                             h3_cell, region, country, primary_value_eur, sector,
                                             borrower_entity_id, minimum_safeguards_status)
            VALUES (:entity_id, :org_id, 'banking', :entity_name, :entity_type, :latitude, :longitude,
                    :h3_cell, :region, :country, :primary_value_eur, :sector,
                    :borrower_entity_id, :minimum_safeguards_status)
        """), records)
        session.execute(text("""
            INSERT INTO ext_banking (entity_id, outstanding_loan_balance_eur, loan_origination_date, taxonomy_status)
            VALUES (:entity_id, :outstanding_loan_balance_eur, :loan_origination_date, :taxonomy_status)
        """), records)

    # Async scoring dispatch is best-effort: the rows are already stored and will be scored on demand when
    # viewed (the globe/any-address path warms them) or when a worker runs. A broker/scorer being down must
    # never fail — or roll back — a completed ingest.
    processing: dict = {}
    if cell_coords:
        try:
            processing = process_new_cells(cell_coords)
        except Exception as exc:  # noqa: BLE001 — deliberately broad; dispatch is fire-and-forget
            processing = {"scoring": "deferred", "n_cells": len(cell_coords),
                          "note": f"async scoring will run when available ({type(exc).__name__})"}
    return {"n_ingested": len(records), "n_skipped": len(skipped), "skipped": skipped, "processing": processing}

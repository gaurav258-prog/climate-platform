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

# Mirrors bank.py ASSET_TEMPLATE_FIELDS required set — the fields a loan-tape row must carry.
BANK_REQUIRED = ["asset_name", "asset_type", "latitude", "longitude", "appraised_value_eur", "sector", "counterparty_evic_eur"]
_SAFEGUARDS = {"compliant", "non_compliant"}
_GOVT_LEVELS = {"central", "regional", "local"}


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


def ingest_bank_assets(session: Session, org_id: str, rows: Iterable[dict],
                       reporting_entity_id: str | None = None, dispatch_scoring: bool = True) -> dict:
    """Land loan-tape rows into portfolio_entities + ext_banking, then score the new H3 cells against the
    golden source (process_new_cells) — the same path an any-address lookup takes. Returns a coverage-style
    result: how many landed, how many were skipped, and why (a sample), plus the scoring summary. A row
    missing a required field or with an out-of-range coordinate is skipped with a reason, never fatal to the
    batch and never guessed.

    reporting_entity_id: when the caller already knows which entity this WHOLE batch belongs to (e.g.
    uploading one subsidiary's own book separately, or a batch import doing one call per legal entity), pass
    it explicitly — every row in this call lands under it. Without it, the entity is auto-inferred only when
    the org happens to have exactly one non-group entity (default_reporting_entity); an org with a real
    multi-entity hierarchy has no way to infer which entity an unlabelled batch belongs to, so it stays
    honestly unassigned (reporting_entity_gap) rather than guessed."""
    from services.governance.entities import default_reporting_entity
    default_entity = reporting_entity_id or default_reporting_entity(session, org_id)

    records: list[dict] = []
    cell_coords: dict = {}
    skipped: list[dict] = []

    for idx, row in enumerate(rows):
        lat, lon, value = _num(row.get("latitude")), _num(row.get("longitude")), _num(row.get("appraised_value_eur"))
        name, atype, sector = _str(row.get("asset_name")), _str(row.get("asset_type")), _str(row.get("sector"))
        evic = _num(row.get("counterparty_evic_eur"))
        missing = [k for k, v in (("asset_name", name), ("asset_type", atype), ("sector", sector),
                                  ("latitude", lat), ("longitude", lon), ("appraised_value_eur", value),
                                  ("counterparty_evic_eur", evic)) if v is None]
        if missing:
            if len(skipped) < 25:
                skipped.append({"row": idx, "reason": "missing required field(s)", "fields": missing})
            continue
        if evic <= 0:
            if len(skipped) < 25:
                skipped.append({"row": idx, "reason": "counterparty_evic_eur must be a positive value",
                                "fields": ["counterparty_evic_eur"]})
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
        govt_level = (_str(row.get("counterparty_govt_level")) or "").lower() or None
        if govt_level and govt_level not in _GOVT_LEVELS:
            govt_level = None
        origination = _str(row.get("loan_origination_date"))
        records.append({
            "entity_id": str(uuid.uuid4()), "org_id": org_id,
            "reporting_entity_id": default_entity,
            "entity_name": name, "entity_type": atype,
            "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": _str(row.get("region")), "country": _str(row.get("country")),
            "primary_value_eur": value, "sector": sector,
            "outstanding_loan_balance_eur": _num(row.get("outstanding_loan_balance_eur")),
            "loan_origination_date": origination[:10] if origination else None,
            "counterparty_evic_eur": evic,
            "counterparty_govt_level": govt_level,
            "borrower_entity_id": _str(row.get("borrower_entity_id")),
            "minimum_safeguards_status": safeguards,
            # No nace_code on intake yet, so EU Taxonomy classification can't run — honest "not_assessed".
            "taxonomy_status": "not_assessed",
        })

    if records:
        session.execute(text("""
            INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type, latitude, longitude,
                                             h3_cell, region, country, primary_value_eur, sector,
                                             borrower_entity_id, minimum_safeguards_status, reporting_entity_id)
            VALUES (:entity_id, :org_id, 'banking', :entity_name, :entity_type, :latitude, :longitude,
                    :h3_cell, :region, :country, :primary_value_eur, :sector,
                    :borrower_entity_id, :minimum_safeguards_status, CAST(:reporting_entity_id AS uuid))
        """), records)
        session.execute(text("""
            INSERT INTO ext_banking (entity_id, outstanding_loan_balance_eur, loan_origination_date, taxonomy_status, counterparty_evic_eur, counterparty_govt_level)
            VALUES (:entity_id, :outstanding_loan_balance_eur, :loan_origination_date, :taxonomy_status, :counterparty_evic_eur, :counterparty_govt_level)
        """), records)

    # Async scoring dispatch is best-effort: the rows are already stored and will be scored on demand when
    # viewed (the globe/any-address path warms them) or when a worker runs. A broker/scorer being down must
    # never fail — or roll back — a completed ingest.
    processing: dict = {}
    if cell_coords and dispatch_scoring:
        try:   # never inside the request: raster and reanalysis reads run on the jobs layer (worker or child process)
            from services.tasks.jobs import submit
            processing = {"scoring": "queued", "n_cells": len(cell_coords), **submit("scoring.process_cells", cell_coords)}
        except Exception as exc:  # noqa: BLE001 — deliberately broad; dispatch is fire-and-forget
            processing = {"scoring": "deferred", "n_cells": len(cell_coords),
                          "note": f"async scoring will run when available ({type(exc).__name__})"}
    result = {"n_ingested": len(records), "n_skipped": len(skipped), "skipped": skipped, "processing": processing,
              "value_ingested": float(sum(r["primary_value_eur"] for r in records)), "cell_coords": cell_coords}
    if records and default_entity is None:
        # honest, not silent: these rows will show in the org-wide view but be invisible to any per-entity
        # or consolidated-group filing until an operator assigns them (multi-entity orgs have no unambiguous
        # default — see services.governance.entities.default_reporting_entity).
        result["reporting_entity_gap"] = (
            f"{len(records)} ingested asset(s) have no reporting entity assigned (this org has more than one "
            "legal entity/fund, so none could be inferred). They will appear in the org-wide book but not in "
            "any per-entity or consolidated-group filing until assigned via the entity hierarchy.")
    return result

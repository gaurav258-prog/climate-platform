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

from typing import Iterable

from sqlalchemy.orm import Session

from services.ingest.sector_ingest import BANK, RowIssue

# Mirrors ASSET_TEMPLATE_FIELDS' required set — the fields a loan-tape row must carry.
BANK_REQUIRED = ["asset_name", "asset_type", "latitude", "longitude", "appraised_value_eur", "sector", "counterparty_evic_eur"]


def ingest_bank_assets(session: Session, org_id: str, rows: Iterable[dict],
                       reporting_entity_id: str | None = None, dispatch_scoring: bool = True) -> dict:
    """Land loan-tape rows as NEW assets (seed scripts and tests; customer files go through services.intake.pipeline,
    which also matches rows to assets already held). Row rules are the intake pipeline's own (sector_ingest.BANK),
    so the two paths cannot drift. A row that cannot become an asset is skipped with a reason, never guessed.

    reporting_entity_id: when the caller already knows which entity this WHOLE batch belongs to, pass it — every row
    lands under it. Without it, the entity is inferred only when the org has exactly one non-group entity; a
    multi-entity org stays honestly unassigned (reporting_entity_gap) rather than guessed."""
    ctx = BANK.prepare(session, org_id)
    if reporting_entity_id:
        ctx["default_entity"] = reporting_entity_id
    records: list[dict] = []
    skipped: list[dict] = []
    n_skipped = 0
    for idx, row in enumerate(rows):
        try:
            records.append(BANK.build(ctx, row))
        except RowIssue as e:
            n_skipped += 1
            if len(skipped) < 25:
                skipped.append({"row": idx, "reason": str(e)})
    if records:
        BANK.insert(session, org_id, ctx, records)
    cell_coords = {r["h3_cell"]: (r["latitude"], r["longitude"]) for r in records}

    # Scoring dispatch is best-effort: the rows are stored and will be scored when viewed or when a worker runs.
    processing: dict = {}
    if cell_coords and dispatch_scoring:
        try:   # never inside the request: raster and reanalysis reads run on the jobs layer
            from services.tasks.jobs import submit
            processing = {"scoring": "queued", "n_cells": len(cell_coords), **submit("scoring.process_cells", cell_coords)}
        except Exception as exc:  # noqa: BLE001 — deliberately broad; dispatch is fire-and-forget
            processing = {"scoring": "deferred", "n_cells": len(cell_coords),
                          "note": f"async scoring will run when available ({type(exc).__name__})"}
    result = {"n_ingested": len(records), "n_skipped": n_skipped, "skipped": skipped, "processing": processing,
              "value_ingested": float(sum(r["primary_value_eur"] for r in records)), "cell_coords": cell_coords}
    if records and not ctx.get("default_entity"):
        result["reporting_entity_gap"] = (
            f"{len(records)} ingested asset(s) have no reporting entity assigned (this org has more than one "
            "legal entity/fund, so none could be inferred). They will appear in the org-wide book but not in "
            "any per-entity or consolidated-group filing until assigned via the entity hierarchy.")
    return result

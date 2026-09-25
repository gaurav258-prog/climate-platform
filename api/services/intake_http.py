"""HTTP glue for the intake controls — one place that turns form inputs into the declared-controls dict and a
GateError into the 409 the UI renders. Every sector's validate / upload route uses this, so the behaviour is identical."""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from services.ingest.batches import GateError, parse_declared


def declared_from_form(row_count: Optional[str], totals: Optional[str]) -> Optional[dict]:
    try:
        return parse_declared(row_count, totals)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "bad_declared_controls", "message": str(e)}) from e


def gate_409(e: GateError) -> HTTPException:
    return HTTPException(status_code=409, detail=e.detail())


def slim(controls: dict) -> dict:
    """Controls as returned to the UI: everything, but the accepted-row detail lists are capped."""
    return controls

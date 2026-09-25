"""HTTP glue for the intake pipeline — shared by every sector's validate / upload route and the API push, so the
behaviour (status codes, body shape) is identical everywhere."""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from services.ingest.batch_controls import (
    parse_money,  # noqa: F401 — (kept for callers that format declared totals)
)
from services.intake import pipeline


def declared_from_form(row_count: Optional[str], totals: Optional[str]) -> Optional[dict]:
    import json
    out: dict = {}
    if row_count not in (None, ""):
        try:
            out["row_count"] = int(row_count)
        except (TypeError, ValueError) as e:
            raise HTTPException(400, {"error": "bad_declared_controls", "message": "declared_row_count must be a whole number"}) from e
    if totals not in (None, ""):
        try:
            t = json.loads(totals)
        except ValueError as e:
            raise HTTPException(400, {"error": "bad_declared_controls",
                                      "message": 'declared_totals must be JSON like {"appraised_value_eur": 1250000000}'}) from e
        if not isinstance(t, dict):
            raise HTTPException(400, {"error": "bad_declared_controls", "message": "declared_totals must be an object of field → total"})
        out["control_totals"] = t
    return out or None


def preview(session: Session, org_id: str, template: str, raw: bytes, filename: Optional[str], declared: Optional[dict],
            mapping_profile_id: Optional[str] = None) -> dict:
    try:
        return pipeline.preview(session, org_id, template, raw, filename, declared, mapping_profile_id=mapping_profile_id or None)
    except pipeline.IntakeError as e:
        raise HTTPException(e.status, e.body) from e


def submit(session: Session, org_id: str, template: str, raw: bytes, filename: Optional[str], *, user_id: Optional[str] = None,
           token_id: Optional[str] = None, via: str = "upload", declared: Optional[dict] = None, reason: Optional[str] = None,
           mapping_profile_id: Optional[str] = None):
    """Runs the pipeline. A refusal that recorded evidence (a batch) is committed before the error is returned,
    so the rejected attempt stays on the ledger."""
    try:
        out = pipeline.submit(session, org_id, template, raw, filename, via=via, user_id=user_id, token_id=token_id,
                              declared=declared, reason=reason, mapping_profile_id=mapping_profile_id or None)
    except pipeline.IntakeError as e:
        if e.body.get("batch_id"):
            session.commit()
        raise HTTPException(e.status, e.body) from e
    status = out.pop("http_status")
    if status == 200:
        return out
    session.commit()
    return JSONResponse(status_code=status, content=jsonable(out))


def jsonable(o):
    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(o)

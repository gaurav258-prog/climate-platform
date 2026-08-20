"""Realized climate exposure — the observed events that have already crossed the org's own book.

The retrospective counterpart to the forward scores: real named storms + earthquakes (located books) or real
observed yield shocks (agri), matched to the institution's own assets. See services/intelligence/realized_
exposure.py. One endpoint, sector-dispatched off the caller's org type — every figure is an observed catalogue
event, nothing projected.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import DbSession, require_permission
from services.intelligence.realized_exposure import realized_exposure

router = APIRouter(prefix="/v1/realized-exposure", tags=["Realized exposure"])

# org type -> shared-engine vertical
_VERTICAL = {"bank": "banking", "insurer": "insurance", "reit": "realestate",
             "asset_manager": "assetmgmt", "manufacturer": "agri"}


@router.get("", summary="Real climate events that have already crossed this org's book (observed, not modelled)")
def get_realized_exposure(session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    org = ctx["org"]
    vertical = _VERTICAL.get(org.get("type"))
    if not vertical:
        return {"available": False, "reason": "unsupported_sector"}
    return {"org_id": org["org_id"], "sector": org["type"],
            **realized_exposure(session, org["org_id"], vertical)}

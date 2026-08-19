"""Platform metadata — the browsable data dictionary of the single golden model."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import DbSession, require_permission

router = APIRouter(prefix="/v1/meta", tags=["Meta"])


@router.get("/data-dictionary", summary="The single golden model — fields, source feeds, vintage, consumers")
def data_dictionary(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.data_dictionary import data_dictionary as _dd
    return _dd(session)

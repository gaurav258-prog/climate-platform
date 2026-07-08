"""Customer-facing calculation-method triggers -- see org_calc_settings
migration and services/calc_settings.py for what each switch means and its
default. Any authenticated user can see which method their org has chosen;
changing it is an admin-level config action (admin.roles.manage), same tier
as managing roles, since it changes what every disclosure/report shows."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.deps import DbSession, require_permission
from services.calc_settings import get_calc_settings, upsert_calc_settings

router = APIRouter(prefix="/v1/calc-settings", tags=["Calc settings"])


class CalcSettingsUpdate(BaseModel):
    severity_model: Optional[str] = Field(None, pattern="^(universal|peril_specific)$")
    assetmgmt_var_method: Optional[str] = Field(None, pattern="^(haircut|monte_carlo)$")
    insurance_return_period_model: Optional[str] = Field(None, pattern="^(fixed|peril_specific)$")


@router.get("", summary="This org's calculation-method choices (defaults if never configured)")
def get_settings(session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    return get_calc_settings(session, ctx["org"]["org_id"])


@router.patch("", summary="Change a calculation-method trigger (admin)")
def update_settings(body: CalcSettingsUpdate, session: DbSession,
                     ctx: dict = Depends(require_permission("admin.roles.manage"))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    return upsert_calc_settings(session, ctx["org"]["org_id"], updates, ctx["user"]["id"])

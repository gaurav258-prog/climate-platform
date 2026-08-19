"""Customer-facing calculation-method + interpretation settings — see services/calc_settings.py for what each
switch means and its default. Any authenticated user can see which method/interpretation their org has chosen;
changing it is an admin-level config action (admin.roles.manage), routed through config governance (audited,
4-eyes if the org's approval matrix requires it), and the resolved settings are stamped onto every frozen
filing snapshot so a regulator sees which interpretation produced each number."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import DbSession, require_permission
from services.calc_settings import (
    INTERPRETATION_SCHEMA,
    get_calc_settings,
    interpretation_catalog,
    validate_interpretation,
)

router = APIRouter(prefix="/v1/calc-settings", tags=["Calc settings"])


class CalcSettingsUpdate(BaseModel):
    # legacy typed methods
    severity_model: Optional[str] = Field(None, pattern="^(universal|peril_specific)$")
    assetmgmt_var_method: Optional[str] = Field(None, pattern="^(haircut|monte_carlo)$")
    insurance_return_period_model: Optional[str] = Field(None, pattern="^(fixed|peril_specific)$")
    # open-ended interpretation switches (validated against INTERPRETATION_SCHEMA)
    interpretation: Optional[dict[str, Any]] = None


@router.get("", summary="This org's calculation-method + interpretation choices (defaults if never configured)")
def get_settings(session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    return get_calc_settings(session, ctx["org"]["org_id"])


@router.get("/catalog", summary="The interpretation switches available (schema, defaults, allowed values)")
def catalog(ctx: dict = Depends(require_permission("modules.view"))):
    """The interpretation-switch catalog, scoped to the org's sector — each switch's label, description,
    default and allowed set, for the settings UI."""
    return {"interpretation": interpretation_catalog(ctx["org"].get("type"))}


@router.patch("", summary="Change a calculation method / interpretation (admin; audited, 4-eyes if required)")
def update_settings(body: CalcSettingsUpdate, session: DbSession,
                    ctx: dict = Depends(require_permission("admin.roles.manage"))):
    updates = {k: v for k, v in body.model_dump().items()
               if v is not None and k != "interpretation"}
    # merge + validate the interpretation switches up front (so a bad value fails before an approval is opened)
    for key, val in (body.interpretation or {}).items():
        if key not in INTERPRETATION_SCHEMA:
            raise HTTPException(422, {"error": "unknown_setting", "message": f"unknown interpretation setting '{key}'"})
        try:
            updates[key] = validate_interpretation(key, val)
        except ValueError as e:
            raise HTTPException(422, {"error": "invalid_value", "message": str(e)})
    if not updates:
        return {"status": "applied", "result": get_calc_settings(session, ctx["org"]["org_id"])}
    from services.governance.config_governance import submit_or_apply_config
    return submit_or_apply_config(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                                  request_type="config.calc_settings", updates=updates)

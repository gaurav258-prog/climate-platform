"""Lane 2 — provided datapoints: submit a value calculated on the customer/vendor side, see it reconciled
against Tellumen's own number, and attest it through 4-eyes before it lands in a filing."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import DbSession, require_permission
import services.governance.provided_data as P

router = APIRouter(prefix="/v1/provided", tags=["Provided data (Lane 2)"])


class SubmitBody(BaseModel):
    framework:     str
    datapoint_key: str
    value_num:     Optional[float] = None
    value_text:    Optional[str] = Field(None, max_length=4000)
    unit:          Optional[str] = Field(None, max_length=40)
    source:        str = "client"
    provider_name: Optional[str] = Field(None, max_length=120)
    data_vintage:  Optional[str] = None          # ISO date
    period_label:  Optional[str] = Field(None, max_length=40)


@router.get("/catalog", summary="Datapoints a customer/vendor can provide for a framework")
def catalog(framework: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"framework": framework, "datapoints": P.providable(framework)}


@router.get("", summary="Provided values with their reconciliation + attestation status")
def list_provided(session: DbSession, framework: Optional[str] = None,
                  ctx: dict = Depends(require_permission("reports.view"))):
    return {"provided": P.provided_list(session, ctx["org"]["org_id"], framework)}


@router.post("", status_code=201, summary="Submit a provided value (raises a 4-eyes attest request)")
def submit(body: SubmitBody, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        return P.submit(session, ctx["org"]["org_id"], ctx["user"]["id"], framework=body.framework,
                        datapoint_key=body.datapoint_key, value_num=body.value_num, value_text=body.value_text,
                        unit=body.unit, source=body.source, provider_name=body.provider_name,
                        data_vintage=body.data_vintage, period_label=body.period_label)
    except P.ProvidedError as e:
        raise HTTPException(400, {"error": "bad_request", "message": str(e)})

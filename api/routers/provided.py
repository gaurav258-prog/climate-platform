"""Lane 2 — provided datapoints: submit a value calculated on the customer/vendor side, see it reconciled
against Tellumen's own number, and attest it through 4-eyes before it lands in a filing."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import services.governance.provided_data as P
from api.deps import DbSession, require_permission

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
    reporting_period_end: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")  # the period the value is for (ISO date)
    reporting_entity_id: Optional[str] = None     # the undertaking it is stated for (Solvency II); None = the organisation
    restatement_reason: Optional[str] = Field(None, max_length=2000)   # required once the period is closed
    currency: Optional[str] = Field(None, min_length=3, max_length=3)  # an ESRS amount: the currency it is stated in
    breakdown_member: Optional[str] = Field(None, max_length=120)      # an ESRS breakdown: which member (e.g. Scope 3 category '1')


@router.get("/catalog", summary="Datapoints a customer/vendor can provide for a framework")
def catalog(framework: str, session: DbSession, period_end: Optional[str] = None,
            ctx: dict = Depends(require_permission("reports.view"))):
    """For ESRS (framework=esrs) the figures depend on the version governing the financial year: give period_end."""
    if framework == P.ESRS:
        if not period_end:
            raise HTTPException(400, {"error": "bad_request", "message": "ESRS figures depend on the financial year: give period_end"})
        try:
            return {"framework": framework, **P.esrs_providable(session, ctx["org"]["org_id"], period_end)}
        except P.ProvidedError as e:
            raise HTTPException(400, {"error": "bad_request", "message": str(e)})
    if framework == P.METHOD:
        return {"framework": framework, **P.method_providable()}
    return {"framework": framework, "datapoints": P.providable(framework)}


@router.get("/method/needed", summary="The stated-method parameters the organisation's current figures still need")
def method_needed(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    """Runs the organisation's own figures on its basis and returns what they asked for and did not find, as attested
    for the reporting period (services.money.params.Method.record) — the list that turns a gap into a figure."""
    from services.governance.reporting_settings import get_settings
    org_id, org_type = ctx["org"]["org_id"], ctx["org"].get("type")
    s = get_settings(session, org_id)
    builders = {"bank": "api.routers.bank", "reit": "api.routers.realestate", "insurer": "api.routers.insurance",
                "asset_manager": "api.routers.assetmgmt"}
    if org_type in builders:
        import importlib
        rec = importlib.import_module(builders[org_type]).build_disclosure_snapshot(
            session, org_id, s["scenario"], s["horizon"])["method"]
    else:
        from services.money.params import for_org
        m = for_org(session, org_id)
        if org_type == "manufacturer":
            from services.intelligence.company_sites import list_sites_with_risk
            from services.intelligence.site_interruption import sites_bi
            sites_bi(m, list_sites_with_risk(session, org_id, s["scenario"], s["horizon"]))
            m.get("method.reallocation_cap")
        m.get("method.at_risk_level")
        rec = m.record()
    return {"period_end": rec["period_end"], "basis": {"scenario": s["scenario"], "horizon": s["horizon"]},
            "needed": rec["gaps"], "used": [u for u in rec["used"] if u]}


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
                        data_vintage=body.data_vintage, period_label=body.period_label,
                        reporting_period_end=body.reporting_period_end, reporting_entity_id=body.reporting_entity_id,
                        restatement_reason=body.restatement_reason, currency=body.currency,
                        breakdown_member=body.breakdown_member)
    except P.ProvidedError as e:
        raise HTTPException(400, {"error": "bad_request", "message": str(e)})

"""Crop calibrations — the platform operators' review of calibration runs before they publish (E162).

The calibration pipeline records every run of every recipe; the runs that would change a publication are proposed as
one batch (an approval request in the platform organisation, decided through the one approvals path,
POST /v1/approvals/{id}/decide). Every route needs calibration.review, a platform-operator permission.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import DbSession, require_permission
from api.services.rbac import write_audit
from services.calibration import review

router = APIRouter(prefix="/v1/ops/calibrations", tags=["Platform operator"])
_REVIEW = require_permission("calibration.review")


@router.get("", summary="Calibration batches awaiting a decision, and every recipe with its latest and published run")
def list_calibrations(session: DbSession, ctx: dict = Depends(_REVIEW)):
    from services.calibration.gates import protocol
    return {"pending": review.pending(session), "recipes": review.recipes(session), "protocol": protocol()}


@router.post("/run", summary="Re-run every active recipe off the request path; changes are proposed for review")
def run_all(session: DbSession, ctx: dict = Depends(_REVIEW)):
    from services.tasks.jobs import submit
    out = submit("calibration.run", None)
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="calibration.run",
                target_type="calibration_pipeline", target_id="all", detail={"via": out.get("via")})
    return {"submitted": True, "via": out.get("via")}

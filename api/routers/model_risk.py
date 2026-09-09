"""Model-risk register — model cards, the organisation's review record, exports."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from api.deps import DbSession, require_permission
from services.governance import model_risk as MR

router = APIRouter(prefix="/v1/model-risk", tags=["Governance"])


@router.get("", summary="The model-risk register: a card per model with its validation, governance and your review")
def get_register(session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    v = MR.view(session, ctx["org"]["org_id"], ctx["org"].get("type"))
    v["can_review"] = "reports.publish" in ctx["permissions"]
    return v


@router.get("/register.csv", summary="Export the register (for the auditor, the supervisor or the GRC suite)")
def export_csv(session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    v = MR.view(session, ctx["org"]["org_id"], ctx["org"].get("type"))
    return Response(content=MR.register_csv(v), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="model-risk-register.csv"'})


@router.get("/card.pdf", summary="One model card as PDF (pass ?ref=)")
def card_pdf(ref: str, session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    c = next((x for x in MR.cards(session, ctx["org"].get("type")) if x["ref"] == ref), None)
    if not c:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such model in the register."})
    pdf = MR.render_card_pdf(c, ctx["org"].get("name") or "", MR.history(session, ctx["org"]["org_id"], ref))
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="model-card-{c["hazard"]}-{c["name"][:40]}.pdf"'})


@router.get("/history", summary="Every review of one model by this organisation (pass ?ref=)")
def review_history(ref: str, session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    return {"reviews": MR.history(session, ctx["org"]["org_id"], ref)}


class Review(BaseModel):
    ref: str
    conclusion: str
    comment: Optional[str] = None
    next_review_by: Optional[date] = None


@router.post("/review", summary="Record an independent review of one model, bound to the card you saw")
def post_review(body: Review, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        out = MR.review(session, org_id=ctx["org"]["org_id"], org_type=ctx["org"].get("type"), model_ref=body.ref, actor=ctx["user"], conclusion=body.conclusion, comment=body.comment, next_review_by=body.next_review_by)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": "invalid", "message": str(e)})
    session.commit()
    return out

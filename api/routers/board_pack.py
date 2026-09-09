"""Board climate-risk pack — generate, read, download, attest (step-up)."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from api.deps import DbSession, require_permission, require_step_up
from services.governance import board_pack as BP

router = APIRouter(prefix="/v1/board-pack", tags=["Governance"])


def _regulated(ctx: dict) -> dict:
    if (ctx.get("org") or {}).get("type") == "regulator":
        raise HTTPException(status_code=404, detail={"error": "not_applicable", "message": "A supervisory body has no board climate-risk pack; use the population export."})
    return ctx


@router.get("", summary="Board climate-risk packs (versions, summaries, attestations)")
def list_packs(session: DbSession, ctx: dict = Depends(require_permission("oversight.view"))):
    _regulated(ctx)
    return {"packs": BP.list_packs(session, ctx["org"]["org_id"]), "statements": BP.STATEMENTS, "sections": BP.SECTIONS,
            "can_generate": "reports.publish" in ctx["permissions"], "can_attest": "board.attest" in ctx["permissions"]}


class PackCreate(BaseModel):
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    note: Optional[str] = None


@router.post("", status_code=201, summary="Generate a new, immutable board pack for a period")
def create_pack(body: PackCreate, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    _regulated(ctx)
    try:
        out = BP.create(session, org=ctx["org"], actor=ctx["user"], period_from=body.period_from, period_to=body.period_to, note=body.note)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": "invalid", "message": str(e)})
    session.commit()
    return out


@router.get("/{pack_id}.{fmt}", summary="Download the pack (PDF with the attestation record, or canonical JSON)")
# declared before the plain read: "{id}.pdf" would otherwise be read as an id
def download_pack(pack_id: str, fmt: str, session: DbSession, ctx: dict = Depends(require_permission("oversight.view"))):
    p = BP.get_pack(session, ctx["org"]["org_id"], pack_id)
    if not p:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such board pack."})
    stem = f"board-pack-v{p['version']}-{p['period_to']}"
    if fmt == "pdf":
        return Response(content=BP.render_pdf(p["content"], p["attestations"]), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{stem}.pdf"'})
    if fmt == "json":
        return Response(content=BP.canonical_json({**p["content"], "attestations": p["attestations"]}), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{stem}.json"'})
    raise HTTPException(status_code=422, detail={"error": "invalid", "message": "Format must be pdf or json."})


@router.get("/{pack_id}", summary="One board pack: its full content and attestations")
def get_pack(pack_id: str, session: DbSession, ctx: dict = Depends(require_permission("oversight.view"))):
    p = BP.get_pack(session, ctx["org"]["org_id"], pack_id)
    if not p:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such board pack."})
    return p


class Attest(BaseModel):
    capacity: str
    statement: str
    comment: Optional[str] = None


@router.post("/{pack_id}/attest", summary="Attest this pack by name, in a stated capacity (requires step-up re-authentication)")
def attest_pack(pack_id: str, body: Attest, request: Request, session: DbSession, ctx: dict = Depends(require_permission("board.attest")), _su: dict = Depends(require_step_up)):
    fwd = request.headers.get("x-forwarded-for")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)
    try:
        out = BP.attest(session, org_id=ctx["org"]["org_id"], pack_id=pack_id, actor=ctx["user"], capacity=body.capacity, statement=body.statement, comment=body.comment, ip=ip)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": "invalid", "message": str(e)})
    session.commit()
    return out

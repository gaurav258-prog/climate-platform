"""European ESG Template (EET) — share classes, the manager's answers, and versions a second person approves.

    GET    /v1/eet/fields                      the FinDatEx field list (search, requirement per use, who fills it)
    GET    /v1/funds/{fund_id}/share-classes   a fund's share classes          POST  … add one
    PATCH  /v1/share-classes/{id}              edit / close a share class      GET   /v1/share-classes/resolve?isin=
    GET    /v1/eet/answers?fund_id=            the manager's answers           PUT   … save answers (checked)
    GET    /v1/eet/draft?uses=                 what a file would hold now + what is missing
    GET    /v1/eet/changes                     a fresh build vs the latest published version
    POST   /v1/eet/versions                    prepare the next version (needs a second person's approval)
    GET    /v1/eet/versions[/{id}]             versions · GET …/{id}/export?format=xlsx|csv  the EET file
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from api.deps import DbSession, require_permission
from api.services.rbac import write_audit
from services.eet import fields as F
from services.eet import publication as P
from services.eet import share_classes as S
from services.eet.generator import build, computed_names

router = APIRouter(prefix="/v1", tags=["European ESG Template (EET)"])


def _err(e: Exception, code: str = "eet_error", status: int = 422):
    raise HTTPException(status, {"error": code, "message": str(e)})


def _uses(uses: str) -> tuple[str, ...]:
    got = tuple(u.strip() for u in (uses or "").split(",") if u.strip())
    bad = [u for u in got if u not in F.USES]
    if bad or not got:
        _err(ValueError(f"uses must be one or more of: {', '.join(F.USES)}"), "bad_uses")
    return got


class ShareClassBody(BaseModel):
    isin: Optional[str] = None
    name: Optional[str] = None
    currency: Optional[str] = None
    hedged: Optional[bool] = None
    distribution: Optional[str] = None
    launch_date: Optional[str] = None
    status: Optional[str] = None


class AnswersBody(BaseModel):
    fund_id: Optional[str] = None
    values: dict[str, Optional[str]]


class PrepareBody(BaseModel):
    uses: list[str]
    note: Optional[str] = None


@router.get("/eet/fields", summary="The EET field list — requirement per use and who fills each field")
def eet_fields(q: str = Query("", max_length=100), uses: str = Query("entity"), only: str = Query("all"),
               _ctx: dict = Depends(require_permission("reports.view"))):
    use_t, computed, ql = _uses(uses), computed_names(), q.strip().lower()
    out = []
    for f in F.fields():
        level = F.requirement(f, use_t)
        if only == "required" and level not in ("M", "C"):
            continue
        if ql and ql not in f["name"].lower() and ql not in (f["definition"] or "").lower():
            continue
        allowed, multi = F.choices(f) if F.kind(f) == "choice" else (set(), False)
        out.append({"name": f["name"], "section": f["section"], "definition": f["definition"], "requirement": level,
                    "codification": (f["codification"] or "").split("\n")[0], "kind": F.kind(f),
                    "choices": sorted(allowed), "multi": multi, "filled_by": "tellumen" if f["name"] in computed else "manager",
                    "scope": "organisation" if int(f["code"]) < 20000 else "fund"})
    return {"eet_version": F.version(), "n": len(out), "fields": out[:700]}


@router.get("/funds/{fund_id}/share-classes", summary="A fund's share classes")
def share_classes(fund_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"share_classes": S.list_classes(session, ctx["org"]["org_id"], fund_id)}


@router.post("/funds/{fund_id}/share-classes", status_code=201, summary="Register a share class (ISIN, currency, hedged, distribution)")
def add_share_class(fund_id: str, body: ShareClassBody, session: DbSession,
                    ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        sc = S.create(session, ctx["org"]["org_id"], fund_id, body.model_dump(exclude_none=True), ctx["user"]["id"])
    except S.ShareClassError as e:
        _err(e, "share_class_error")
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="eet.share_class.create",
                target_type="fund_share_class", target_id=sc["share_class_id"], detail={"isin": sc["isin"], "fund_id": fund_id})
    session.commit()
    return sc


@router.patch("/share-classes/{share_class_id}", summary="Edit or close a share class")
def edit_share_class(share_class_id: str, body: ShareClassBody, session: DbSession,
                     ctx: dict = Depends(require_permission("reports.publish"))):
    changes = body.model_dump(exclude_none=True)
    try:
        sc = S.update(session, ctx["org"]["org_id"], share_class_id, changes, ctx["user"]["id"])
    except S.ShareClassError as e:
        _err(e, "share_class_error")
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="eet.share_class.update",
                target_type="fund_share_class", target_id=share_class_id, detail={"changes": changes})
    session.commit()
    return sc


@router.get("/share-classes/resolve", summary="Is this ISIN one of your share classes? → its fund")
def resolve(isin: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"isin": isin.strip().upper(), "valid": S.isin_valid(isin), "share_class": S.resolve_isin(session, ctx["org"]["org_id"], isin)}


@router.get("/eet/answers", summary="The manager's EET answers (organisation + fund)")
def get_answers(session: DbSession, fund_id: Optional[str] = None, ctx: dict = Depends(require_permission("reports.view"))):
    return P.answers(session, ctx["org"]["org_id"], fund_id)


@router.put("/eet/answers", summary="Save EET answers — each checked against its field's format")
def put_answers(body: AnswersBody, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        out = P.set_answers(session, ctx["org"]["org_id"], body.fund_id, body.values, ctx["user"]["id"])
    except P.EETError as e:
        _err(e)
    if out["saved"] or out["removed"]:
        write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="eet.answers.save",
                    target_type="fund" if body.fund_id else "organisation", target_id=body.fund_id,
                    detail={"saved": out["saved"], "removed": out["removed"]})
    session.commit()
    return out


@router.get("/eet/draft", summary="What an EET would hold now, and what is still missing")
def draft(session: DbSession, uses: str = Query("entity"), ctx: dict = Depends(require_permission("reports.view"))):
    out = build(session, ctx["org"]["org_id"], _uses(uses))
    return {**{k: out[k] for k in ("eet_version", "uses", "funds", "notes", "completeness")},
            "rows": [{"fund_id": r["fund_id"], "isin": r["isin"], "n_filled": len(r["values"]), "values": r["values"]}
                     for r in out["rows"]]}


@router.get("/eet/changes", summary="A fresh EET vs the latest published version")
def eet_changes(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return P.changes(session, ctx["org"]["org_id"])


@router.post("/eet/versions", status_code=201, summary="Prepare the next EET version (a second person must approve it)")
def prepare(body: PrepareBody, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        v = P.prepare(session, ctx["org"]["org_id"], ctx["user"]["id"], body.uses, body.note)
    except P.EETError as e:
        _err(e, "not_ready")
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="eet.version.prepare",
                target_type="eet_publication", target_id=v["publication_id"],
                detail={"version": v["version"], "uses": v["uses"], "sha256": v["payload_sha256"]})
    session.commit()
    return v


@router.get("/eet/versions", summary="EET versions — pending, published, rejected")
def versions(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"versions": P.list_versions(session, ctx["org"]["org_id"])}


@router.get("/eet/versions/{publication_id}", summary="One EET version (frozen rows, hash-verified)")
def version(publication_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    try:
        return P.get(session, ctx["org"]["org_id"], publication_id)
    except P.EETError as e:
        _err(e, "not_found", 404)


@router.get("/eet/versions/{publication_id}/export", summary="The EET file — xlsx or csv, from the frozen version")
def export(publication_id: str, session: DbSession, format: str = Query("xlsx"),
           ctx: dict = Depends(require_permission("reports.view"))):
    try:
        name, media, data = P.export(session, ctx["org"]["org_id"], publication_id, format)
    except P.EETError as e:
        _err(e, "export_error")
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="eet.version.export",
                target_type="eet_publication", target_id=publication_id, detail={"format": format})
    session.commit()
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})

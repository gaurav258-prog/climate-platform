"""Custom analytics views — user-defined saved parameter sets over the forward-looking exposure analytics.

A "custom view" stores ONLY PARAMETERS (scope × measure × scenario × horizon × group-by), never numbers:
every figure is recomputed live in the client from the golden-source disclosure, so a saved view can never
carry a stale or invented value and is always exploratory — never a frozen or filed figure. Private by
default; is_shared exposes it read-only to the rest of the org; only the creator can edit or delete it.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, require_permission

router = APIRouter(prefix="/v1/analytics", tags=["Analytics"])


class ViewBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    config: dict
    is_shared: bool = False
    is_pinned: bool = False


class ViewPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    config: Optional[dict] = None
    is_shared: Optional[bool] = None
    is_pinned: Optional[bool] = None


def _row(r) -> dict:
    d = dict(r)
    d["view_id"] = str(d["view_id"])
    d["created_by"] = str(d["created_by"])
    return d


@router.get("/views", summary="List saved custom views (your own + those shared in your org)")
def list_views(session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    org_id, uid = ctx["org"]["org_id"], ctx["user"]["id"]
    rows = session.execute(text("""
        SELECT view_id, name, config, is_shared, is_pinned, created_by, created_at, updated_at,
               (created_by = CAST(:u AS uuid)) AS is_owner
        FROM analytics_saved_view
        WHERE org_id = CAST(:o AS uuid) AND (created_by = CAST(:u AS uuid) OR is_shared = true)
        ORDER BY is_pinned DESC, updated_at DESC
    """), {"o": str(org_id), "u": str(uid)}).mappings().all()
    return {"views": [_row(r) for r in rows]}


@router.post("/views", status_code=201, summary="Save a custom view")
def create_view(body: ViewBody, session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    org_id, uid = ctx["org"]["org_id"], ctx["user"]["id"]
    # view_id / timestamps: generate the id here — the model's uuid default is ORM-side and never fires on a
    # raw INSERT, and the request DB carries no column default for it.
    row = session.execute(text("""
        INSERT INTO analytics_saved_view (view_id, org_id, created_by, name, config, is_shared, is_pinned)
        VALUES (CAST(:vid AS uuid), CAST(:o AS uuid), CAST(:u AS uuid), :n, CAST(:c AS jsonb), :sh, :pin)
        RETURNING view_id, name, config, is_shared, is_pinned, created_by, created_at, updated_at
    """), {"vid": str(uuid.uuid4()), "o": str(org_id), "u": str(uid), "n": body.name.strip(),
           "c": json.dumps(body.config), "sh": body.is_shared, "pin": body.is_pinned}).mappings().first()
    session.commit()
    return _row(row) | {"is_owner": True}


@router.patch("/views/{view_id}", summary="Rename / pin / share / update a view you own")
def patch_view(view_id: str, body: ViewPatch, session: DbSession,
               ctx: dict = Depends(require_permission("modules.view"))):
    org_id, uid = ctx["org"]["org_id"], ctx["user"]["id"]
    owned = session.execute(text("""
        SELECT 1 FROM analytics_saved_view
        WHERE view_id = CAST(:v AS uuid) AND org_id = CAST(:o AS uuid) AND created_by = CAST(:u AS uuid)
    """), {"v": view_id, "o": str(org_id), "u": str(uid)}).first()
    if not owned:
        raise HTTPException(404, {"error": "not_found", "message": "View not found, or not yours to edit."})
    sets, p = [], {"v": view_id}
    if body.name is not None:      sets.append("name = :n");                 p["n"] = body.name.strip()
    if body.config is not None:    sets.append("config = CAST(:c AS jsonb)"); p["c"] = json.dumps(body.config)
    if body.is_shared is not None: sets.append("is_shared = :sh");           p["sh"] = body.is_shared
    if body.is_pinned is not None: sets.append("is_pinned = :pin");          p["pin"] = body.is_pinned
    if sets:
        sets.append("updated_at = now()")
        session.execute(text(f"UPDATE analytics_saved_view SET {', '.join(sets)} WHERE view_id = CAST(:v AS uuid)"), p)
        session.commit()
    return {"ok": True}


@router.delete("/views/{view_id}", status_code=204, summary="Delete a view you own")
def delete_view(view_id: str, session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    org_id, uid = ctx["org"]["org_id"], ctx["user"]["id"]
    res = session.execute(text("""
        DELETE FROM analytics_saved_view
        WHERE view_id = CAST(:v AS uuid) AND org_id = CAST(:o AS uuid) AND created_by = CAST(:u AS uuid)
    """), {"v": view_id, "o": str(org_id), "u": str(uid)})
    session.commit()
    if res.rowcount == 0:
        raise HTTPException(404, {"error": "not_found", "message": "View not found, or not yours to delete."})

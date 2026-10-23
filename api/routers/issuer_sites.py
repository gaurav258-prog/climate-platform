"""Issuers' real sites from public registers — the platform operators' review (the product owner's decisions of
2026-10-23). Climate TRACE ties a site to an issuer by the owner LEI it states; the EEA's industrial register names the
parent company only by name, so each such site is proposed here and used only after an operator confirms it. Every
route needs reference.release_review, a platform-operator permission no customer role holds; every decision is audited.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, require_permission
from core.errors import UserError

router = APIRouter(prefix="/v1/ops/issuer-sites", tags=["Platform operator"])
_REVIEW = require_permission("reference.release_review")


@router.get("", summary="Register sites by source and the name matches waiting for a decision")
def summary(session: DbSession, status: str = Query("pending", pattern="^(pending|confirmed|rejected)$"),
            limit: int = Query(200, ge=1, le=1000), ctx: dict = Depends(_REVIEW)):
    sources = [dict(r) for r in session.execute(text("""
        SELECT source, match_basis, count(*) AS sites, count(DISTINCT issuer_id) AS issuers
        FROM issuer_facilities WHERE match_basis IS NOT NULL GROUP BY 1, 2 ORDER BY 1""")).mappings()]
    counts = {r[0]: r[1] for r in session.execute(text(
        "SELECT status, count(*) FROM issuer_site_candidates GROUP BY 1")).all()}
    rows = [dict(r) for r in session.execute(text("""
        SELECT c.candidate_id::text, c.issuer_id::text, i.name AS issuer_name, i.lei AS issuer_lei, c.register,
               c.register_ref, c.register_vintage, c.name, c.latitude, c.longitude, c.country, c.owner_named,
               c.matched_lei, c.matched_name, c.relation, c.rule, c.status, c.decided_at, c.note, c.site_facts,
               u.email AS decided_by
        FROM issuer_site_candidates c JOIN issuers i ON i.issuer_id = c.issuer_id
        LEFT JOIN users u ON u.user_id = c.decided_by
        WHERE c.status = :s ORDER BY i.name, c.owner_named, c.name LIMIT :n"""), {"s": status, "n": limit}).mappings()]
    return {"sources": sources, "counts": counts, "candidates": rows}


class Decision(BaseModel):
    confirm: bool
    note: Optional[str] = Field(None, max_length=2000)


@router.post("/candidates/{candidate_id}/decide", summary="Confirm or reject one proposed site (audited)")
def decide(candidate_id: UUID, body: Decision, session: DbSession, ctx: dict = Depends(_REVIEW)):
    from services.reference import register_matching as M
    try:
        out = M.decide(session, str(candidate_id), ctx["user"]["id"], ctx["org"]["org_id"], body.confirm, body.note)
    except M.DecisionError as e:
        raise UserError(e.code, **e.params) from e
    session.commit()
    scoring = None
    if out["cells"]:
        from services.tasks.jobs import submit
        scoring = submit("scoring.process_cells", out["cells"])
    return {**{k: v for k, v in out.items() if k != "cells"}, "scoring": scoring}

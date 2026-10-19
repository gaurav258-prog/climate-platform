"""Regulatory specifications API — the versioned template specs, what changed between them, and their sign-off."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import services.regspec as R
from api.deps import CurrentUser, DbSession, require_permission
from core.errors import UserError
from services.regspec import signoff as S

router = APIRouter(prefix="/v1/regspec", tags=["Regulatory specifications"])


def reader(ctx: CurrentUser) -> dict:
    """Who reads the register: an organisation's report users, and the platform operator who runs the change route and
    signs its specifications (platform.admin) — the change pipeline page is theirs."""
    if not {"reports.view", "platform.admin"} & set(ctx["permissions"]):
        raise UserError("error.forbidden")
    return ctx


class Sign(BaseModel):
    role: str
    sha256: str = Field(..., min_length=64, max_length=64)
    note: Optional[str] = Field(None, max_length=1000)
    sole_reviewer: bool = False            # the same person signs both roles, and says so


@router.get("", summary="Every template specification: act, dates, sign-off, coverage and what changed from the version before")
def overview(session: DbSession, ctx: dict = Depends(reader)):
    return {"specs": S.overview(session)}


@router.get("/{framework}/{version}", summary="One specification in full (templates, rows, columns, quoted instructions)")
def one(framework: str, version: str, session: DbSession, ctx: dict = Depends(reader)):
    try:
        spec = S._document(framework, version)
    except R.SpecError as e:
        raise UserError("regchange.spec.error.not_found") from e
    return {**{k: v for k, v in spec.items() if k != "_sha256"}, "sha256": spec["_sha256"],
            "signoff": S.status(session, framework, version)}


@router.post("/{framework}/{version}/sign", summary="Sign a specification as regulatory reviewer or engineer (platform operator; two different people)")
def sign(framework: str, version: str, body: Sign, session: DbSession, ctx: dict = Depends(require_permission("platform.admin"))):
    try:
        out = S.sign(session, framework, version, body.role, ctx["user"]["id"], body.sha256, body.note,
                     sole_reviewer=body.sole_reviewer)
    except S.SignoffError as e:
        raise UserError(e.code, **e.params) from e
    except R.SpecError as e:
        raise UserError("regchange.spec.error.not_found") from e
    session.commit()
    return out

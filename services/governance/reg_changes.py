"""Regulatory-change register — the 'change the bank' pipeline, spotted → shipped.

Tenancy: a change is either org-scoped (a tenant's own adaptation item) or platform-wide (org_id NULL,
seeded by the platform — a rule change that affects everyone). A tenant sees its own + platform-wide changes,
but may only mutate its OWN org-scoped ones — platform-wide rows are read-only to a tenant.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

STAGES = ["identified", "analysis", "scheduled", "in_dev", "testing", "released"]


class ChangeError(ValueError):
    pass


def _row(r) -> dict:
    return {"change_id": str(r["change_id"]), "title": r["title"], "framework": r["framework"],
            "summary": r["summary"], "citation": r["citation"], "stage": r["stage"], "owner": r["owner"],
            "impact": r["impact"], "effective_date": r["effective_date"].isoformat() if r["effective_date"] else None,
            "is_platform": r["org_id"] is None, "updated_at": r["updated_at"].isoformat()}


def board(session: Session, org_id: str) -> dict:
    """Changes grouped by stage — platform-wide + this org's, newest first per stage."""
    rows = session.execute(text("""
        SELECT change_id, org_id, title, framework, summary, citation, stage, owner, impact, effective_date, updated_at
        FROM regulatory_change WHERE org_id IS NULL OR org_id = :o
        ORDER BY stage, updated_at DESC
    """), {"o": org_id}).mappings().all()
    items = [_row(r) for r in rows]
    return {"stages": [{"key": s, "changes": [c for c in items if c["stage"] == s]} for s in STAGES],
            "summary": {"total": len(items), "released": sum(1 for c in items if c["stage"] == "released")}}


def create_change(session: Session, org_id: str, actor: str, *, title: str, framework: str | None = None,
                  summary: str | None = None, citation: str | None = None, owner: str = "platform",
                  impact: str | None = None, effective_date: str | None = None,
                  org_scoped: bool = True) -> dict:
    """Register a change. Org-scoped by default — a tenant endpoint never creates a platform-wide (NULL) row
    (those are seeded by the platform), so a tenant can't inject into the global feed."""
    if not (title or "").strip():
        raise ChangeError("a change needs a title")
    if owner not in ("platform", "tenant"):
        raise ChangeError("owner must be platform or tenant")
    cid = session.execute(text("""
        INSERT INTO regulatory_change (org_id, title, framework, summary, citation, owner, impact,
                                       effective_date, created_by)
        VALUES (:o, :t, :fw, :s, :c, :ow, :im, :ed, :u) RETURNING change_id
    """), {"o": (org_id if org_scoped else None), "t": title.strip(), "fw": framework, "s": summary,
           "c": citation, "ow": owner, "im": impact, "ed": effective_date, "u": actor}).scalar()
    return get_change(session, org_id, str(cid))


def get_change(session: Session, org_id: str, change_id: str) -> dict | None:
    """A change the caller may see: their own, or a platform-wide one."""
    r = session.execute(text("""
        SELECT change_id, org_id, title, framework, summary, citation, stage, owner, impact, effective_date, updated_at
        FROM regulatory_change WHERE change_id = :c AND (org_id = :o OR org_id IS NULL)
    """), {"c": change_id, "o": org_id}).mappings().first()
    return _row(r) if r else None


def advance(session: Session, org_id: str, change_id: str, stage: str) -> dict:
    """Advance a change's stage. Tenant-scoped: only the org's OWN changes — platform-wide (NULL) rows are
    read-only to a tenant, and another org's change is invisible."""
    if stage not in STAGES:
        raise ChangeError(f"unknown stage '{stage}'")
    r = session.execute(text(
        "UPDATE regulatory_change SET stage=:s WHERE change_id=:c AND org_id=:o RETURNING change_id"),
        {"s": stage, "c": change_id, "o": org_id}).first()
    if not r:
        raise ChangeError("change not found, or it is a platform-managed change you can't modify")
    return get_change(session, org_id, change_id)

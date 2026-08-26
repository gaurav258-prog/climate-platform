"""Customer-contracts vault — the org's signed agreements, role-gated and audited.

Contracts (MSA, DPA, SOW, order forms, NDA) are stored against the tenant as bytea (the regulatory_task_attachment
pattern) with their commercial metadata. Access is by RBAC: contracts.view to list/download, contracts.manage to
upload/replace/remove. The router gates on those and audits every download. Everything is org-scoped — a contract
can only ever be read or written within its own tenant.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

CONTRACT_TYPES = {"msa", "dpa", "sow", "order_form", "nda", "other"}
CONTRACT_STATUSES = {"active", "expired", "terminated", "draft"}
MAX_BYTES = 25 * 1024 * 1024   # 25 MB per contract


class ContractError(ValueError):
    """A contract operation was rejected (bad input, too large, not found)."""


def list_contracts(session: Session, org_id: str) -> list[dict]:
    """Metadata for the org's contracts (no file bytes), newest first."""
    rows = session.execute(text("""
        SELECT c.contract_id::text AS contract_id, c.title, c.counterparty, c.contract_type, c.status,
               c.signed_date, c.effective_date, c.expiry_date, c.filename, c.content_type, c.size_bytes,
               c.created_at, u.full_name AS uploaded_by, u.email AS uploaded_by_email
        FROM customer_contract c
        LEFT JOIN users u ON u.user_id = c.uploaded_by
        WHERE c.org_id = CAST(:o AS uuid)
        ORDER BY c.created_at DESC
    """), {"o": org_id}).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("signed_date", "effective_date", "expiry_date", "created_at"):
            d[k] = d[k].isoformat() if d[k] else None
        out.append(d)
    return out


def add_contract(session: Session, org_id: str, actor: str | None, *, title: str, filename: str,
                 content_type: str | None, data: bytes, counterparty: str | None = None,
                 contract_type: str = "other", status: str = "active", signed_date: str | None = None,
                 effective_date: str | None = None, expiry_date: str | None = None) -> dict:
    """Store one signed contract against the tenant. Returns its metadata."""
    title = (title or "").strip()
    if not title:
        raise ContractError("a contract needs a title")
    if not data:
        raise ContractError("the contract file is empty")
    if len(data) > MAX_BYTES:
        raise ContractError(f"file exceeds the {MAX_BYTES // (1024 * 1024)} MB limit")
    ctype = contract_type if contract_type in CONTRACT_TYPES else "other"
    st = status if status in CONTRACT_STATUSES else "active"
    cid = str(uuid.uuid4())
    session.execute(text("""
        INSERT INTO customer_contract (contract_id, org_id, title, counterparty, contract_type, status,
            signed_date, effective_date, expiry_date, filename, content_type, size_bytes, data, uploaded_by)
        VALUES (CAST(:id AS uuid), CAST(:o AS uuid), :t, :cp, :ct, :st,
            CAST(:sd AS date), CAST(:ed AS date), CAST(:xd AS date), :fn, :mime, :sz, :data, CAST(:by AS uuid))
    """), {"id": cid, "o": org_id, "t": title, "cp": (counterparty or None), "ct": ctype, "st": st,
           "sd": signed_date or None, "ed": effective_date or None, "xd": expiry_date or None,
           "fn": (filename or "contract").strip(), "mime": content_type, "sz": len(data), "data": data, "by": actor})
    session.commit()
    return {"contract_id": cid, "title": title, "filename": filename, "size_bytes": len(data),
            "contract_type": ctype, "status": st}


def get_contract_file(session: Session, org_id: str, contract_id: str) -> tuple[str, str | None, bytes] | None:
    """(filename, content_type, bytes) for one contract, scoped to the org. None if not found."""
    r = session.execute(text("""
        SELECT filename, content_type, data FROM customer_contract
        WHERE contract_id = CAST(:c AS uuid) AND org_id = CAST(:o AS uuid)
    """), {"c": contract_id, "o": org_id}).first()
    if not r:
        return None
    return r[0], r[1], bytes(r[2])


def delete_contract(session: Session, org_id: str, contract_id: str) -> bool:
    res = session.execute(text("DELETE FROM customer_contract WHERE contract_id = CAST(:c AS uuid) AND org_id = CAST(:o AS uuid)"),
                          {"c": contract_id, "o": org_id})
    session.commit()
    return bool(res.rowcount)

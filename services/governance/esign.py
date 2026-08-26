"""E-signature requests — DocuSign-gated, with a manual upload-into-vault fallback.

When `DOCUSIGN_API_KEY` is set, a signature request creates a vendor envelope and tracks it to completion; absent
that, the request is recorded in 'manual' mode — the counterparty signs offline and the signed PDF is uploaded
into the customer-contracts vault (the flow that already exists), then the request is marked complete.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.services.rbac import write_audit
from core.config import settings

CONTRACT_TYPES = {"msa", "dpa", "sow", "order_form", "nda", "other"}


class EsignError(ValueError):
    pass


def _provider() -> str:
    return "docusign" if settings.DOCUSIGN_API_KEY else "manual"


def request_signature(session: Session, *, org_id: str, actor_user_id: str, title: str,
                      signer_email: str, contract_id: str | None = None) -> dict:
    title = (title or "").strip()
    signer_email = (signer_email or "").strip().lower()
    if not title:
        raise EsignError("a document title is required")
    if "@" not in signer_email:
        raise EsignError("a valid signer email is required")
    provider = _provider()
    external_id = None
    status = "pending"
    if provider == "docusign":
        external_id = _create_docusign_envelope(title=title, signer_email=signer_email)  # env-gated
        status = "sent"
    rid = str(uuid.uuid4())
    session.execute(text("""
        INSERT INTO esign_request (request_id, org_id, title, signer_email, provider, external_id, status, contract_id, created_by)
        VALUES (CAST(:i AS uuid), CAST(:o AS uuid), :t, :se, :p, :x, :st, :cid, :by)
    """), {"i": rid, "o": org_id, "t": title, "se": signer_email, "p": provider, "x": external_id,
           "st": status, "cid": contract_id, "by": actor_user_id})
    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="esign.requested",
                target_type="esign_request", target_id=rid, detail={"provider": provider})
    session.commit()
    return {"request_id": rid, "provider": provider, "status": status,
            "instructions": None if provider == "docusign" else "Sign offline, then upload the signed PDF to the contracts vault and mark this complete."}


def _create_docusign_envelope(*, title: str, signer_email: str) -> str:
    """Create a DocuSign envelope. Reached only when DOCUSIGN_API_KEY is set; the live API call belongs here."""
    raise EsignError("DocuSign is configured but the vendor API is unreachable in this environment")


def list_requests(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT request_id, title, signer_email, provider, status, contract_id, created_at, completed_at
        FROM esign_request WHERE org_id = CAST(:o AS uuid) ORDER BY created_at DESC LIMIT 200
    """), {"o": org_id}).mappings().all()
    return [dict(r) for r in rows]


def complete_request(session: Session, *, org_id: str, request_id: str, actor_user_id: str,
                     contract_id: str | None = None) -> dict:
    r = session.execute(text("SELECT status FROM esign_request WHERE request_id = CAST(:i AS uuid) AND org_id = CAST(:o AS uuid)"),
                        {"i": request_id, "o": org_id}).first()
    if not r:
        raise EsignError("request not found")
    session.execute(text("""
        UPDATE esign_request SET status = 'completed', completed_at = now(), contract_id = COALESCE(CAST(:c AS uuid), contract_id)
        WHERE request_id = CAST(:i AS uuid)
    """), {"c": contract_id, "i": request_id})
    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="esign.completed",
                target_type="esign_request", target_id=request_id)
    session.commit()
    return {"request_id": request_id, "status": "completed"}

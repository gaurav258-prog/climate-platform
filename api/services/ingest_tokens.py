"""Tenant ingest tokens — service-account credentials for the direct-integration API.

A token authenticates a customer's *system* (their ERP / data pipeline) into their own tenant, so they can
push data without a human login. Org-scoped and attributed to the admin who created it. Distinct from:
  * user JWTs (a person's session), and
  * the legacy customer-scoped api_keys (the old scores API).

Format: tlm_live_<48hex>. Only the SHA-256 is stored; the raw token is returned exactly once at creation.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

PREFIX = "tlm_live_"


def _generate() -> tuple[str, str, str]:
    raw = f"{PREFIX}{os.urandom(24).hex()}"          # tlm_live_ + 48 hex
    return raw, hashlib.sha256(raw.encode()).hexdigest(), raw[:16]


def create_token(session: Session, org_id: str, name: str, created_by_user_id: str,
                 expires_at: Optional[datetime] = None) -> dict:
    """Create a token for an org. Returns metadata + the raw token (shown ONCE)."""
    raw, token_hash, prefix = _generate()
    token_id = uuid.uuid4()
    session.execute(text("""
        INSERT INTO ingest_tokens (token_id, org_id, created_by_user_id, name, token_hash, token_prefix)
        VALUES (:t, :o, :u, :n, :h, :p)
    """), {"t": str(token_id), "o": org_id, "u": created_by_user_id, "n": name, "h": token_hash, "p": prefix})
    return {"token_id": str(token_id), "name": name, "token_prefix": prefix, "raw_token": raw,
            "created_at": datetime.now(timezone.utc).isoformat()}


def validate_token(session: Session, raw: str) -> Optional[dict]:
    """Validate a raw token → {org_id, token_id, org_type, org_name} if active & unexpired, else None.
    Bumps last_used_at (best-effort). Never raises on a bad token — a bad token is simply 'no match'."""
    if not raw or not raw.startswith(PREFIX):
        return None
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = session.execute(text("""
        SELECT it.token_id, it.org_id, it.is_active, it.expires_at, o.type AS org_type, o.name AS org_name
        FROM   ingest_tokens it JOIN organizations o ON o.org_id = it.org_id
        WHERE  it.token_hash = :h
    """), {"h": token_hash}).mappings().first()
    if not row or not row["is_active"]:
        return None
    if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
        return None
    try:
        session.execute(text("UPDATE ingest_tokens SET last_used_at = now() WHERE token_id = :t"),
                        {"t": str(row["token_id"])})
    except Exception:
        pass
    return {"org_id": str(row["org_id"]), "token_id": str(row["token_id"]),
            "org_type": row["org_type"], "org_name": row["org_name"]}


def list_tokens(session: Session, org_id: str) -> list[dict]:
    """All tokens for an org (never the hash or raw). Includes revoked ones for the audit trail."""
    rows = session.execute(text("""
        SELECT it.token_id, it.name, it.token_prefix, it.is_active, it.created_at, it.last_used_at,
               it.expires_at, u.email AS created_by_email
        FROM   ingest_tokens it LEFT JOIN users u ON u.user_id = it.created_by_user_id
        WHERE  it.org_id = :o ORDER BY it.created_at DESC
    """), {"o": org_id}).mappings().all()
    return [{
        "token_id": str(r["token_id"]), "name": r["name"], "token_prefix": r["token_prefix"],
        "is_active": r["is_active"], "created_by_email": r["created_by_email"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
        "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
    } for r in rows]


def revoke_token(session: Session, token_id: str, org_id: str) -> bool:
    """Deactivate a token. org_id scopes it so no tenant can revoke another's token."""
    res = session.execute(text("""
        UPDATE ingest_tokens SET is_active = false
        WHERE token_id = :t AND org_id = :o AND is_active = true
    """), {"t": token_id, "o": org_id})
    return res.rowcount > 0

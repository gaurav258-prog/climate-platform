"""
API key authentication service.

Key lifecycle:
  1. POST /v1/auth/keys  — create key, returns raw key ONCE (cp_live_<32hex>)
  2. Authorization: Bearer <raw_key> on every request
  3. Middleware hashes incoming key, looks up key_hash in api_keys table
  4. Returns customer_id from matched row

Key format:  cp_live_<32 lowercase hex chars>   (total length = 40 chars)
Stored:      SHA-256(raw_key) in key_hash column — raw key never persisted
Prefix:      first 12 chars shown on list endpoints for identification
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


# ── Key generation ─────────────────────────────────────────────────────

def generate_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns (raw_key, key_hash, key_prefix):
      raw_key    — shown to the user once, never stored
      key_hash   — SHA-256 of raw_key, stored in DB
      key_prefix — first 12 chars, stored for display
    """
    token    = os.urandom(16).hex()          # 32 hex chars
    raw_key  = f"cp_live_{token}"            # cp_live_<32hex>
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    prefix   = raw_key[:12]                  # "cp_live_xxxx"
    return raw_key, key_hash, prefix


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ── DB operations ──────────────────────────────────────────────────────

def create_api_key(
    session: Session,
    customer_id: str,
    name: str,
    expires_at: Optional[datetime] = None,
) -> dict:
    """
    Create and persist a new API key for customer_id.

    Returns dict with key metadata + raw_key (shown once).
    """
    raw_key, key_hash, prefix = generate_key()
    key_id = uuid.uuid4()
    now    = datetime.now(timezone.utc)

    session.execute(text("""
        INSERT INTO api_keys
            (key_id, customer_id, key_hash, key_prefix, name,
             is_active, created_at, expires_at)
        VALUES
            (:key_id, :customer_id, :key_hash, :key_prefix, :name,
             true, :created_at, :expires_at)
    """), {
        "key_id":      str(key_id),
        "customer_id": str(customer_id),
        "key_hash":    key_hash,
        "key_prefix":  prefix,
        "name":        name,
        "created_at":  now,
        "expires_at":  expires_at,
    })

    return {
        "key_id":      str(key_id),
        "customer_id": str(customer_id),
        "name":        name,
        "key_prefix":  prefix,
        "raw_key":     raw_key,   # returned ONCE — not stored
        "created_at":  now.isoformat(),
        "expires_at":  expires_at.isoformat() if expires_at else None,
    }


def validate_api_key(session: Session, raw_key: str) -> Optional[dict]:
    """
    Validate a raw API key.

    Returns {customer_id, key_id, name} if valid and active, else None.
    Updates last_used_at on success.
    """
    key_hash = hash_key(raw_key)
    now      = datetime.now(timezone.utc)

    row = session.execute(text("""
        SELECT key_id, customer_id, name, is_active, expires_at
        FROM   api_keys
        WHERE  key_hash = :key_hash
    """), {"key_hash": key_hash}).mappings().first()

    if not row:
        return None
    if not row["is_active"]:
        return None
    if row["expires_at"] and row["expires_at"] < now:
        return None

    # Bump last_used_at (best-effort — don't fail the request if this errors)
    try:
        session.execute(text("""
            UPDATE api_keys SET last_used_at = :now WHERE key_id = :key_id
        """), {"now": now, "key_id": str(row["key_id"])})
    except Exception:
        pass

    return {
        "customer_id": str(row["customer_id"]),
        "key_id":      str(row["key_id"]),
        "name":        row["name"],
    }


def revoke_api_key(session: Session, key_id: str, customer_id: str) -> bool:
    """
    Revoke a key. Returns True if a key was deactivated, False if not found.
    customer_id is required to prevent cross-customer revocation.
    """
    result = session.execute(text("""
        UPDATE api_keys
        SET    is_active = false
        WHERE  key_id = :key_id
          AND  customer_id = :customer_id
          AND  is_active = true
    """), {"key_id": key_id, "customer_id": str(customer_id)})
    return result.rowcount > 0


def list_api_keys(session: Session, customer_id: str) -> list[dict]:
    """List all active keys for a customer (no key_hash, no raw_key)."""
    rows = session.execute(text("""
        SELECT key_id, key_prefix, name, is_active, created_at, last_used_at, expires_at
        FROM   api_keys
        WHERE  customer_id = :customer_id
        ORDER  BY created_at DESC
    """), {"customer_id": str(customer_id)}).mappings().all()

    return [
        {
            "key_id":       str(r["key_id"]),
            "key_prefix":   r["key_prefix"],
            "name":         r["name"],
            "is_active":    r["is_active"],
            "created_at":   r["created_at"].isoformat() if r["created_at"] else None,
            "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
            "expires_at":   r["expires_at"].isoformat() if r["expires_at"] else None,
        }
        for r in rows
    ]

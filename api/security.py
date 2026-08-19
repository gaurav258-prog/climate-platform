"""
Password hashing (bcrypt) + JWT session tokens (PyJWT).

User login uses these primitives. This is deliberately separate from the machine
API-key service (api/auth.py): API keys are opaque `cp_live_...` strings hashed with
SHA-256; user sessions are short-lived signed JWTs. The two never collide — a JWT is
three dot-separated base64url segments and never starts with `cp_live_`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from core.config import settings

# ── Passwords ──────────────────────────────────────────────────────────

def hash_password(plaintext: str) -> str:
    """bcrypt hash (per-password salt). Store the returned string; never the plaintext."""
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plaintext: str, hashed: Optional[str]) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── JWT access tokens ──────────────────────────────────────────────────

def create_access_token(user_id: str, org_id: str, extra: Optional[dict] = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRATION_HOURS),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Return the claims dict, or None if the token is missing/invalid/expired."""
    if not token:
        return None
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def token_expires_in_seconds() -> int:
    return settings.JWT_EXPIRATION_HOURS * 3600

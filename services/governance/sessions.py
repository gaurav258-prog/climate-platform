"""Refresh-token sessions — rotating refresh tokens with reuse detection, and a per-session list.

A short-lived access JWT is paired with a long-lived refresh token (one DB row per active session). Refreshing
rotates the token: the old one is marked rotated and a new one issued. If a rotated/revoked token is ever
presented again, that's a theft signal — we revoke the user's entire session family and bump their token
version (invalidating outstanding access tokens too). This also powers "active sessions" + revoke-one.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.security import create_access_token
from core.config import settings


class SessionError(Exception):
    pass


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_version(session: Session, user_id: str) -> int:
    return session.execute(text("SELECT token_version FROM users WHERE user_id = CAST(:u AS uuid)"),
                           {"u": user_id}).scalar() or 0


def issue_refresh(session: Session, *, user_id: str, org_id: str, user_agent: str | None = None,
                  ip: str | None = None) -> str:
    raw = "rt_" + secrets.token_urlsafe(40)
    session.execute(text("""
        INSERT INTO refresh_token (token_id, user_id, org_id, token_hash, status, user_agent, ip, expires_at)
        VALUES (CAST(:i AS uuid), CAST(:u AS uuid), CAST(:o AS uuid), :h, 'active', :ua, :ip, :exp)
    """), {"i": str(uuid.uuid4()), "u": user_id, "o": org_id, "h": _hash(raw),
           "ua": (user_agent or "")[:400], "ip": ip, "exp": _now() + timedelta(days=settings.REFRESH_TOKEN_DAYS)})
    session.commit()
    return raw


def issue_pair(session: Session, *, user_id: str, org_id: str, user_agent: str | None = None,
               ip: str | None = None) -> dict:
    """Issue an access + refresh token pair (used at login / SSO)."""
    access = create_access_token(user_id=user_id, org_id=org_id, token_version=_token_version(session, user_id))
    refresh = issue_refresh(session, user_id=user_id, org_id=org_id, user_agent=user_agent, ip=ip)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer",
            "expires_in": settings.JWT_EXPIRATION_HOURS * 3600}


def rotate(session: Session, raw: str, *, user_agent: str | None = None, ip: str | None = None) -> dict:
    row = session.execute(text("SELECT * FROM refresh_token WHERE token_hash = :h"), {"h": _hash(raw)}).mappings().first()
    if not row:
        raise SessionError("invalid refresh token")
    if row["status"] != "active" or row["expires_at"] <= _now():
        # a rotated/revoked/expired token presented again → treat as reuse: nuke the whole family
        revoke_all(session, user_id=str(row["user_id"]))
        session.execute(text("UPDATE users SET token_version = token_version + 1 WHERE user_id = CAST(:u AS uuid)"),
                        {"u": str(row["user_id"])})
        session.commit()
        raise SessionError("refresh token reuse detected — all sessions revoked")
    new_raw = "rt_" + secrets.token_urlsafe(40)
    new_id = str(uuid.uuid4())
    session.execute(text("""
        INSERT INTO refresh_token (token_id, user_id, org_id, token_hash, status, user_agent, ip, expires_at)
        VALUES (CAST(:i AS uuid), :u, :o, :h, 'active', :ua, :ip, :exp)
    """), {"i": new_id, "u": row["user_id"], "o": row["org_id"], "h": _hash(new_raw),
           "ua": (user_agent or "")[:400], "ip": ip, "exp": _now() + timedelta(days=settings.REFRESH_TOKEN_DAYS)})
    session.execute(text("UPDATE refresh_token SET status = 'rotated', replaced_by = CAST(:nb AS uuid), last_used_at = now() WHERE token_id = :tid"),
                    {"nb": new_id, "tid": str(row["token_id"])})
    session.commit()
    access = create_access_token(user_id=str(row["user_id"]), org_id=str(row["org_id"]),
                                 token_version=_token_version(session, str(row["user_id"])))
    return {"access_token": access, "refresh_token": new_raw, "token_type": "bearer",
            "expires_in": settings.JWT_EXPIRATION_HOURS * 3600}


def list_sessions(session: Session, user_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT token_id, user_agent, ip, created_at, last_used_at FROM refresh_token
        WHERE user_id = CAST(:u AS uuid) AND status = 'active' AND expires_at > now()
        ORDER BY created_at DESC
    """), {"u": user_id}).mappings().all()
    return [dict(r) for r in rows]


def revoke_session(session: Session, *, user_id: str, token_id: str) -> bool:
    n = session.execute(text("""
        UPDATE refresh_token SET status = 'revoked' WHERE token_id = CAST(:t AS uuid) AND user_id = CAST(:u AS uuid) AND status = 'active'
    """), {"t": token_id, "u": user_id}).rowcount
    session.commit()
    return n > 0


def revoke_all(session: Session, *, user_id: str) -> int:
    n = session.execute(text("UPDATE refresh_token SET status = 'revoked' WHERE user_id = CAST(:u AS uuid) AND status = 'active'"),
                        {"u": user_id}).rowcount
    session.commit()
    return n

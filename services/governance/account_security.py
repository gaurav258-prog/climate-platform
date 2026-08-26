"""Account security — password reset, MFA recovery codes, admin MFA reset, session revocation, login lockout.

The self-service and administrative safety nets around authentication:
  • forgot-password → emailed reset link → set a new password (revokes existing sessions)
  • MFA backup codes (issued at enrolment, one-time) + an admin "reset this user's MFA"
  • revoke-all-sessions via a token version bumped on the user (stateless JWTs carry the version)
  • brute-force lockout helpers used by the authenticator
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.security import hash_password
from api.services.rbac import write_audit
from core.config import settings
from services.notifications.mailer import queue_email

RESET_TTL_HOURS = 2
LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15
N_BACKUP_CODES = 10


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── password reset ───────────────────────────────────────────────────────────
def request_password_reset(session: Session, email: str) -> dict:
    """Always returns ok (never reveals whether the email exists). Emails a reset link for a local account."""
    row = session.execute(text("""
        SELECT user_id, org_id, full_name, auth_provider FROM users
        WHERE lower(email) = lower(:e) AND status = 'active'
    """), {"e": (email or "").strip()}).mappings().first()
    if row and (row["auth_provider"] or "local") == "local":
        raw = secrets.token_urlsafe(32)
        session.execute(text("""
            INSERT INTO password_reset (reset_id, user_id, token_hash, status, expires_at)
            VALUES (CAST(:i AS uuid), CAST(:u AS uuid), :h, 'pending', :exp)
        """), {"i": str(uuid.uuid4()), "u": str(row["user_id"]), "h": _hash(raw),
               "exp": _now() + timedelta(hours=RESET_TTL_HOURS)})
        link = f"{settings.APP_BASE_URL.rstrip('/')}/reset/{raw}"
        queue_email(session, org_id=str(row["org_id"]), to_email=email.strip().lower(),
                    subject="Reset your Tellumen password",
                    html=(f"<p>We received a request to reset your password.</p>"
                          f"<p><a href='{link}'>Reset your password</a> — this link expires in {RESET_TTL_HOURS} hours.</p>"
                          f"<p>If you didn't request this, you can ignore this email.</p>"),
                    text_body=f"Reset your Tellumen password: {link} (expires in {RESET_TTL_HOURS}h)",
                    kind="password_reset")
        session.commit()
    return {"ok": True}


def get_reset(session: Session, token: str) -> dict | None:
    r = session.execute(text("""
        SELECT p.reset_id, u.email FROM password_reset p JOIN users u ON u.user_id = p.user_id
        WHERE p.token_hash = :h AND p.status = 'pending' AND p.expires_at > now()
    """), {"h": _hash(token)}).mappings().first()
    return {"email": r["email"]} if r else None


def complete_password_reset(session: Session, token: str, password: str) -> dict:
    r = session.execute(text("""
        SELECT p.reset_id, p.user_id, u.org_id FROM password_reset p JOIN users u ON u.user_id = p.user_id
        WHERE p.token_hash = :h AND p.status = 'pending' AND p.expires_at > now()
    """), {"h": _hash(token)}).mappings().first()
    if not r:
        raise ValueError("this reset link is invalid or has expired")
    if not password or len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    session.execute(text("""
        UPDATE users SET hashed_password = :pw, failed_login_count = 0, locked_until = NULL,
          token_version = token_version + 1 WHERE user_id = :u
    """), {"pw": hash_password(password), "u": str(r["user_id"])})
    session.execute(text("UPDATE password_reset SET status = 'used', used_at = now() WHERE reset_id = :i"),
                    {"i": str(r["reset_id"])})
    write_audit(session, org_id=str(r["org_id"]), actor_user_id=str(r["user_id"]),
                action="account.password_reset", target_type="user", target_id=str(r["user_id"]))
    session.commit()
    return {"ok": True}


# ── MFA backup codes ─────────────────────────────────────────────────────────
def generate_backup_codes(session: Session, user_id: str) -> list[str]:
    """Issue a fresh set of one-time recovery codes (shown once), replacing any prior set."""
    session.execute(text("DELETE FROM mfa_backup_code WHERE user_id = CAST(:u AS uuid)"), {"u": user_id})
    codes = []
    for _ in range(N_BACKUP_CODES):
        code = "-".join(secrets.token_hex(2) for _ in range(2))  # e.g. 3f9a-1c04
        codes.append(code)
        session.execute(text("""
            INSERT INTO mfa_backup_code (code_id, user_id, code_hash) VALUES (CAST(:i AS uuid), CAST(:u AS uuid), :h)
        """), {"i": str(uuid.uuid4()), "u": user_id, "h": _hash(code)})
    session.commit()
    return codes


def consume_backup_code(session: Session, user_id: str, code: str) -> bool:
    r = session.execute(text("""
        SELECT code_id FROM mfa_backup_code WHERE user_id = CAST(:u AS uuid) AND code_hash = :h AND used_at IS NULL
    """), {"u": user_id, "h": _hash((code or "").strip().lower())}).first()
    if not r:
        return False
    session.execute(text("UPDATE mfa_backup_code SET used_at = now() WHERE code_id = :i"), {"i": str(r[0])})
    session.commit()
    return True


def admin_reset_mfa(session: Session, *, actor_user_id: str, org_id: str, user_id: str) -> dict:
    """Clear a user's MFA enrolment + backup codes so they re-enrol (help-desk recovery). Org-scoped."""
    r = session.execute(text("SELECT 1 FROM users WHERE user_id = CAST(:u AS uuid) AND org_id = CAST(:o AS uuid)"),
                        {"u": user_id, "o": org_id}).first()
    if not r:
        raise ValueError("user not found in this organization")
    session.execute(text("UPDATE users SET mfa_secret = NULL, mfa_enrolled_at = NULL WHERE user_id = CAST(:u AS uuid)"),
                    {"u": user_id})
    session.execute(text("DELETE FROM mfa_backup_code WHERE user_id = CAST(:u AS uuid)"), {"u": user_id})
    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="account.mfa_reset",
                target_type="user", target_id=user_id)
    session.commit()
    return {"ok": True}


# ── session revocation ───────────────────────────────────────────────────────
def revoke_all_sessions(session: Session, *, user_id: str, org_id: str) -> dict:
    """Invalidate every outstanding JWT for a user by bumping their token version."""
    v = session.execute(text("UPDATE users SET token_version = token_version + 1 WHERE user_id = CAST(:u AS uuid) RETURNING token_version"),
                        {"u": user_id}).scalar()
    write_audit(session, org_id=org_id, actor_user_id=user_id, action="account.sessions_revoked",
                target_type="user", target_id=user_id)
    session.commit()
    return {"token_version": v}

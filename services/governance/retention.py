"""Data-retention sweep — prune expired tokens, consumed challenges, delivered mail, and aged audit rows.

Housekeeping that keeps short-lived security artifacts from accumulating and enforces the configured audit
retention window. Safe to run repeatedly (idempotent deletes); intended for a scheduled worker or an on-demand
platform-operator action.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import settings


def cleanup(session: Session, *, audit_days: int | None = None) -> dict:
    audit_days = audit_days if audit_days is not None else settings.AUDIT_RETENTION_DAYS
    counts: dict[str, int] = {}

    def _run(name: str, sql: str, params: dict | None = None) -> None:
        counts[name] = session.execute(text(sql), params or {}).rowcount

    _run("password_reset", "DELETE FROM password_reset WHERE status <> 'pending' OR expires_at < now() - interval '1 day'")
    _run("user_activation", "DELETE FROM user_activation WHERE status <> 'pending' OR expires_at < now() - interval '1 day'")
    _run("webauthn_challenge", "DELETE FROM webauthn_challenge WHERE expires_at < now()")
    _run("saml_assertion_seen", "DELETE FROM saml_assertion_seen WHERE seen_at < now() - interval '7 days'")
    _run("refresh_token", "DELETE FROM refresh_token WHERE status <> 'active' AND created_at < now() - interval '30 days'")
    _run("email_outbox", "DELETE FROM email_outbox WHERE status = 'sent' AND sent_at < now() - interval '30 days'")
    _run("access_audit_log", "DELETE FROM access_audit_log WHERE created_at < now() - make_interval(days => :d)", {"d": audit_days})

    session.commit()
    return {"deleted": counts, "audit_retention_days": audit_days}

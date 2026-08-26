"""Account security — password reset, MFA backup codes, session revocation — against a real tenant, self-cleaning."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from api.security import hash_password, verify_password
from core.db.session import get_session
from services.governance import account_security as acct

ORG = "11111111-1111-4111-8111-111111111111"   # Meridian Bank (demo)


def _mk_user(s) -> tuple[str, str]:
    uid = str(uuid.uuid4())
    email = f"acct.{uuid.uuid4().hex[:8]}@sec-test.local"
    s.execute(text("""
        INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status, auth_provider, created_at)
        VALUES (CAST(:u AS uuid), CAST(:o AS uuid), :e, 'viewer', 'Acct Test', :pw, 'active', 'local', now())
    """), {"u": uid, "o": ORG, "e": email, "pw": hash_password("Initial!Pass1")})
    s.commit()
    return uid, email


def _cleanup(s, uid: str, email: str) -> None:
    s.execute(text("DELETE FROM mfa_backup_code WHERE user_id = CAST(:u AS uuid)"), {"u": uid})
    s.execute(text("DELETE FROM password_reset WHERE user_id = CAST(:u AS uuid)"), {"u": uid})
    s.execute(text("DELETE FROM email_outbox WHERE to_email = :e"), {"e": email})
    s.execute(text("DELETE FROM users WHERE user_id = CAST(:u AS uuid)"), {"u": uid})
    s.commit()


@pytest.mark.integration
def test_password_reset_revokes_sessions_and_sets_password():
    with get_session() as s:
        uid, email = _mk_user(s)
        try:
            v0 = s.execute(text("SELECT token_version FROM users WHERE user_id = CAST(:u AS uuid)"), {"u": uid}).scalar()
            acct.request_password_reset(s, email)
            # recover the raw token from the queued email link (token itself is only stored hashed)
            body = s.execute(text("SELECT body_text FROM email_outbox WHERE to_email = :e ORDER BY created_at DESC LIMIT 1"),
                             {"e": email}).scalar()
            token = body.split("/reset/")[1].split()[0].strip()
            assert acct.get_reset(s, token)["email"] == email
            acct.complete_password_reset(s, token, "Rotated!Pass99")
            row = s.execute(text("SELECT hashed_password, token_version FROM users WHERE user_id = CAST(:u AS uuid)"), {"u": uid}).mappings().first()
            assert verify_password("Rotated!Pass99", row["hashed_password"])
            assert row["token_version"] == v0 + 1                       # sessions revoked
            assert acct.get_reset(s, token) is None                     # token single-use
        finally:
            _cleanup(s, uid, email)


@pytest.mark.integration
def test_backup_codes_are_one_time():
    with get_session() as s:
        uid, email = _mk_user(s)
        try:
            codes = acct.generate_backup_codes(s, uid)
            assert len(codes) == 10 and len(set(codes)) == 10
            assert acct.consume_backup_code(s, uid, codes[0]) is True
            assert acct.consume_backup_code(s, uid, codes[0]) is False   # already used
            assert acct.consume_backup_code(s, uid, "0000-0000") is False
            # regenerating replaces the old set
            codes2 = acct.generate_backup_codes(s, uid)
            assert acct.consume_backup_code(s, uid, codes[1]) is False   # old set invalidated
            assert acct.consume_backup_code(s, uid, codes2[0]) is True
        finally:
            _cleanup(s, uid, email)


@pytest.mark.integration
def test_revoke_all_sessions_bumps_version():
    with get_session() as s:
        uid, email = _mk_user(s)
        try:
            v0 = s.execute(text("SELECT token_version FROM users WHERE user_id = CAST(:u AS uuid)"), {"u": uid}).scalar()
            out = acct.revoke_all_sessions(s, user_id=uid, org_id=ORG)
            assert out["token_version"] == v0 + 1
        finally:
            _cleanup(s, uid, email)

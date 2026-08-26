"""Refresh-token sessions — rotation, reuse detection, revoke — against a real tenant, self-cleaning."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from api.security import hash_password
from core.db.session import get_session
from services.governance import sessions as sess

ORG = "11111111-1111-4111-8111-111111111111"


def _mk(s):
    uid = str(uuid.uuid4()); email = f"sess.{uuid.uuid4().hex[:8]}@sec-test.local"
    s.execute(text("INSERT INTO users (user_id,org_id,email,role,full_name,hashed_password,status,auth_provider,created_at) "
                   "VALUES (CAST(:u AS uuid),CAST(:o AS uuid),:e,'viewer','S',:p,'active','local',now())"),
              {"u": uid, "o": ORG, "e": email, "p": hash_password("Init!Pass1")})
    s.commit(); return uid, email


def _clean(s, uid, email):
    s.execute(text("DELETE FROM refresh_token WHERE user_id = CAST(:u AS uuid)"), {"u": uid})
    s.execute(text("DELETE FROM users WHERE user_id = CAST(:u AS uuid)"), {"u": uid}); s.commit()


@pytest.mark.integration
def test_rotation_and_reuse_detection():
    with get_session() as s:
        uid, email = _mk(s)
        try:
            rt = sess.issue_refresh(s, user_id=uid, org_id=ORG)
            pair = sess.rotate(s, rt)
            assert pair["refresh_token"] != rt and pair["access_token"]
            # reusing the old (rotated) token trips reuse detection and revokes the family
            with pytest.raises(sess.SessionError):
                sess.rotate(s, rt)
            with pytest.raises(sess.SessionError):
                sess.rotate(s, pair["refresh_token"])   # new one revoked too
        finally:
            _clean(s, uid, email)


@pytest.mark.integration
def test_list_and_revoke_sessions():
    with get_session() as s:
        uid, email = _mk(s)
        try:
            sess.issue_refresh(s, user_id=uid, org_id=ORG)
            sess.issue_refresh(s, user_id=uid, org_id=ORG)
            rows = sess.list_sessions(s, uid)
            assert len(rows) == 2
            assert sess.revoke_session(s, user_id=uid, token_id=str(rows[0]["token_id"])) is True
            assert len(sess.list_sessions(s, uid)) == 1
            assert sess.revoke_all(s, user_id=uid) == 1
            assert sess.list_sessions(s, uid) == []
        finally:
            _clean(s, uid, email)

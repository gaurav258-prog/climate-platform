"""Passkey option/challenge flow + e-signature request lifecycle. Self-cleaning.

The full WebAuthn ceremony needs a real authenticator (device-gated, like SSO); here we verify the server issues
valid options with a stored challenge, and the e-sign request lifecycle in manual mode.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from api.security import hash_password
from core.db.session import get_session
from services.governance import esign as esign_svc
from services.governance import passkeys as pk

ORG = "11111111-1111-4111-8111-111111111111"


def _mk(s):
    uid = str(uuid.uuid4()); email = f"pk.{uuid.uuid4().hex[:8]}@sec-test.local"
    s.execute(text("INSERT INTO users (user_id,org_id,email,role,full_name,hashed_password,status,auth_provider,created_at) "
                   "VALUES (CAST(:u AS uuid),CAST(:o AS uuid),:e,'viewer','PK',:p,'active','local',now())"),
              {"u": uid, "o": ORG, "e": email, "p": hash_password("x")})
    s.commit(); return uid, email


@pytest.mark.integration
def test_passkey_registration_options_issue_a_challenge():
    with get_session() as s:
        uid, email = _mk(s)
        try:
            opts = pk.registration_options(s, user_id=uid, email=email, full_name="PK Tester")
            assert opts["challenge"] and opts["rp"]["id"] and opts["user"]["name"] == email
            stored = s.execute(text("SELECT challenge FROM webauthn_challenge WHERE ref = :r"), {"r": f"reg:{uid}"}).scalar()
            assert stored                                        # challenge persisted for verification
            # a user with no credential offers no authentication options
            assert pk.authentication_options(s, email) is None
        finally:
            s.execute(text("DELETE FROM webauthn_challenge WHERE ref = :r"), {"r": f"reg:{uid}"})
            s.execute(text("DELETE FROM users WHERE user_id = CAST(:u AS uuid)"), {"u": uid}); s.commit()


@pytest.mark.integration
def test_esign_request_lifecycle_manual_mode():
    with get_session() as s:
        rid = None
        try:
            r = esign_svc.request_signature(s, org_id=ORG, actor_user_id=None, title="MSA - Test",
                                            signer_email="legal@counterparty.test")
            rid = r["request_id"]
            assert r["provider"] == "manual" and r["status"] == "pending" and r["instructions"]
            assert any(x["request_id"] == uuid.UUID(rid) or str(x["request_id"]) == rid for x in esign_svc.list_requests(s, ORG))
            done = esign_svc.complete_request(s, org_id=ORG, request_id=rid, actor_user_id=None)
            assert done["status"] == "completed"
            with pytest.raises(esign_svc.EsignError):
                esign_svc.request_signature(s, org_id=ORG, actor_user_id=None, title="", signer_email="x@y.z")
        finally:
            if rid:
                s.execute(text("DELETE FROM esign_request WHERE request_id = CAST(:i AS uuid)"), {"i": rid}); s.commit()

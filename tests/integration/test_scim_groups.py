"""SCIM Groups → role mapping — membership grants/revokes the mapped role. Self-cleaning."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from api.security import hash_password
from core.db.session import get_session
from services.governance import scim as scim_svc

ORG = "11111111-1111-4111-8111-111111111111"   # Meridian Bank (demo) — has roles admin/analyst/approver/viewer


def _mk(s):
    uid = str(uuid.uuid4()); email = f"grp.{uuid.uuid4().hex[:8]}@sec-test.local"
    s.execute(text("INSERT INTO users (user_id,org_id,email,role,full_name,hashed_password,status,auth_provider,created_at) "
                   "VALUES (CAST(:u AS uuid),CAST(:o AS uuid),:e,'viewer','G',:p,'active','sso',now())"),
              {"u": uid, "o": ORG, "e": email, "p": hash_password("x")})
    s.commit(); return uid, email


def _has_role(s, uid, role):
    return s.execute(text("SELECT count(*) FROM user_roles ur JOIN roles r ON r.role_id=ur.role_id "
                          "WHERE ur.user_id=CAST(:u AS uuid) AND r.name=:r AND r.org_id=CAST(:o AS uuid)"),
                     {"u": uid, "r": role, "o": ORG}).scalar()


@pytest.mark.integration
def test_group_membership_maps_to_role():
    with get_session() as s:
        uid, email = _mk(s)
        gid = None
        try:
            g = scim_svc.create_group(s, ORG, {"displayName": "analyst", "members": [{"value": uid}]})
            gid = g["id"]
            assert g["mappedRole"] == "analyst"
            assert _has_role(s, uid, "analyst") == 1                       # granted on membership

            scim_svc.patch_group(s, ORG, gid, {"Operations": [{"op": "remove", "path": "members", "value": [{"value": uid}]}]})
            assert _has_role(s, uid, "analyst") == 0                       # revoked on removal

            scim_svc.patch_group(s, ORG, gid, {"Operations": [{"op": "add", "path": "members", "value": [{"value": uid}]}]})
            assert _has_role(s, uid, "analyst") == 1                       # re-granted

            with pytest.raises(scim_svc.ScimError):
                scim_svc.create_group(s, ORG, {"displayName": "analyst"})  # duplicate → 409
        finally:
            if gid:
                s.execute(text("DELETE FROM scim_group WHERE group_id = CAST(:g AS uuid)"), {"g": gid})
            s.execute(text("DELETE FROM user_roles WHERE user_id = CAST(:u AS uuid)"), {"u": uid})
            s.execute(text("DELETE FROM users WHERE user_id = CAST(:u AS uuid)"), {"u": uid})
            s.commit()

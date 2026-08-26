"""SCIM 2.0 provisioning — the IdP-driven create / update / deactivate flow, end to end against a real tenant.

Exercises the provisioning lifecycle Okta/Entra drives (create user → read → filter → PATCH-deactivate →
DELETE-deprovision) plus SCIM-token resolution, cleaning up the users it creates.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.governance import scim as scim_svc
from services.governance import sso as sso_svc

ORG = "11111111-1111-4111-8111-111111111111"   # Meridian Bank (demo)


def _operator(s) -> str:
    return str(s.execute(text("SELECT user_id FROM users WHERE org_id = :o LIMIT 1"), {"o": ORG}).scalar())


@pytest.mark.integration
def test_scim_provisioning_lifecycle():
    suffix = uuid.uuid4().hex[:8]
    email = f"scim.{suffix}@scim-test.local"
    created_id = None
    try:
        with get_session() as s:
            actor = _operator(s)

            # a SCIM token resolves back to its org (the IdP presents it as a bearer)
            issued = sso_svc.generate_scim_token(s, ORG, actor_user_id=actor)
            assert issued["scim_token"].startswith("scim_")
            assert sso_svc.org_for_scim_token(s, issued["scim_token"]) == ORG
            assert sso_svc.org_for_scim_token(s, "scim_not-a-real-token") is None

            # 1. IdP creates a user
            created = scim_svc.create_user(s, ORG, {
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
                "userName": email, "externalId": f"idp-{suffix}",
                "name": {"givenName": "Scim", "familyName": "Tester"}, "active": True,
            })
            created_id = created["id"]
            assert created["active"] is True and created["userName"] == email

            # the user landed as an active, password-less SSO account
            row = s.execute(text("SELECT status, auth_provider, hashed_password FROM users WHERE user_id = CAST(:u AS uuid)"),
                            {"u": created_id}).mappings().first()
            assert row["status"] == "active" and row["auth_provider"] == "sso" and row["hashed_password"] is None

            # 2. duplicate create → SCIM 409
            with pytest.raises(scim_svc.ScimError) as ei:
                scim_svc.create_user(s, ORG, {"userName": email})
            assert ei.value.status == 409

            # 3. read + filter (the existence probe IdPs run before create)
            assert scim_svc.get_user(s, ORG, created_id)["id"] == created_id
            listed = scim_svc.list_users(s, ORG, filter_=f'userName eq "{email}"')
            assert listed["totalResults"] == 1 and listed["Resources"][0]["id"] == created_id

            # 4. PATCH deactivation (how Entra/Okta disable a leaver)
            patched = scim_svc.patch_user(s, ORG, created_id, {
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "replace", "path": "active", "value": False}],
            })
            assert patched["active"] is False
            assert s.execute(text("SELECT status FROM users WHERE user_id = CAST(:u AS uuid)"), {"u": created_id}).scalar() == "disabled"

            # 5. DELETE deprovision (soft-disable, preserves the audit trail)
            scim_svc.deactivate_user(s, ORG, created_id)
            assert s.execute(text("SELECT status FROM users WHERE user_id = CAST(:u AS uuid)"), {"u": created_id}).scalar() == "disabled"
    finally:
        with get_session() as s:
            if created_id:
                s.execute(text("DELETE FROM user_roles WHERE user_id = CAST(:u AS uuid)"), {"u": created_id})
                s.execute(text("DELETE FROM users WHERE user_id = CAST(:u AS uuid)"), {"u": created_id})
            # reset the tenant's SCIM token so the demo org is left as it was
            s.execute(text("UPDATE tenant_sso_config SET scim_token_hash = NULL, scim_enabled = false WHERE org_id = CAST(:o AS uuid)"), {"o": ORG})
            s.commit()

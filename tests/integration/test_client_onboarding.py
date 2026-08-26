"""Client-onboarding lifecycle, end to end: intake → submit → provision → activate (password + MFA) → login.

The service commits at each step (create_tenant + add_contract commit internally), so this test cleans up the
tenant it creates in a finally block rather than relying on rollback.
"""
from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import text

from api.services.rbac import authenticate
from core.db.session import get_session
from services.governance import client_onboarding as ob
from services.governance import totp

PLATFORM_ORG = "99999999-9999-4999-8999-999999999999"


def _operator(s) -> str:
    return str(s.execute(text("SELECT user_id FROM users WHERE org_id = :o LIMIT 1"),
                         {"o": PLATFORM_ORG}).scalar())


def _nuke_org(s, org_id: str) -> None:
    for tbl in ("email_outbox", "user_activation", "customer_contract", "org_entitlements"):
        s.execute(text(f"DELETE FROM {tbl} WHERE org_id = CAST(:o AS uuid)"), {"o": org_id})
    s.execute(text("DELETE FROM role_permissions WHERE role_id IN (SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid))"), {"o": org_id})
    s.execute(text("DELETE FROM user_roles WHERE role_id IN (SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid))"), {"o": org_id})
    s.execute(text("DELETE FROM users WHERE org_id = CAST(:o AS uuid)"), {"o": org_id})
    s.execute(text("DELETE FROM roles WHERE org_id = CAST(:o AS uuid)"), {"o": org_id})
    s.execute(text("DELETE FROM client_intake WHERE provisioned_org_id = CAST(:o AS uuid)"), {"o": org_id})
    s.execute(text("DELETE FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id})
    s.commit()


@pytest.mark.integration
def test_full_onboarding_lifecycle():
    suffix = uuid.uuid4().hex[:8]
    company = f"Test Onboarding Co {suffix}"
    admin_email = f"admin.{suffix}@onboarding-test.local"
    org_id = None
    try:
        with get_session() as s:
            actor = _operator(s)

            # 1. operator opens an intake → tokenized form link
            intake = ob.create_intake(s, actor_user_id=actor, actor_org_id=PLATFORM_ORG,
                                      company_name=company, org_type="bank",
                                      contact_email=f"ops.{suffix}@onboarding-test.local", region="EU")
            assert intake["status"] == "invited" and intake["form_token"]
            token = intake["form_token"]

            # 2. the token resolves the intake (client side, no auth)
            assert ob.get_intake_by_token(s, token)["company_name"] == company

            # 3. client submits company details + roster → submitted
            ob.submit_intake_form(s, token, {
                "company_name": company, "country": "IE", "region": "EU",
                "roster": [
                    {"email": admin_email, "full_name": "Test Admin", "role": "admin"},
                    {"email": f"analyst.{suffix}@onboarding-test.local", "full_name": "Test Analyst", "role": "analyst"},
                ],
            })
            row = s.execute(text("SELECT intake_id, status FROM client_intake WHERE company_name = :c"),
                            {"c": company}).mappings().first()
            assert row["status"] == "submitted"
            intake_id = str(row["intake_id"])

            # 4. operator provisions → tenant + users + activation links
            result = ob.provision_from_intake(s, actor_user_id=actor, intake_id=intake_id)
            org_id = result["org_id"]
            assert result["region"] == "EU"
            assert {u["role"] for u in result["users"]} == {"admin", "analyst"}

            # region stamped, users invited (not active until activation)
            assert s.execute(text("SELECT region FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).scalar() == "EU"
            statuses = dict(s.execute(text("SELECT status, count(*) FROM users WHERE org_id = CAST(:o AS uuid) GROUP BY status"), {"o": org_id}).all())
            assert statuses.get("invited") == 2

            # a can't-log-in-yet check: an invited user is rejected
            assert authenticate(s, admin_email, "anything") is None

            # 5. activation — set password + enrol MFA
            admin_link = next(u["activation_url"] for u in result["users"] if u["role"] == "admin")
            act_token = admin_link.rsplit("/", 1)[-1]
            assert ob.get_activation(s, act_token)["password_set"] is False
            ob.set_activation_password(s, act_token, "Str0ng!Passw0rd")
            begin = ob.begin_mfa_enrollment(s, act_token)
            secret = begin["secret"]
            code = totp._code_at(secret, int(time.time() // 30))
            done = ob.confirm_mfa_enrollment(s, act_token, code)
            assert done["activated"] is True

            # 6. now the account is active + MFA-enrolled, and password authenticates
            u = authenticate(s, admin_email, "Str0ng!Passw0rd")
            assert u is not None and u["mfa_enrolled_at"] is not None
            # and the enrolled secret validates a live code (the login layer requires this)
            assert totp.verify(u["mfa_secret"], totp._code_at(secret, int(time.time() // 30))) is True

            # the token is single-use — consumed after activation
            assert ob.get_activation(s, act_token) is None
    finally:
        if org_id:
            with get_session() as s:
                _nuke_org(s, org_id)
        else:
            with get_session() as s:
                s.execute(text("DELETE FROM client_intake WHERE company_name = :c"), {"c": company})
                s.commit()

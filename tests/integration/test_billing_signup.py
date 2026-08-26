"""Self-serve signup + seat-enforced billing — against real provisioning, self-cleaning."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.governance import billing
from services.governance import signup as signup_svc


def _nuke(s, oid):
    s.execute(text("DELETE FROM mfa_backup_code WHERE user_id IN (SELECT user_id FROM users WHERE org_id=CAST(:o AS uuid))"), {"o": oid})
    for t in ("invoice", "subscription", "refresh_token", "email_outbox", "org_entitlements"):
        s.execute(text(f"DELETE FROM {t} WHERE org_id = CAST(:o AS uuid)"), {"o": oid})
    s.execute(text("DELETE FROM role_permissions WHERE role_id IN (SELECT role_id FROM roles WHERE org_id=CAST(:o AS uuid))"), {"o": oid})
    s.execute(text("DELETE FROM user_roles WHERE role_id IN (SELECT role_id FROM roles WHERE org_id=CAST(:o AS uuid))"), {"o": oid})
    s.execute(text("DELETE FROM users WHERE org_id = CAST(:o AS uuid)"), {"o": oid})
    s.execute(text("DELETE FROM roles WHERE org_id = CAST(:o AS uuid)"), {"o": oid})
    s.execute(text("DELETE FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": oid})
    s.commit()


@pytest.mark.integration
def test_signup_creates_trial_and_billing_enforces_seats():
    sfx = uuid.uuid4().hex[:8]
    oid = None
    try:
        with get_session() as s:
            res = signup_svc.self_serve_signup(
                s, company_name=f"Signup Co {sfx}", org_type="bank", country="IE",
                admin_email=f"founder.{sfx}@signup-test.local", admin_full_name="Founder", password="Trial!Pass123")
            oid = res["org_id"]
            row = s.execute(text("SELECT plan, environment FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": oid}).mappings().first()
            assert row["plan"] == "trial" and row["environment"] == "production"

            b = billing.get_billing(s, oid)
            assert b["subscription"]["plan"] == "trial" and b["subscription"]["seats"] == 5
            assert b["seats_used"] == 1

            # fill to the seat limit, then enforce_seat must refuse
            for i in range(4):
                s.execute(text("INSERT INTO users (user_id,org_id,email,role,status,auth_provider,created_at) "
                               "VALUES (gen_random_uuid(),CAST(:o AS uuid),:e,'viewer','active','local',now())"),
                          {"o": oid, "e": f"seat{i}.{sfx}@signup-test.local"})
            s.commit()
            with pytest.raises(billing.BillingError):
                billing.enforce_seat(s, oid)

            # upgrading lifts the limit and raises an invoice
            b2 = billing.change_plan(s, oid, plan="growth", actor_user_id=res["admin_user_id"])
            assert b2["subscription"]["plan"] == "growth" and len(b2["invoices"]) >= 1
            billing.enforce_seat(s, oid)   # no longer raises

            # invalid plan rejected
            with pytest.raises(billing.BillingError):
                billing.change_plan(s, oid, plan="nonsense", actor_user_id=res["admin_user_id"])
    finally:
        if oid:
            with get_session() as s:
                _nuke(s, oid)


@pytest.mark.integration
def test_signup_validates_input():
    with get_session() as s:
        with pytest.raises(signup_svc.SignupError):
            signup_svc.self_serve_signup(s, company_name="X", org_type="bank", country="IE",
                                         admin_email="bad", admin_full_name="", password="short")

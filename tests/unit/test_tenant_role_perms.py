"""The tenant default role -> permission matrix — pins the 2026-09-23 fix that stopped "analyst" being a
second tenant super-user (an independent architecture review finding: a bank's normal preparer role
silently held admin.users.manage and approvals.decide, undermining maker/checker by role design)."""
from __future__ import annotations

from services.governance.tenant_provisioning import ALL_TENANT_PERMS, DEFAULT_ROLE_PERMS, _ADMIN_AND_DECISION_PERMS


def test_analyst_is_a_strict_subset_of_admin():
    analyst = set(DEFAULT_ROLE_PERMS["analyst"])
    admin = set(DEFAULT_ROLE_PERMS["admin"])
    assert analyst < admin, "analyst must be strictly narrower than admin, never equal"


def test_analyst_never_holds_admin_or_decision_permissions():
    analyst = set(DEFAULT_ROLE_PERMS["analyst"])
    assert not (analyst & _ADMIN_AND_DECISION_PERMS), \
        f"analyst holds a permission it never should: {analyst & _ADMIN_AND_DECISION_PERMS}"
    for code in ("admin.users.manage", "admin.roles.manage", "admin.approval_policy.manage",
                "approvals.decide", "board.attest"):
        assert code not in analyst, f"{code} must not be in the analyst default role"


def test_analyst_still_sees_and_prepares_everything_else():
    # narrowing must not have silently dropped an unrelated permission — only the admin/decision ones
    analyst = set(DEFAULT_ROLE_PERMS["analyst"])
    expected = set(ALL_TENANT_PERMS) - _ADMIN_AND_DECISION_PERMS
    assert analyst == expected


def test_admin_still_holds_every_permission():
    # admin is untouched by this fix — it remains the full superset
    assert set(DEFAULT_ROLE_PERMS["admin"]) == set(ALL_TENANT_PERMS)

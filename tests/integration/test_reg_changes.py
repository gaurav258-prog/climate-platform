"""Regulatory-change register — tenancy: a tenant sees platform + own changes, but may only mutate its own."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
import services.governance.reg_changes as C

ORG_A = "11111111-1111-4111-8111-111111111111"   # Meridian
ORG_B = "55555555-5555-4555-8555-555555555555"   # Nordkap


def _actor(s, org):
    return str(s.execute(text("SELECT user_id FROM users WHERE org_id = :o LIMIT 1"), {"o": org}).scalar())


@pytest.mark.integration
def test_tenant_create_is_org_scoped_not_platform_wide():
    with get_session() as s:
        c = C.create_change(s, ORG_A, _actor(s, ORG_A), title="adapt mapping", org_scoped=True)
        assert c["is_platform"] is False
        s.rollback()


@pytest.mark.integration
def test_tenant_cannot_advance_another_orgs_change():
    with get_session() as s:
        # a change owned by org B
        b = C.create_change(s, ORG_B, _actor(s, ORG_B), title="org B change", org_scoped=True)
        # org A must not be able to advance it, nor see it via get_change
        with pytest.raises(C.ChangeError):
            C.advance(s, ORG_A, b["change_id"], "analysis")
        assert C.get_change(s, ORG_A, b["change_id"]) is None
        s.rollback()


@pytest.mark.integration
def test_tenant_cannot_advance_platform_wide_change():
    with get_session() as s:
        # simulate a platform-seeded change (org_id NULL)
        cid = s.execute(text(
            "INSERT INTO regulatory_change (org_id, title, stage) VALUES (NULL, 'EBA ITS', 'identified') RETURNING change_id"
        )).scalar()
        # visible to the tenant (read) …
        assert C.get_change(s, ORG_A, str(cid)) is not None
        # … but NOT advanceable by the tenant
        with pytest.raises(C.ChangeError):
            C.advance(s, ORG_A, str(cid), "analysis")
        s.rollback()

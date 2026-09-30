"""Scope refusals: the retired E1-only report takes no new filings or values (the ESRS statement is filed per
undertaking, with its CSRD role — services.governance.csrd_roles); SFDR keeps its own fund-based reason.

Requires PostgreSQL. Read-only (the refusal raises before anything is written).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.governance import entities as E
from services.governance import filings as F

MANUFACTURER_ORG = "55555555-5555-4555-8555-555555555555"   # Terra Foods (demo)


def _actor(session):
    return str(session.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())


@pytest.mark.integration
def test_csrd_e1_is_retired_for_new_filings_and_values():
    """The E1-only report is retired: a new ESRS statement is an esrs_pack filing, filed per undertaking."""
    with get_session() as s:
        with pytest.raises(F.FilingError, match="retired"):
            F.preflight(s, MANUFACTURER_ORG, "manufacturer", "csrd_e1")
        assert "csrd_e1" not in {f["framework"] for f in F.available_frameworks("manufacturer")}
        from services.governance.provided_data import ProvidedError, submit
        with pytest.raises(ProvidedError, match="retired"):
            submit(s, MANUFACTURER_ORG, None, framework="csrd_e1", datapoint_key="e1_ghg", value_num=1,
                   reporting_period_end="2025-12-31")
        s.rollback()


@pytest.mark.integration
def test_sfdr_pai_refusal_unchanged_reason():
    """SFDR's own reason (fund-based consolidation) is a genuinely different, already-accurate gap — it must
    NOT pick up the agri-specific legal-scoping language."""
    with get_session() as s:
        u = _actor(s)
        am_org = s.execute(text("SELECT org_id::text FROM organizations WHERE type='asset_manager' LIMIT 1")).scalar()
        e = E.create_entity(s, am_org, name="Test C5 AM Sub", kind="legal_entity")
        token = F.preflight(s, am_org, "asset_manager", "sfdr_pai")["confirm_token"]
        with pytest.raises(F.FilingError) as exc:
            F.generate_filing(s, am_org, "asset_manager", "sfdr_pai", u,
                              confirm_token=token, entity_id=e["entity_id"])
        msg = str(exc.value)
        assert "consolidates by fund" in msg
        assert "legal scoping" not in msg and "Art 19a" not in msg
        s.rollback()

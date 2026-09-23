"""Agri CSRD/ESRS entity-scope refusal (2026-09-23 C5 fix): generate_filing() must name BOTH real gaps —
data attribution (no per-legal-entity COGS split) AND legal scoping (doesn't track which subsidiary is the
actual Art 19a/29a reporting undertaking, or which claims the Art 19a(3)/29a(3) exemption) — not just the
first, which understates what a customer would actually need built.

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
def test_csrd_e1_entity_scope_refusal_names_both_gaps():
    with get_session() as s:
        u = _actor(s)
        e = E.create_entity(s, MANUFACTURER_ORG, name="Test C5 Sub", kind="legal_entity")
        token = F.preflight(s, MANUFACTURER_ORG, "manufacturer", "csrd_e1")["confirm_token"]
        with pytest.raises(F.FilingError) as exc:
            F.generate_filing(s, MANUFACTURER_ORG, "manufacturer", "csrd_e1", u,
                              confirm_token=token, entity_id=e["entity_id"])
        msg = str(exc.value)
        assert "data attribution" in msg and "COGS" in msg
        assert "legal scoping" in msg and "Art 19a" in msg and "Art 29a" in msg
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

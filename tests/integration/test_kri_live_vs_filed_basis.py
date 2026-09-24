"""KRI headline KPIs are honestly labeled live, not passed off as "what was filed" (2026-09-24 fix, platform
E2E audit finding #5): confirmed independently across bank/insurer/agri/asset-manager KRI that the headline
tiles recompute from the current book on every call, while only `history` reads frozen filed snapshots — a
disclosed design in the module docstring, but nothing on the response itself said so. Fixed by adding a
`basis` field the shared kri() dispatcher stamps onto every supported result.

Requires PostgreSQL.
"""
from __future__ import annotations

import pytest

from core.db.session import get_session
from services.governance.kri import kri

BANK_ORG = "11111111-1111-4111-8111-111111111111"
INSURER_ORG = "22222222-2222-4222-8222-222222222222"


@pytest.mark.integration
def test_bank_kri_carries_a_live_basis_disclosure():
    with get_session() as s:
        d = kri(s, BANK_ORG, "bank_tcfd")
        assert d["supported"]
        assert d["basis"]["kpis"] == "live"
        assert "recomputed live" in d["basis"]["note"] or "live" in d["basis"]["note"]
        s.rollback()


@pytest.mark.integration
def test_last_filed_reflects_the_real_most_recent_filed_snapshot():
    """When real filed history exists, basis.last_filed must name the MOST RECENT one (history is ordered
    ascending by period), not the first or an arbitrary entry."""
    with get_session() as s:
        d = kri(s, BANK_ORG, "bank_tcfd")
        hist = d.get("history") or []
        if not hist:
            pytest.skip("no filed history for this fixture org/framework right now")
        assert d["basis"]["last_filed"] is not None
        assert d["basis"]["last_filed"]["period_label"] == hist[-1]["label"]
        assert d["basis"]["last_filed"]["filing_id"] == hist[-1]["filing_id"]
        s.rollback()


@pytest.mark.integration
def test_insurer_kri_also_carries_the_basis_disclosure():
    """The fix is in the shared dispatcher, not one framework's builder — must apply uniformly."""
    with get_session() as s:
        d = kri(s, INSURER_ORG, "insurer_climate")
        assert d["supported"]
        assert d["basis"]["kpis"] == "live"
        s.rollback()


@pytest.mark.integration
def test_unsupported_framework_has_no_basis_field():
    with get_session() as s:
        d = kri(s, BANK_ORG, "not_a_real_framework")
        assert d["supported"] is False
        assert "basis" not in d
        s.rollback()

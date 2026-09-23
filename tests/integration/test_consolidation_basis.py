"""consolidation_method guardrail (2026-09-23 C2 fix): an admin can no longer silently tag a 30%-owned stake
'full' — or a majority-owned one 'proportional'/'equity' — with no record of why. IFRS 10 control is
principles-based, so the guardrail never blocks the combination outright; it requires an explicit
consolidation_basis whenever the method runs counter to what ownership_pct alone would presume.

Requires PostgreSQL. Non-polluting: uses "Test Bank Onboarding" (zero pre-existing filings/entities) as a
clean sandbox, each test rolls back its session on exit.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.governance import entities as E
import services.governance.entity_structure_import as ESI

EMPTY_BANK_ORG = "7ec33d97-e346-4d1a-8c84-e257a43aa95c"


def _actor(session):
    return str(session.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())


@pytest.mark.integration
def test_full_below_majority_needs_basis():
    with get_session() as s:
        with pytest.raises(E.EntityError, match="IFRS 10"):
            E.create_entity(s, EMPTY_BANK_ORG, name="Test C2 Minority Full", kind="legal_entity",
                            ownership_pct=30, consolidation_method="full")
        # with a stated basis, it's allowed
        e = E.create_entity(s, EMPTY_BANK_ORG, name="Test C2 Minority Full OK", kind="legal_entity",
                            ownership_pct=30, consolidation_method="full",
                            consolidation_basis="de facto control per IFRS 10.B41-45, board majority")
        assert e["consolidation_method"] == "full" and e["consolidation_basis"]
        s.rollback()


@pytest.mark.integration
def test_proportional_above_majority_needs_basis():
    with get_session() as s:
        with pytest.raises(E.EntityError, match="IFRS 10"):
            E.create_entity(s, EMPTY_BANK_ORG, name="Test C2 Majority Proportional", kind="legal_entity",
                            ownership_pct=80, consolidation_method="proportional")
        e = E.create_entity(s, EMPTY_BANK_ORG, name="Test C2 Majority Proportional OK", kind="legal_entity",
                            ownership_pct=80, consolidation_method="proportional",
                            consolidation_basis="contractual joint control despite majority stake, per JV agreement")
        assert e["consolidation_method"] == "proportional"
        s.rollback()


@pytest.mark.integration
def test_unremarkable_combinations_need_no_basis():
    """Full at >50% (the ordinary case) and proportional/equity at <50% never require a basis."""
    with get_session() as s:
        e1 = E.create_entity(s, EMPTY_BANK_ORG, name="Test C2 Ordinary Full", kind="legal_entity",
                             ownership_pct=100, consolidation_method="full")
        assert e1["consolidation_basis"] is None
        e2 = E.create_entity(s, EMPTY_BANK_ORG, name="Test C2 Ordinary Equity", kind="legal_entity",
                             ownership_pct=25, consolidation_method="equity")
        assert e2["consolidation_basis"] is None
        # exactly 50% is left alone in either direction (genuine joint-control ambiguity)
        e3 = E.create_entity(s, EMPTY_BANK_ORG, name="Test C2 Fifty Fifty", kind="legal_entity",
                             ownership_pct=50, consolidation_method="proportional")
        assert e3["consolidation_basis"] is None
        s.rollback()


@pytest.mark.integration
def test_update_entity_checks_effective_values_not_just_changed_field():
    """Dropping ownership_pct below 50% on an entity that's already 'full' must trigger the guardrail even
    though consolidation_method itself isn't being touched in this call."""
    with get_session() as s:
        e = E.create_entity(s, EMPTY_BANK_ORG, name="Test C2 Update Drop", kind="legal_entity",
                            ownership_pct=100, consolidation_method="full")
        with pytest.raises(E.EntityError, match="IFRS 10"):
            E.update_entity(s, EMPTY_BANK_ORG, e["entity_id"], ownership_pct=20)
        # providing the basis in the same call satisfies it
        e2 = E.update_entity(s, EMPTY_BANK_ORG, e["entity_id"], ownership_pct=20,
                             consolidation_basis="parent guarantee retains control despite the sell-down")
        assert e2["ownership_pct"] == 20.0
        s.rollback()


@pytest.mark.integration
def test_entity_structure_import_enforces_the_same_guardrail():
    """A staged row with a contradicting method/ownership combo and no source_note fails validation up front
    (naming the row), before any entity is created; source_note satisfies it, same as consolidation_basis."""
    with get_session() as s:
        u = _actor(s)
        rows_bad = [{"name": "Test C2 Import Bad", "ownership_pct": 25, "consolidation_method": "full"}]
        imp = ESI.create_import(s, EMPTY_BANK_ORG, u, "manual_csv", rows_bad)
        with pytest.raises(ESI.ImportError_, match="IFRS 10"):
            ESI.confirm_import(s, EMPTY_BANK_ORG, imp["import_id"], u)

        rows_ok = [{"name": "Test C2 Import OK", "ownership_pct": 25, "consolidation_method": "full",
                   "source_note": "de facto control — sole operator under a management agreement"}]
        imp2 = ESI.create_import(s, EMPTY_BANK_ORG, u, "manual_csv", rows_ok)
        res = ESI.confirm_import(s, EMPTY_BANK_ORG, imp2["import_id"], u)
        assert res["status"] == "confirmed" and res["n_created"] == 1
        s.rollback()

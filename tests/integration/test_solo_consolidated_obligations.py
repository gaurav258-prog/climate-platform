"""Solo-and-consolidated as parallel, explicit filing obligations (2026-09-23 C1 foundational fix).

CRR Art 6 requires most bank subsidiaries to file BOTH an individual (solo) return AND be captured in the
parent's consolidated return — as parallel obligations, not alternatives. These tests cover the pieces that
make that real: `filing_role_for()`'s branch/leaf/group derivation, `create_entity()`'s CRR-safe
`requires_solo_filing` default (and the branch exception), `ensure_obligations()` generating a genuine
per-entity solo row for every entity that requires one, and `list_obligations()`'s entity-aware join
correctly distinguishing filing status per entity rather than conflating them.

Requires PostgreSQL. Non-polluting: uses "Test Bank Onboarding" (zero pre-existing filings/entities) as a
clean sandbox, each test rolls back its session on exit.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.governance import entities as E
from services.governance import filings as F

EMPTY_BANK_ORG = "7ec33d97-e346-4d1a-8c84-e257a43aa95c"


def _actor(session):
    return str(session.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())


@pytest.mark.integration
def test_create_entity_defaults_requires_solo_filing_true():
    """The CRR-safe default: assume the individual-reporting duty applies unless waived."""
    with get_session() as s:
        u = _actor(s)
        e = E.create_entity(s, EMPTY_BANK_ORG, name="Test Sub A", kind="legal_entity")
        assert e["requires_solo_filing"] is True
        assert e["solo_waiver_reason"] is None
        s.rollback()


@pytest.mark.integration
def test_create_entity_branch_defaults_requires_solo_filing_false():
    """A branch has no separate legal personality from its head office — no independent Art 6 duty."""
    with get_session() as s:
        e = E.create_entity(s, EMPTY_BANK_ORG, name="Test London Branch", kind="branch")
        assert e["requires_solo_filing"] is False
        s.rollback()


@pytest.mark.integration
def test_create_entity_branch_default_can_be_overridden():
    """Some third-country regimes genuinely impose host-country solo reporting on a branch — allow it explicitly."""
    with get_session() as s:
        e = E.create_entity(s, EMPTY_BANK_ORG, name="Test NY Branch", kind="branch", requires_solo_filing=True)
        assert e["requires_solo_filing"] is True
        s.rollback()


@pytest.mark.integration
def test_waiver_reason_requires_waiver_to_be_true():
    """A waiver reason implies the duty was waived — setting both requires_solo_filing=True and a reason is
    self-contradictory and must be rejected, not silently accepted."""
    with get_session() as s:
        with pytest.raises(E.EntityError):
            E.create_entity(s, EMPTY_BANK_ORG, name="Test Sub B", kind="legal_entity",
                            requires_solo_filing=True, solo_waiver_reason="parent guarantee under Art 7")
        s.rollback()


@pytest.mark.integration
def test_filing_role_for_whole_org_leaf_and_group():
    with get_session() as s:
        parent = E.create_entity(s, EMPTY_BANK_ORG, name="Test Group Parent", kind="group")
        child = E.create_entity(s, EMPTY_BANK_ORG, name="Test Group Child", kind="legal_entity",
                                parent_entity_id=parent["entity_id"])
        assert E.filing_role_for(s, EMPTY_BANK_ORG, None) == "whole_org"
        assert E.filing_role_for(s, EMPTY_BANK_ORG, child["entity_id"]) == "solo"          # leaf → own duty
        assert E.filing_role_for(s, EMPTY_BANK_ORG, parent["entity_id"]) == "consolidated"  # has children → rolls up
        s.rollback()


@pytest.mark.integration
def test_ensure_obligations_generates_solo_row_per_entity_requiring_one():
    """A genuine per-entity solo row for each entity with requires_solo_filing=true, on top of the whole-org row —
    not just one blanket whole-org obligation."""
    with get_session() as s:
        parent = E.create_entity(s, EMPTY_BANK_ORG, name="Test OB Parent", kind="group")
        E.create_entity(s, EMPTY_BANK_ORG, name="Test OB Sub 1", kind="legal_entity",
                        parent_entity_id=parent["entity_id"])
        E.create_entity(s, EMPTY_BANK_ORG, name="Test OB Branch", kind="branch",
                        parent_entity_id=parent["entity_id"])  # requires_solo_filing=False by default

        F.ensure_obligations(s, EMPTY_BANK_ORG, "bank")
        rows = s.execute(text("""
            SELECT entity_id::text AS entity_id, filing_role FROM regulatory_obligation
            WHERE org_id = CAST(:o AS uuid) AND framework = 'bank_tcfd'
        """), {"o": EMPTY_BANK_ORG}).mappings().all()

        # one whole_org row (entity_id NULL) + one solo row per requires_solo_filing=true entity;
        # the branch (requires_solo_filing=False) gets none of its own
        whole_org = [r for r in rows if r["entity_id"] is None]
        solo = [r for r in rows if r["entity_id"] is not None]
        assert len(whole_org) == 1 and whole_org[0]["filing_role"] == "whole_org"
        assert all(r["filing_role"] == "solo" for r in solo)
        assert {r["entity_id"] for r in solo} == {parent["entity_id"], s.execute(text(
            "SELECT entity_id::text FROM reporting_entities WHERE org_id=:o AND name='Test OB Sub 1'"),
            {"o": EMPTY_BANK_ORG}).scalar()}
        s.rollback()


@pytest.mark.integration
def test_ensure_obligations_skips_entity_scoping_for_non_entity_scoped_frameworks():
    """sfdr_pai isn't entity-scoped — only the whole-org row should exist for it, never per-entity solo.
    org_id and org_type are decoupled params (ensure_obligations never looks up the org's real registered
    type), so the sandbox org_id can stand in under org_type='asset_manager' purely to reach a
    non-entity-scoped framework — assetmgmt_tcfd (also asset_manager-sector) is entity-scoped and still
    gets checked here for contrast."""
    with get_session() as s:
        parent = E.create_entity(s, EMPTY_BANK_ORG, name="Test NES Parent", kind="group")
        E.create_entity(s, EMPTY_BANK_ORG, name="Test NES Sub", kind="legal_entity",
                        parent_entity_id=parent["entity_id"])
        F.ensure_obligations(s, EMPTY_BANK_ORG, "asset_manager")

        pai_rows = s.execute(text("""
            SELECT entity_id FROM regulatory_obligation
            WHERE org_id = CAST(:o AS uuid) AND framework = 'sfdr_pai'
        """), {"o": EMPTY_BANK_ORG}).mappings().all()
        assert len(pai_rows) == 1 and pai_rows[0]["entity_id"] is None

        tcfd_rows = s.execute(text("""
            SELECT entity_id FROM regulatory_obligation
            WHERE org_id = CAST(:o AS uuid) AND framework = 'assetmgmt_tcfd'
        """), {"o": EMPTY_BANK_ORG}).mappings().all()
        assert len(tcfd_rows) == 3  # whole_org + 2 solo (parent + sub)
        s.rollback()


@pytest.mark.integration
def test_list_obligations_matches_filing_status_per_entity_not_globally():
    """The entity-aware join: two entities' solo obligations for the same framework/period must show their OWN
    filing's status, not both inheriting whichever filing was created first (the pre-fix bug)."""
    with get_session() as s:
        u = _actor(s)
        parent = E.create_entity(s, EMPTY_BANK_ORG, name="Test Join Parent", kind="group")
        sub = E.create_entity(s, EMPTY_BANK_ORG, name="Test Join Sub", kind="legal_entity",
                              parent_entity_id=parent["entity_id"])

        # generate a real filing scoped to the SUBSIDIARY only (needs its own snapshot/portfolio data — use a
        # direct insert against a throwaway period, same pattern as test_filing_lifecycle, to avoid needing a
        # populated book just to prove the join)
        pe = "2099-12-31"
        fid_sub = s.execute(text("""
            INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, entity_id,
                                           filing_role, created_by)
            VALUES (:o, 'bank_tcfd', :pe, 'FY2099', 'submitted', CAST(:e AS uuid), 'solo', :u)
            RETURNING filing_id
        """), {"o": EMPTY_BANK_ORG, "pe": pe, "e": sub["entity_id"], "u": u}).scalar()

        s.execute(text("""
            INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency,
                                                entity_id, filing_role)
            VALUES (:o, 'bank_tcfd', :pe, 'FY2099', :pe, 'annual', CAST(:e AS uuid), 'solo')
        """), {"o": EMPTY_BANK_ORG, "pe": pe, "e": sub["entity_id"]})
        s.execute(text("""
            INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency,
                                                entity_id, filing_role)
            VALUES (:o, 'bank_tcfd', :pe, 'FY2099', :pe, 'annual', CAST(:e AS uuid), 'solo')
        """), {"o": EMPTY_BANK_ORG, "pe": pe, "e": parent["entity_id"]})

        obs = F.list_obligations(s, EMPTY_BANK_ORG, "bank")
        by_entity = {o["entity_id"]: o for o in obs
                    if o["framework"] == "bank_tcfd" and o["period_end"] == pe}
        assert by_entity[sub["entity_id"]]["filing_status"] == "submitted"
        assert by_entity[parent["entity_id"]]["filing_status"] == "not_started"  # must NOT inherit the sub's filing
        s.rollback()

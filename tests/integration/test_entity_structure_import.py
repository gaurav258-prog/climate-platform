"""Entity-structure import — the standard workflow for onboarding any institution's org tree (staging,
review, confirm). Requires PostgreSQL; non-polluting (each test rolls back).

Uses "Test Bank Onboarding" (zero pre-existing filings/entities) as a clean sandbox so a topological-order
or cycle test never collides with a real demo org's own tree.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
import services.governance.entity_structure_import as ESI

EMPTY_BANK_ORG = "7ec33d97-e346-4d1a-8c84-e257a43aa95c"


def _actor(session):
    return str(session.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())


@pytest.mark.integration
def test_stage_then_confirm_creates_entities_in_parent_child_order():
    with get_session() as s:
        u = _actor(s)
        rows = [
            {"name": "Acme Holding N.V.", "country": "NL", "ownership_pct": 100, "consolidation_method": "full"},
            {"name": "Acme Belgium N.V.", "parent_ref": "Acme Holding N.V.", "country": "BE",
             "ownership_pct": 100, "consolidation_method": "full"},
            {"name": "Acme Poland S.A.", "parent_ref": "Acme Holding N.V.", "country": "PL",
             "ownership_pct": 75, "consolidation_method": "full"},
        ]
        imp = ESI.create_import(s, EMPTY_BANK_ORG, u, "manual_csv", rows)
        assert imp["status"] == "staged" and len(imp["rows"]) == 3

        res = ESI.confirm_import(s, EMPTY_BANK_ORG, imp["import_id"], u)
        assert res["status"] == "confirmed" and res["n_created"] == 3

        tree = {r["name"]: r for r in s.execute(text("""
            SELECT name, parent_entity_id::text AS parent_entity_id, ownership_pct::float AS ownership_pct
            FROM reporting_entities WHERE org_id = CAST(:o AS uuid)
        """), {"o": EMPTY_BANK_ORG}).mappings().all()}
        assert tree["Acme Holding N.V."]["parent_entity_id"] is None
        assert tree["Acme Poland S.A."]["ownership_pct"] == 75.0
        # exact parent-id resolution (not just "has a parent") is covered by the next test
        s.rollback()


@pytest.mark.integration
def test_parent_child_link_resolves_to_the_real_created_entity_id():
    with get_session() as s:
        u = _actor(s)
        rows = [
            {"name": "Beta Holding N.V.", "country": "NL"},
            {"name": "Beta Germany AG", "parent_ref": "Beta Holding N.V.", "country": "DE"},
        ]
        imp = ESI.create_import(s, EMPTY_BANK_ORG, u, "manual_csv", rows)
        ESI.confirm_import(s, EMPTY_BANK_ORG, imp["import_id"], u)

        rows_db = {r["name"]: r for r in s.execute(text("""
            SELECT entity_id::text AS entity_id, name, parent_entity_id::text AS parent_entity_id
            FROM reporting_entities WHERE org_id = CAST(:o AS uuid)
        """), {"o": EMPTY_BANK_ORG}).mappings().all()}
        assert rows_db["Beta Germany AG"]["parent_entity_id"] == rows_db["Beta Holding N.V."]["entity_id"]
        s.rollback()


@pytest.mark.integration
def test_circular_parent_reference_is_refused_before_creating_anything():
    with get_session() as s:
        u = _actor(s)
        rows = [
            {"name": "Loop A", "parent_ref": "Loop B"},
            {"name": "Loop B", "parent_ref": "Loop A"},
        ]
        imp = ESI.create_import(s, EMPTY_BANK_ORG, u, "manual_csv", rows)
        with pytest.raises(ESI.ImportError_, match="circular"):
            ESI.confirm_import(s, EMPTY_BANK_ORG, imp["import_id"], u)
        n = s.execute(text("SELECT count(*) FROM reporting_entities WHERE org_id=CAST(:o AS uuid) AND name LIKE 'Loop%'"),
                      {"o": EMPTY_BANK_ORG}).scalar()
        assert n == 0, "a refused batch must create nothing, not a partial tree"
        s.rollback()


@pytest.mark.integration
def test_dangling_parent_reference_is_refused():
    with get_session() as s:
        u = _actor(s)
        rows = [{"name": "Orphan Corp", "parent_ref": "Nonexistent Parent Ltd"}]
        imp = ESI.create_import(s, EMPTY_BANK_ORG, u, "manual_csv", rows)
        with pytest.raises(ESI.ImportError_, match="neither another row"):
            ESI.confirm_import(s, EMPTY_BANK_ORG, imp["import_id"], u)
        s.rollback()


@pytest.mark.integration
def test_rejected_row_is_excluded_from_creation():
    with get_session() as s:
        u = _actor(s)
        rows = [{"name": "Keep Me Ltd"}, {"name": "Reject Me Ltd"}]
        imp = ESI.create_import(s, EMPTY_BANK_ORG, u, "manual_csv", rows)
        reject_row = next(r for r in imp["rows"] if r["name"] == "Reject Me Ltd")
        ESI.update_row(s, EMPTY_BANK_ORG, imp["import_id"], reject_row["row_id"], status="rejected")

        res = ESI.confirm_import(s, EMPTY_BANK_ORG, imp["import_id"], u)
        assert res["n_created"] == 1 and res["n_rejected"] == 1
        names = {c["name"] for c in res["created"]}
        assert names == {"Keep Me Ltd"}
        s.rollback()


@pytest.mark.integration
def test_can_attach_under_an_already_existing_entity_by_id():
    with get_session() as s:
        from services.governance.entities import create_entity
        u = _actor(s)
        existing = create_entity(s, EMPTY_BANK_ORG, name="Pre-existing Parent Ltd")
        rows = [{"name": "New Sub Ltd", "parent_entity_id": existing["entity_id"]}]
        imp = ESI.create_import(s, EMPTY_BANK_ORG, u, "manual_csv", rows)
        res = ESI.confirm_import(s, EMPTY_BANK_ORG, imp["import_id"], u)
        assert res["n_created"] == 1
        new_id = res["created"][0]["entity_id"]
        parent = s.execute(text("SELECT parent_entity_id::text FROM reporting_entities WHERE entity_id=CAST(:e AS uuid)"),
                           {"e": new_id}).scalar()
        assert parent == existing["entity_id"]
        s.rollback()


@pytest.mark.integration
def test_discard_leaves_nothing_created():
    with get_session() as s:
        u = _actor(s)
        imp = ESI.create_import(s, EMPTY_BANK_ORG, u, "manual_csv", [{"name": "Discarded Corp"}])
        ESI.discard_import(s, EMPTY_BANK_ORG, imp["import_id"])
        got = ESI.get_import(s, EMPTY_BANK_ORG, imp["import_id"])
        assert got["status"] == "discarded"
        n = s.execute(text("SELECT count(*) FROM reporting_entities WHERE org_id=CAST(:o AS uuid) AND name='Discarded Corp'"),
                      {"o": EMPTY_BANK_ORG}).scalar()
        assert n == 0
        with pytest.raises(ESI.ImportError_):
            ESI.confirm_import(s, EMPTY_BANK_ORG, imp["import_id"], u)
        s.rollback()


@pytest.mark.integration
def test_duplicate_entity_reference_in_one_batch_is_refused():
    with get_session() as s:
        u = _actor(s)
        rows = [{"name": "Dup Ltd", "country": "NL"}, {"name": "Dup Ltd", "country": "BE"}]
        imp = ESI.create_import(s, EMPTY_BANK_ORG, u, "manual_csv", rows)
        with pytest.raises(ESI.ImportError_, match="duplicate"):
            ESI.confirm_import(s, EMPTY_BANK_ORG, imp["import_id"], u)
        s.rollback()

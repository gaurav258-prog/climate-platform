"""Intake phase 3: every asset fact per source, with history; our own values derived; differences queued for a person.

  * the book as first seen is recorded as the client's statement (method book); a later change is credited to the path
    that made it (a batch, an edit) — never re-recorded when nothing changed
  * our country comes from the coordinates (land layer → ISO 3166 via the country reference): agreement is silent, a
    real difference opens one conflict; a written form the reference knows ('UK') is not a difference
  * a decision stands: keeping the client's value closes the conflict and the same pair is never raised again
  * using our value needs a second person; approved, the live value changes and is not taken for a client statement
  * a corrected book value closes an open conflict as 'agreed'
Runs inside a rolled-back transaction."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.intake import conflicts as C
from services.intake import observations as O
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration


def _asset(s, country: str):
    """A new Meridian bank asset in Germany (by its coordinates) — a copy of a seeded Berlin asset made inside this
    rolled-back transaction — with its book country set to `country`. New, so the facts ledger (append-only) has never
    seen it: the test does not depend on what the live database has recorded before."""
    src = s.execute(text("""SELECT entity_id::text FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND vertical = 'banking'
                            AND source = 'own' AND latitude BETWEEN 52.3 AND 52.7 AND longitude BETWEEN 13.2 AND 13.6 LIMIT 1"""),
                    {"o": BANK_ORG}).scalar()
    if not src:
        pytest.skip("no seeded Berlin asset")
    new = s.execute(text("""
        INSERT INTO portfolio_entities
        SELECT (jsonb_populate_record(NULL::portfolio_entities, to_jsonb(p) || jsonb_build_object(
                'entity_id', gen_random_uuid(), 'entity_name', 'asset-facts test ' || gen_random_uuid(), 'country', CAST(:c AS text)))).*
        FROM portfolio_entities p WHERE p.entity_id = CAST(:src AS uuid)
        RETURNING entity_id::text"""), {"src": src, "c": country}).scalar()
    s.execute(text("""
        INSERT INTO ext_banking
        SELECT (jsonb_populate_record(NULL::ext_banking, to_jsonb(x) || jsonb_build_object('entity_id', CAST(:new AS text)))).*
        FROM ext_banking x WHERE x.entity_id = CAST(:src AS uuid)"""), {"src": src, "new": new})
    return new


def _open(s, aid):
    return s.execute(text("SELECT conflict_id::text, client_value, tellumen_value, rule, status FROM asset_conflicts "
                          "WHERE asset_id = CAST(:a AS uuid) AND status <> 'resolved'"), {"a": aid}).mappings().first()


def _user(s, email):
    return s.execute(text("SELECT user_id::text FROM users WHERE email = :e"), {"e": email}).scalar()


def test_the_book_is_recorded_once_and_our_country_agrees_silently(session_rolled_back):
    s = session_rolled_back
    aid = _asset(s, "DE")
    first = O.sync(s, BANK_ORG, asset_ids=[aid])
    seen = O.latest(s, BANK_ORG, "portfolio_entities", [aid])
    assert seen[(aid, "country", "client")]["value"] == "DE" and seen[(aid, "country", "client")]["method"] == "book"
    assert seen[(aid, "country", "tellumen")]["value"] == "DE" and seen[(aid, "country", "tellumen")]["method"] == "land_layer"
    assert first["client"] > 5 and _open(s, aid) is None
    assert O.sync(s, BANK_ORG, asset_ids=[aid]) == {"client": 0, "tellumen": 0, "opened": 0, "agreed": 0}   # nothing new
    s.execute(text("UPDATE portfolio_entities SET entity_name = entity_name || ' (renamed)' WHERE entity_id = CAST(:i AS uuid)"), {"i": aid})
    O.sync(s, BANK_ORG, asset_ids=[aid], method="manual_edit", origin="user:test")
    hist = [h for h in O.history(s, BANK_ORG, "portfolio_entities", aid) if h["field"] == "entity_name"]
    assert [h["method"] for h in hist] == ["manual_edit", "book"] and hist[0]["origin"] == "user:test"


def test_a_written_form_the_reference_knows_is_not_a_difference(session_rolled_back):
    s = session_rolled_back
    aid = _asset(s, "de")
    O.sync(s, BANK_ORG, asset_ids=[aid])
    assert _open(s, aid) is None


def test_a_real_difference_opens_one_conflict_and_keeping_the_clients_value_stands(session_rolled_back):
    s = session_rolled_back
    aid = _asset(s, "FR")
    O.sync(s, BANK_ORG, asset_ids=[aid])
    c = _open(s, aid)
    assert c and c["client_value"] == "FR" and c["tellumen_value"] == "DE" and "coordinates are in DE" in c["rule"]
    listed = C.list_conflicts(s, BANK_ORG)
    assert any(x["conflict_id"] == c["conflict_id"] and x["asset_name"] for x in listed["conflicts"])
    C.resolve(s, BANK_ORG, c["conflict_id"], "client", _user(s, "admin@meridian.demo"), None)
    assert _open(s, aid) is None
    s.execute(text("ALTER TABLE asset_observations DISABLE TRIGGER trg_asset_obs_worm"))   # simulate a re-sent file
    O.record(s, [{"org_id": BANK_ORG, "asset_table": "portfolio_entities", "asset_id": aid, "field": "country",
                  "value": "DE", "source": "client", "method": "intake_batch"},
                 {"org_id": BANK_ORG, "asset_table": "portfolio_entities", "asset_id": aid, "field": "country",
                  "value": "FR", "source": "client", "method": "intake_batch"}])
    s.execute(text("ALTER TABLE asset_observations ENABLE TRIGGER trg_asset_obs_worm"))
    C.reconcile(s, BANK_ORG, "portfolio_entities", [aid])
    assert _open(s, aid) is None                                   # the same (FR, DE) was decided: not raised again
    with pytest.raises(C.ConflictError):
        C.resolve(s, BANK_ORG, c["conflict_id"], "client", _user(s, "admin@meridian.demo"), None)


def test_using_our_value_needs_a_second_person_and_then_changes_the_live_value(session_rolled_back):
    s = session_rolled_back
    aid = _asset(s, "FR")
    O.sync(s, BANK_ORG, asset_ids=[aid])
    c = _open(s, aid)
    with pytest.raises(C.ConflictError):
        C.resolve(s, BANK_ORG, c["conflict_id"], "explained", _user(s, "admin@meridian.demo"), "  ")   # a note is required
    out = C.resolve(s, BANK_ORG, c["conflict_id"], "tellumen", _user(s, "admin@meridian.demo"), "coordinates are geocoded")
    assert out["status"] == "awaiting_approval"
    live = lambda: s.execute(text("SELECT country FROM portfolio_entities WHERE entity_id = CAST(:i AS uuid)"), {"i": aid}).scalar()  # noqa: E731
    assert live() == "FR"                                          # nothing changes before the second person
    payload = s.execute(text("SELECT payload FROM approval_requests WHERE request_id = CAST(:r AS uuid)"),
                        {"r": out["approval_request_id"]}).scalar()
    assert C.apply_decision(s, BANK_ORG, payload, "approved", _user(s, "approver@meridian.demo"))["applied"]
    assert live() == "DE"
    assert O.sync(s, BANK_ORG, asset_ids=[aid])["client"] == 0      # our value in the book is not a client statement
    assert _open(s, aid) is None


def test_a_corrected_book_closes_the_conflict_as_agreed(session_rolled_back):
    s = session_rolled_back
    aid = _asset(s, "FR")
    O.sync(s, BANK_ORG, asset_ids=[aid])
    assert _open(s, aid)
    s.execute(text("UPDATE portfolio_entities SET country = 'DE' WHERE entity_id = CAST(:i AS uuid)"), {"i": aid})
    assert O.sync(s, BANK_ORG, asset_ids=[aid], method="intake_batch", origin="batch:test")["agreed"] == 1
    assert _open(s, aid) is None

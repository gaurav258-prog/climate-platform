"""A Meridian bank asset in Berlin, made inside the caller's rolled-back transaction — a copy of any of Meridian's own
banking assets, placed at Berlin's coordinates (inside Germany on the land layer) and booked in `country`. New, so no
ledger (append-only) has seen it and no test depends on what the live database happens to hold (until 2026-10-03 these
tests used a leftover upload-test asset and skipped when it was gone)."""
from __future__ import annotations

from sqlalchemy import text

from tests.integration.test_intake_pipeline import BANK_ORG

BERLIN = (52.5200, 13.4050)


def berlin_asset(s, country: str) -> str:
    src = s.execute(text("""SELECT entity_id::text FROM portfolio_entities WHERE org_id = CAST(:o AS uuid)
                            AND vertical = 'banking' AND source = 'own' ORDER BY entity_id LIMIT 1"""), {"o": BANK_ORG}).scalar()
    assert src, "Meridian has no banking asset to copy"
    new = s.execute(text("""
        INSERT INTO portfolio_entities
        SELECT (jsonb_populate_record(NULL::portfolio_entities, to_jsonb(p) || jsonb_build_object(
                'entity_id', gen_random_uuid(), 'entity_name', 'Berlin test asset ' || gen_random_uuid(),
                'external_ref', NULL, 'latitude', CAST(:lat AS float), 'longitude', CAST(:lon AS float),
                'country', CAST(:c AS text)))).*
        FROM portfolio_entities p WHERE p.entity_id = CAST(:src AS uuid)
        RETURNING entity_id::text"""), {"src": src, "c": country, "lat": BERLIN[0], "lon": BERLIN[1]}).scalar()
    s.execute(text("""
        INSERT INTO ext_banking
        SELECT (jsonb_populate_record(NULL::ext_banking, to_jsonb(x) || jsonb_build_object('entity_id', CAST(:new AS text)))).*
        FROM ext_banking x WHERE x.entity_id = CAST(:src AS uuid)"""), {"src": src, "new": new})
    return new

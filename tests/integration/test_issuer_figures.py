"""E318: when several rows state an issuer's figure for the same year, the one read is settled by the stated order of
sources (services.issuer_figures; the product owner's decision of 2026-10-22), after the organisation's own row and the
vendor rule. Rolled back throughout."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.issuer_figures import latest

pytestmark = pytest.mark.integration
ORG = "0bbe0bbe-0000-4000-8000-000000317a01"


def _read(s, issuer: str):
    return tuple(s.execute(text(f"SELECT x.v, x.y FROM {latest('evic_eur', 'CAST(:iss AS uuid)')} x"),
                           {"iss": issuer, "org": ORG}).first() or (None, None))


def _row(s, issuer, source, evic, org=None, year=2025):
    s.execute(text("""INSERT INTO issuer_emissions (issuer_id, org_id, reporting_year, evic_eur, source)
                      VALUES (CAST(:i AS uuid), CAST(:o AS uuid), :y, :v, :s)"""),
              {"i": issuer, "o": org, "y": year, "v": evic, "s": source})


def test_a_tie_is_settled_by_the_stated_order_of_sources(session_rolled_back):
    s = session_rolled_back
    s.execute(text("INSERT INTO organizations (org_id, name, type, country) VALUES (:o, 'tie test', 'asset_manager', 'DE')"),
              {"o": ORG})
    issuer = s.execute(text("INSERT INTO issuers (name, source) VALUES ('Tie Test AG', 'manual') "
                            "RETURNING issuer_id::text")).scalar()
    assert _read(s, issuer) == (None, None)
    _row(s, issuer, "cdp", 10e9)
    _row(s, issuer, "vendor", 30e9)
    assert _read(s, issuer) == (10e9, 2025)            # a vendor's last
    _row(s, issuer, "disclosed", 20e9)
    assert _read(s, issuer) == (20e9, 2025)            # the annual report before CDP, the same year
    _row(s, issuer, "disclosed", 25e9, year=2024)
    assert _read(s, issuer) == (20e9, 2025)            # the latest year before the source order
    _row(s, issuer, "vendor", 35e9, org=ORG)
    assert _read(s, issuer) == (35e9, 2025)            # the organisation's own row first, as before
    _row(s, issuer, "client", 40e9, org=ORG)
    assert _read(s, issuer) == (40e9, 2025)            # its own data before its vendor's

"""E317: an issuer's site lies in the country it states. The demo book's sites once sat near Valencia while named and
stated as Cologne, Stockholm, Malmö or Rotterdam — a German utility's head office was scored, and its loss read, in Spain
(the loss engine picks a site's damage curve by its stated country). Read over the development database, as the demo-data
guard is: a site whose coordinates fall in a country the land layer draws must state that country."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from scripts.seed_demo_asset_manager import ISSUERS, SITES
from services.intake.observations import _country_from_location, _drawn

pytestmark = pytest.mark.integration


def misplaced(rows) -> list[str]:
    drawn = _drawn()
    out = []
    for r in rows:
        stated, where = (r["country"] or "").strip().upper(), _country_from_location(None, dict(r))
        if stated and where and stated in drawn and where != stated:
            out.append(f"{r['issuer']} · {r['name']}: states {stated}, lies in {where}")
    return out


def test_every_located_site_lies_in_the_country_it_states():
    with get_session() as s:
        rows = s.execute(text("""SELECT i.name AS issuer, f.name, f.country, f.latitude, f.longitude
                                 FROM issuer_facilities f JOIN issuers i USING (issuer_id)
                                 WHERE f.latitude IS NOT NULL""")).mappings().all()
    assert misplaced(rows) == [], "a site's coordinates and its stated country disagree"


def test_the_demo_seed_places_each_site_in_its_issuers_country():
    rows = [{"issuer": name, "name": f, "country": country, "latitude": SITES[f][0], "longitude": SITES[f][1]}
            for name, _t, country, *_r, facilities, _e in ISSUERS for f, *_ in facilities if SITES[f]]
    assert len(rows) == 10 and misplaced(rows) == []
    assert misplaced([{"issuer": "x", "name": "Cologne HQ", "country": "DE", "latitude": 38.60125,
                       "longitude": -0.10273}])          # where the seed once put it: the guard sees it

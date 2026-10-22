"""E309/E310/E311: a lookup the Copernicus data store would not take ends 'busy' — no unexpected error — and the poll shows
it in customer words; polling a lookup answers at all (it was served by a private helper), and with its own hazard."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from core import messages
from services.data.copernicus import CopernicusBusy

pytestmark = pytest.mark.integration
CELL = "881f1d4b9bfffff"


def test_a_lookup_the_data_store_would_not_take_ends_busy_without_an_error(monkeypatch):
    from core.db.session import get_session
    from scripts import score_heat_on_demand as H
    lid = str(uuid.uuid4())

    def refused(*a, **k):
        raise CopernicusBusy("cds reanalysis-era5-land: refused after 4 attempts")
    monkeypatch.setattr(H, "fetch_and_score", refused)
    with get_session() as s:
        s.execute(text("""INSERT INTO public_lookups (lookup_id, latitude, longitude, h3_cell_r8, hazard_type, status)
                          VALUES (:id, 50.94, 6.97, :c, 'heat_acute', 'computing')"""), {"id": lid, "c": CELL})
    try:
        H.run_heat_lookup(lid, 50.94, 6.97)                     # returns: the refusal is not an unexpected error
        with get_session() as s:
            assert s.execute(text("SELECT status FROM public_lookups WHERE lookup_id = :id"), {"id": lid}).scalar() == "busy"
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM public_lookups WHERE lookup_id = :id"), {"id": lid})


def test_the_poll_answers_and_says_busy_in_customer_words(api):
    busy, pending = str(uuid.uuid4()), str(uuid.uuid4())
    for lid, st in ((busy, "busy"), (pending, "computing")):
        api.s.execute(text("""INSERT INTO public_lookups (lookup_id, latitude, longitude, h3_cell_r8, hazard_type, status)
                              VALUES (:id, 50.94, 6.97, :c, 'heat_acute', :st)"""), {"id": lid, "c": CELL, "st": st})
    r = api.get(f"/v1/lookup/score/{busy}")
    assert r.status_code == 200, r.text
    assert r.json()["hazard"]["status"] == "failed"
    assert r.json()["hazard"]["reason"] == messages.label("lookup.copernicus_busy")
    r = api.get(f"/v1/lookup/score/{pending}")
    assert r.status_code == 200 and r.json()["hazard"]["status"] == "pending"


def test_a_finished_lookup_polls_its_own_hazard_not_the_last_one_scored(api):
    """E311: polling a heat lookup returned the cell's pollution score — the newest score of any hazard for the cell."""
    cell, lid = "88283082a3fffff", str(uuid.uuid4())
    api.s.execute(text("""INSERT INTO public_lookups (lookup_id, latitude, longitude, h3_cell_r8, hazard_type, status)
                          VALUES (:id, 37.77, -122.42, :c, 'heat_acute', 'done')"""), {"id": lid, "c": cell})
    for hz, score, lane, ago in (("heat_acute", 11.0, "standing", 3), ("heat_acute", 42.0, "nowcast", 2),
                                 ("pollution", 77.0, "standing", 0)):
        api.s.execute(text("""INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario,
                              time_horizon, risk_score, risk_bucket, model_version, data_vintage, scored_at, valid_from,
                              score_lane)
                              VALUES (gen_random_uuid(), :c, 8, :hz, 'baseline', 'current', :s, 'M', 'test', now(),
                              now() - make_interval(mins => :a), now(), :lane)"""),
                      {"c": cell, "hz": hz, "s": score, "lane": lane, "a": ago})
    h = api.get(f"/v1/lookup/score/{lid}").json()["hazard"]
    assert (h["hazard_type"], h["risk_score"]) == ("heat_acute", 42.0)    # its own hazard, the nowcast its job wrote

"""E171: the loss API shows what every figure stands on — families with their test or the reason they are refused,
layers with what is sampled, and runs whose totals never add figures of different standing. Rolled back throughout."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.loss import engine
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
ADMIN = ("admin@meridian.demo", "Demo!admin1")


def _org(api) -> str:
    return api.s.execute(text("SELECT org_id::text FROM users WHERE email = :e"), {"e": ADMIN[0]}).scalar()


def test_families_show_their_test_and_the_refused_say_why(api):
    h = _login(api, *ADMIN)
    r = api.get("/v1/loss/families", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    refused = {f["family"]: f["reasons"] for f in body["refused"]}
    for fam in ("eberenz_2021_tdr", "eberenz_2021_rmsf"):
        assert any("max_sustained_wind_1min" in why for why in refused[fam])
    for f in body["families"]:
        assert f["kind"] in ("published", "measured") and f["curves"]
        if f["kind"] == "measured":
            assert f["test"] is not None and "passed" in f["test"]
    assert set(body["adopted"]) == {"flood", "storm"}


def test_layers_are_listed_with_what_is_sampled(api):
    h = _login(api, *ADMIN)
    layers = {L["key"]: L for L in api.get("/v1/loss/layers", headers=h).json()["layers"]}
    assert {"jrc_river_flood", "storm_v4_wind"} <= set(layers)
    assert layers["storm_v4_wind"]["metric"] == "max_sustained_wind_10min"
    assert layers["jrc_river_flood"]["sampled"]["places"] >= 0
    if "jrc_flood_30m" in layers:                                   # a refinement shows both of its tests and its status
        r = layers["jrc_flood_30m"]
        assert r["status"] in ("candidate", "in_use") and "test" in r and "building_scale_test" in r


def test_a_run_lists_gaps_by_reason_and_never_adds_across_standing(api):
    h = _login(api, *ADMIN)
    org = _org(api)
    run_id = engine.run(api.s, org, "banking")["run_id"]
    r = api.get(f"/v1/loss/runs/{run_id}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run"]["run_id"] == run_id
    assert sum(g["count"] for g in body["gaps"]) + sum(t["results"] for t in body["totals"]) == len(body["results"])
    assert len({(t["peril"], t["standing"]) for t in body["totals"]}) == len(body["totals"])
    assert any(x["run_id"] == run_id for x in api.get("/v1/loss/runs", headers=h).json()["runs"])


def test_another_orgs_run_is_not_found(api):
    h = _login(api, *ADMIN)
    other = api.s.execute(text("""SELECT org_id::text FROM organizations WHERE org_id <> CAST(:o AS uuid) LIMIT 1"""),
                          {"o": _org(api)}).scalar()
    run_id = engine.run(api.s, other, "banking")["run_id"]
    assert api.get(f"/v1/loss/runs/{run_id}", headers=h).status_code == 404


def test_a_run_needs_a_known_book(api):
    h = _login(api, *ADMIN)
    assert api.post("/v1/loss/runs", json={"book": "everything"}, headers=h).status_code == 422

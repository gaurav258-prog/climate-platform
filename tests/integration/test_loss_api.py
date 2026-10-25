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
    for why in refused.values():
        assert why                                       # a refused family always says why
    usable = {f["family"]: f for f in body["families"]}
    for fam in ("eberenz_2021_tdr", "eberenz_2021_rmsf"):  # read through STORM's own factor (2026-10-20)
        assert fam in usable and fam not in refused and usable[fam]["metric"] == "max_sustained_wind_1min"
    for f in body["families"]:
        assert f["kind"] in ("published", "measured") and f["curves"]
        if f["kind"] == "measured":
            assert f["test"] is not None and "passed" in f["test"]
    assert set(body["adopted"]) == {"flood", "coastal_flood", "storm"}


def test_layers_are_listed_with_what_is_sampled(api):
    h = _login(api, *ADMIN)
    layers = {L["key"]: L for L in api.get("/v1/loss/layers", headers=h).json()["layers"]}
    assert {"jrc_river_flood", "storm_v4_wind"} <= set(layers)
    assert layers["storm_v4_wind"]["metric"] == "max_sustained_wind_10min"
    assert layers["jrc_river_flood"]["sampled"]["places"] >= 0
    if "jrc_flood_30m" in layers:                                   # a refinement shows both of its tests and its status
        r = layers["jrc_flood_30m"]
        assert r["status"] in ("candidate", "in_use") and "test" in r and "building_scale_test" in r
    eu = layers["jrc_river_flood_europe"]                           # a replacement names what and where it replaces
    assert eu["replaces"] == "jrc_river_flood" and eu["status"] in ("candidate", "in_use", "refused")
    assert eu["coverage_countries"] and len(eu["return_periods"]) == 9


def test_the_protection_map_is_listed_with_what_it_holds(api):
    h = _login(api, *ADMIN)
    got = api.get("/v1/loss/layers", headers=h).json()["protection_layers"]
    P = {p["key"]: p for p in got}["jrc_flood_protection_europe"]
    assert P["unit"] == "years" and P["metric"] == "design_return_period" and P["licence"].startswith("CC BY 4.0")
    assert set(P["sampled"]) >= {"places"}


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


def test_a_projection_names_both_a_scenario_and_a_year(api):
    h = _login(api, *ADMIN)
    assert api.post("/v1/loss/runs", json={"book": "banking", "scenario": "hot_house_3_5c"}, headers=h).status_code == 422
    assert api.post("/v1/loss/runs", json={"book": "banking", "horizon": "2050"}, headers=h).status_code == 422
    assert api.post("/v1/loss/runs", json={"book": "banking", "scenario": "x", "horizon": "2050"}, headers=h).status_code == 422


def test_the_projection_page_says_what_is_served_and_why_the_rest_is_not(api):
    h = _login(api, *ADMIN)
    body = api.get("/v1/loss/projection", headers=h).json()["perils"]
    river = body["flood"]
    cells = {(c["scenario"], c["horizon"]): c["gap"] for c in river["cells"]}
    placed = {(c["scenario"], c["horizon"]): c["placement"] for c in river["cells"]}
    assert cells[("hot_house_3_5c", "2050")] is None and cells[("orderly_1_5c", "2050")] is None   # read at its warming
    assert ("disorderly_2c", "2080") not in cells                                                  # one timeline
    assert cells[("hot_house_3_5c", "2100")]["code"] == "loss.gap.beyond_warming"
    assert "Hot house 3.5 °C by 2100" in cells[("hot_house_3_5c", "2100")]["detail"]["what"]
    assert placed[("orderly_1_5c", "2050")]["code"] == "loss.projection.between"
    assert "RCP" in placed[("orderly_1_5c", "2050")]["detail"]["what"] and placed[("hot_house_3_5c", "2100")] is None
    assert river["licence"] == "CC BY 4.0" and len(river["members"]) == 5
    coast = {(c["scenario"], c["horizon"]): c for c in body["coastal_flood"]["cells"]}           # sea-level percentiles
    assert body["coastal_flood"]["members"] == ["p05", "p50", "p95"] and coast[("orderly_1_5c", "2030")]["gap"] is None
    storm = {(c["scenario"], c["horizon"]): c for c in body["storm"]["cells"]}                   # the future set: 2030 only
    assert storm[("hot_house_3_5c", "2030")]["gap"] is None and "SSP5-8.5" in storm[("hot_house_3_5c", "2030")]["placement"]["detail"]["what"]
    assert storm[("orderly_1_5c", "2050")]["gap"]["code"] == "loss.gap.beyond_warming" and len(body["storm"]["members"]) == 4


def test_a_projected_run_carries_the_same_sources_today(api):
    h = _login(api, *ADMIN)
    run_id = engine.run(api.s, _org(api), "banking", "disorderly_2c", "2050")["run_id"]
    body = api.get(f"/v1/loss/runs/{run_id}", headers=h).json()
    assert body["run"]["scenario"] == "disorderly_2c" and body["run"]["time_horizon"] == "2050"
    assert all("eal_same_source_today_eur" in r and "model_eal" in r for r in body["results"])
    placed = body["run"]["inputs"]["layers"]["flood"]["placement"]           # where 2050 sits on the timeline
    assert (placed["lower"], placed["upper"]) == ("rcp4p5:2050", "rcp8p5:2050")
    m = body["placements"]["flood"]
    assert m["code"] == "loss.projection.between" and "RCP4.5 2050" in m["detail"]["what"] and "water depth" in m["detail"]["what"]

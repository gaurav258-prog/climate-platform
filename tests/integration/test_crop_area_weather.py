"""E163: weather over each crop's own growing area, one weather source for every calibration. Rolled back throughout.

  weights   the crop map's harvested area is placed on the ERA5-Land grid by country, none lost or doubled
  seasons   MIRCA-OS by its share rule (one unbroken run, else held); FAO-56 Table 11 rows exactly as the stored page
            prints them, applied only to the origins listed
  build     a box built from the global files gives the legacy regional file's seasonal SPEI, year by year
  recipes   every crop × origin the maps hold gets a recipe or a reason; a slot with a recipe keeps it
"""
from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from ml.features.drought import ERA5_BASELINE_DIR
from services.calibration import crop_area, crop_weather, seasons
from services.calibration import crop_area_weights as W

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
_HAS_MAPS = (ROOT / W.reference()["maps"]["mapspam2020"]["file"]).exists()


def _global_complete() -> bool:
    try:
        crop_weather._files()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _HAS_MAPS, reason="the crop maps are not on this machine")
def test_the_crop_map_area_is_placed_by_country():
    w = W.weights("Wheat")
    placed = sum(float(v[1].sum()) for v in w.values())
    a, _res = W._map_array("mapspam2020", "WHEA")
    assert 0.995 <= placed / a.sum() <= 1.0                       # cells off every country's polygon are the only loss
    top = sorted(w, key=lambda k: -float(w[k][1].sum()))[:4]
    assert set(top) == {"IN", "RU", "CN", "US"}
    for idx, wt in w.values():
        assert len(idx) == len(set(idx.tolist())) and (wt > 0).all()


def test_seasons_follow_their_sources():
    ma = seasons.mirca_season("Wheat", 504, ["Wheat1", "Wheat2"])
    assert (ma["months"], ma["prev_months"]) == ([1, 2, 3, 4, 5, 6], [12])
    assert "not one season" in seasons.mirca_season("Wheat", 356, ["Wheat1", "Wheat2"])["held"]
    it = seasons.fao56_season("Olive oil", "IT")
    assert (it["months"], it["prev_months"]) == (list(range(3, 12)), [])
    assert "held" in seasons.fao56_season("Olive oil", "PT") and "held" in seasons.fao56_season("Almonds", "ES")


def test_a_calendar_covering_a_minority_of_the_crop_is_held():
    """E168: MIRCA-OS lists 0.28 million ha of Canadian wheat (winter calendar only) against 9.6 million ha mapped."""
    ca = seasons.mirca_season("Wheat", 124, ["Wheat1", "Wheat2"], mapped_ha=9_639_400)
    assert "less than half" in ca["held"] and "9,639,400" in ca["held"]
    ma = seasons.mirca_season("Wheat", 504, ["Wheat1", "Wheat2"], mapped_ha=2_800_000)
    assert ma["months"] == [1, 2, 3, 4, 5, 6]


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.cell, self.on = [], None, False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th"):
            self.cell = ""

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.rows:
            self.rows[-1].append(" ".join(self.cell.split()))
            self.cell = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data


def test_the_fao56_rows_are_as_the_stored_page_prints_them():
    ref = seasons.reference()["fao56"]
    html = (ROOT / ref["file"]).read_text(encoding="latin-1")
    seg = html[html.index("TABLE 11."):html.index("TABLE 12.")]
    p = _Rows()
    p.feed(seg)
    rows = [r for r in p.rows if r]
    for crop, row in ref["crops"].items():
        stages = [str(d) for d in row["stages_days"]]
        month = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                 "November", "December"][row["start_month"] - 1]
        found = [r for r in rows if len(r) >= 7 and r[-1].startswith(row["region"]) and month.startswith(r[-2][:3])
                 and [re.sub(r"\D", "", c) for c in r[-7:-3]] == stages]
        assert found, f"{crop}: {row['row']} {row['region']} {stages} is not a row of the stored Table 11"
        printed_total = re.sub(r"\D", "", found[0][-3])
        assert printed_total.startswith(str(sum(row["stages_days"]))), crop      # a footnote mark may follow the total


@pytest.mark.skipif(not (_global_complete() and os.path.exists(ERA5_BASELINE_DIR / "spain_olive_1991_2024_monthly.nc")),
                    reason="the global and regional ERA5-Land files are not both on this machine")
def test_a_box_built_from_the_global_files_matches_its_regional_file(session_rolled_back):
    from ml.features.drought import baseline_nc, compute_indices, load_monthly, seasonal_by_year
    s = session_rolled_back
    bid = crop_weather.build(s, [], ["spain_olive", "morocco_wheat"])
    for box, months in (("spain_olive", [4, 5, 6, 7, 8]), ("morocco_wheat", [1, 2, 3, 4, 5, 6])):
        legacy = {r["year"]: r["spei"] for r in seasonal_by_year(compute_indices(load_monthly(baseline_nc(box)), scale=6), months)
                  if r["year"] <= 2024 and r["spei"] is not None}      # 1991 has no full season in either (E167)
        built = {y: round(v[0], 2) for y, v in crop_area.seasonal(crop_weather.monthly(s, bid, crop_weather.box_target(box)),
                                                                  months, []).items() if y <= 2024}
        assert built == legacy, box


@pytest.mark.skipif(not _HAS_MAPS, reason="the crop maps are not on this machine")
def test_every_mapped_origin_gets_a_recipe_or_a_reason(session_rolled_back):
    from sqlalchemy import text

    from services.calibration import registry_specs
    s = session_rolled_back
    legacy = s.execute(text("""SELECT spec_id::text FROM crop_calibration_specs WHERE commodity = 'Wheat' AND origin = 'MA'
                               AND retired_at IS NULL""")).scalar()
    registry_specs.generate(s)
    rows = s.execute(text("SELECT commodity, origin, status, reason, spec_id::text FROM crop_calibration_coverage")).mappings().all()
    assert all((r["status"] == "recipe") == (r["reason"] is None) for r in rows)
    by = {(r["commodity"], r["origin"]): r for r in rows}
    from ml.features.crop_registry import crops
    assert set(by) == {(c["commodity"], o) for c in crops() if c.get("crop_map") for o in W.weights(c["commodity"])}
    if legacy:
        assert by[("Wheat", "MA")]["spec_id"] == legacy                 # a slot with a recipe keeps it
    assert by[("Almonds", "ES")]["status"] in ("no_season", "no_yield_series")
    gen = s.execute(text("""SELECT weather_kind, weather_key, spei_scale, driver FROM crop_calibration_specs
                            WHERE basis LIKE 'generated by%' LIMIT 1""")).mappings().first()
    assert gen and (gen["weather_kind"], gen["spei_scale"], gen["driver"]) == ("crop_area", 6, "drought")


@pytest.mark.skipif(not _HAS_MAPS, reason="the crop maps are not on this machine")
def test_a_generated_recipe_that_no_longer_stands_is_retired(session_rolled_back):
    """E168: a generated recipe whose season the reference no longer states is retired with the reason, its proposal
    withdrawn, and the slot generated afresh — never kept because it was there first."""
    from sqlalchemy import text

    from services.calibration import publish, registry_specs, runner, specs
    s = session_rolled_back
    slot = s.execute(text("""SELECT spec_id::text, commodity, origin FROM crop_calibration_specs
                             WHERE retired_at IS NULL AND weather_kind = 'crop_area' AND yield_region = ''
                             ORDER BY commodity, origin LIMIT 1""")).mappings().first()
    if not slot or not crop_weather.latest(s, crop_weather.crop_target(slot["commodity"], slot["origin"])):
        pytest.skip("no generated recipe with a weather build on this database")
    good = s.execute(text("SELECT season_months, season_prev_months, yield_source, weather_key, driver, allow_cycle "
                          "FROM crop_calibration_specs WHERE spec_id = CAST(:i AS uuid)"), {"i": slot["spec_id"]}).mappings().one()
    registry_specs.retire(s, slot["spec_id"], "test: replaced by a recipe with a wrong season")
    wrong = specs.create(s, commodity=slot["commodity"], origin=slot["origin"], weather_kind="crop_area",
                         yield_source=good["yield_source"], driver=good["driver"], weather_key=good["weather_key"],
                         season_months=[1], season_prev_months=[], allow_cycle=good["allow_cycle"],
                         basis="generated by test: a season no source states", protocol="test")
    run = runner.run(s, next(sp for sp in runner.active_specs(s) if sp["spec_id"] == wrong))
    publish.propose(s, [run["run_id"]], "test")
    out = registry_specs.generate(s)
    assert out["retired"] >= 1
    spec = s.execute(text("SELECT retired_at, retired_reason FROM crop_calibration_specs WHERE spec_id = CAST(:i AS uuid)"),
                     {"i": wrong}).mappings().one()
    assert spec["retired_at"] is not None and "season_months [1] →" in spec["retired_reason"]
    r = s.execute(text("SELECT status, decision_reason FROM crop_calibration_runs WHERE run_id = CAST(:i AS uuid)"),
                  {"i": run["run_id"]}).mappings().one()
    assert r["status"] == "superseded" and r["decision_reason"].startswith("recipe retired before a decision")
    now = s.execute(text("""SELECT season_months, season_prev_months FROM crop_calibration_specs WHERE retired_at IS NULL
                            AND commodity = :c AND origin = :o AND yield_region = ''"""),
                    {"c": slot["commodity"], "o": slot["origin"]}).mappings().one()
    assert (sorted(now["season_months"]), sorted(now["season_prev_months"])) == \
        (sorted(good["season_months"]), sorted(good["season_prev_months"]))

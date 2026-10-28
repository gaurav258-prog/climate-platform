"""European windstorm in the loss engine (the product owner's decisions of 2026-10-25): the Prahl et al. (2015) curve as
its equations and Table A1 print it, the gust maps read from the PRIMAVERA event set as the cyclone maps are read, no
country served by both wind hazards, and an event set's address naming its own record (E347)."""
from __future__ import annotations

import json
import tarfile

import numpy as np
import pytest

from scripts import build_prahl_family as B
from services.loss import curves, registry
from services.loss import windstorm_events as W

# ── the curve ──────────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_curve_file_holds_exactly_the_printed_equation_s_points():
    c = curves.families()["prahl_2015_h"]["curves"][0]
    central, low, high = B.curve_points()
    assert c["points"] == central and c["range_points"]["low"] == low and c["range_points"]["high"] == high
    f = c["form"]
    assert (f["H4"], f["H3"], f["H2"], f["H1"]) == (42.3, 2.0, 6.2, 49.7)        # Table A1, absolute gust, DWD, p. 786


def test_the_closed_form_equals_the_convolution_of_eq_a16():
    for v in (30, 40, 50, 60, 80):
        x = np.linspace(42.3 - 12 * 6.2, v, 400001)
        f = np.exp(-0.5 * ((x - 42.3) / 6.2) ** 2) / (6.2 * np.sqrt(2 * np.pi))
        g = np.where(v - x >= 49.7, 1.0, ((v - x) / 49.7) ** 2)
        assert B.loss_ratio(v, 42.3, 6.2) == pytest.approx(float(np.trapezoid(g * f, x)), rel=1e-6)


def test_the_central_curve_is_eq_a17_s_expected_loss_ratio_over_the_critical_gust_s_spread():
    mus = np.linspace(42.3 - 10 * 2.0, 42.3 + 10 * 2.0, 4001)
    w = np.exp(-0.5 * ((mus - 42.3) / 2.0) ** 2)
    w /= w.sum()
    for v in (35, 45, 55):
        mean = sum(B.loss_ratio(v, m, 6.2) * wi for m, wi in zip(mus, w))
        assert mean == pytest.approx(B.loss_ratio(v, 42.3, (6.2 ** 2 + 2.0 ** 2) ** 0.5), rel=1e-4)


def test_the_curve_serves_german_homes_only():
    assert curves.curve_for("prahl_2015_h", "residential", "DE")["key"] == "prahl_2015_h:residential:DE"
    assert curves.curve_for("prahl_2015_h", "commercial", "DE") is None
    assert curves.curve_for("prahl_2015_h", "residential", "FR") is None


def test_a_published_range_must_hold_its_central_curve():
    doc = json.loads(json.dumps(curves.families()["prahl_2015_h"]))
    doc["curves"][0]["range_points"]["high"][50][1] = 0.0
    assert any("low ≤ central ≤ high" in p for p in curves.check_family(doc))
    del doc["curves"][0]["range_points"]
    assert any("published spread" in p for p in curves.check_family(doc))      # spread_required: say which


def test_no_country_is_served_by_both_wind_hazards():
    fams = curves.families()
    assert curves.wind_overlap(fams) == {}
    cyclone = json.loads(json.dumps(fams["eberenz_2021_rmsf"]))
    cyclone["family"] = "cyclone_test"
    cyclone["curves"][0]["countries"] = [*cyclone["curves"][0]["countries"], "DE"]
    out = curves.wind_overlap({"cyclone_test": cyclone, "prahl_2015_h": fams["prahl_2015_h"],
                               "eberenz_2021_tdr": fams["eberenz_2021_tdr"]})
    assert set(out) == {"cyclone_test", "prahl_2015_h"}                         # both refused; two cyclone families fine
    assert "DE" in out["prahl_2015_h"][0] and "DE" in out["cyclone_test"][0]


def test_the_windstorm_family_reads_the_gust_maps_own_measure():
    fam = curves.families()["prahl_2015_h"]
    L = registry.layer(W.LAYER)
    assert (fam["peril"], fam["metric"], fam["unit"]) == (L["peril"], L["metric"], L["unit"])
    assert registry.divisor(W.LAYER, fam["metric"]) == 1.0


# ── an event set's address (E347) ──────────────────────────────────────────────────────────────────────────────────

def test_an_event_set_s_address_must_name_its_own_record_e347(monkeypatch):
    assert registry.doi_record("10.4121/14237678.v1") == "14237678"
    assert registry.doi_record("10.5281/zenodo.6492182") == "6492182"
    assert registry.check() == []
    sets = json.loads(json.dumps(registry.event_sets()))
    sets["primavera_windstorm"]["url"] = "https://zenodo.org/records/1234567"     # a Zenodo address, another record
    monkeypatch.setattr(registry, "event_sets", lambda: sets)
    assert any(p.startswith("event set primavera_windstorm") and "6492182" in p for p in registry.check())


# ── the event set read into gust maps ──────────────────────────────────────────────────────────────────────────────

LAT, LON = np.array([50.25, 50.0]), np.array([8.0, 8.25])


def _footprint(path, gust: np.ndarray) -> None:
    import netCDF4
    d = netCDF4.Dataset(path, "w")
    d.createDimension("latitude", 2)
    d.createDimension("longitude", 2)
    d.createDimension("bnds", 2)
    for name, vals in (("latitude", LAT), ("longitude", LON)):
        d.createVariable(name, "f8", (name,))[:] = vals
        d.createVariable(f"{name}_bnds", "f8", (name, "bnds"))[:] = np.stack([vals - 0.125, vals + 0.125], axis=1)
    g = d.createVariable("corrected_gust", "f4", ("latitude", "longitude"))
    g.units = "m s-1"
    g[:] = gust
    d.license = "a test licence"
    d.close()


def _archive(tmp, run: str, winters: dict[str, list[np.ndarray]]) -> None:
    """One run's archive as published: <run>.tar holding <run>/<run>.tar.gz of the footprints."""
    nc = tmp / "nc"
    nc.mkdir(exist_ok=True)
    gz = tmp / f"{run}.tar.gz"
    with tarfile.open(gz, "w:gz") as t:
        for label, prints in winters.items():
            a, b = label.split("/")
            for i, g in enumerate(prints):
                name = f"{run}_winter{a}-{b}_DJF_storm{i}_{a}-12-{i + 10}_regrid_corrected.nc"
                _footprint(nc / name, g)
                t.add(nc / name, arcname=f"{run}/{name}")
    with tarfile.open(tmp / f"{run}.tar", "w") as t:
        t.add(gz, arcname=f"{run}/{run}.tar.gz")


@pytest.fixture()
def tiny_set(tmp_path, monkeypatch):
    nan = -1.0                                                                   # the files' not-held marker
    _archive(tmp_path, "run_a", {"2000/2001": [np.array([[20, nan], [30, nan]]), np.array([[25, 10], [nan, nan]])],
                                 "2001/2002": [np.array([[40, 12], [nan, 22]])]})
    _archive(tmp_path, "run_b", {"2000/2001": [np.array([[18, 11], [33, nan]])]})
    sets = {W.KEY: {"runs": ["run_a", "run_b"], "years_simulated": 3, "variable": "corrected_gust", "units": "m s-1",
                    "licence": "test", "version": "v1",
                    "files": {"archives": str(tmp_path), "inner": "{run}/{run}.tar.gz"}}}
    monkeypatch.setattr(registry, "event_sets", lambda: sets)
    monkeypatch.setattr(W, "COMPACT", tmp_path / "compact" / "winter_max.npz")
    recorded = {}
    import scripts.fetch_supply_datasets as S
    monkeypatch.setattr(S, "record", lambda key, entry: recorded.update({key: entry}))
    W._held.cache_clear()
    yield tmp_path, sets, recorded
    W._held.cache_clear()


def test_each_winter_holds_its_highest_gust_and_a_point_no_storm_reaches_counts_as_zero(tiny_set):
    _tmp, _sets, recorded = tiny_set
    out = W.compact()
    z = np.load(W.COMPACT)
    am = z["winter_max"]
    assert list(z["winter"]) == ["2000/2001", "2001/2002", "2000/2001"] and list(z["run"]) == ["run_a", "run_a", "run_b"]
    assert am[0].tolist() == [[25, 10], [30, 0]]          # max of the winter's footprints; never reached → 0
    assert am[1].tolist() == [[40, 12], [0, 22]] and am[2].tolist() == [[18, 11], [33, 0]]
    for k, rp in enumerate(z["rp_years"]):
        assert np.allclose(z["rp_level"][k], np.quantile(am, 1 - 1 / rp, axis=0))
    assert out["runs"]["run_a"] == {"footprints": 3, "winters": 2, "central_date_outside_oct_mar": 0,
                                    "file_licence_attribute": ["a test licence"]}
    assert recorded[f"{W.KEY}_compact"]["files"][0]["sha256"] == out["sha256"]


def test_a_location_reads_the_grid_cell_holding_it_and_off_the_grid_is_outside(tiny_set):
    W.compact()
    rows = W.rows(50.1, 8.3)                               # latitude 50.0 ± 0.125, longitude 8.25 ± 0.125
    z = np.load(W.COMPACT)
    assert [r["status"] for r in rows] == ["sampled"] * len(rows)
    assert [r["value"] for r in rows] == pytest.approx([float(v) for v in z["rp_level"][:, 1, 1]])
    assert [r["rp_years"] for r in rows] == registry.layer(W.LAYER)["return_periods"]
    assert {r["status"] for r in W.rows(60.0, 8.0)} == {"outside_coverage"}


def test_a_winter_count_other_than_the_event_set_s_stops_the_build(tiny_set):
    _tmp, sets, _r = tiny_set
    sets[W.KEY]["years_simulated"] = 4
    with pytest.raises(ValueError, match="3 winters held"):
        W.compact()


def test_a_negative_gust_other_than_the_not_held_marker_stops_the_build(tiny_set):
    tmp, _sets, _r = tiny_set
    _archive(tmp, "run_b", {"2000/2001": [np.array([[18, -2], [33, 1]])]})
    with pytest.raises(ValueError, match="not-held marker"):
        W.compact()

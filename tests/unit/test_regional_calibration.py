"""Regional crop calibrations (calibration_protocol.json 'regional'): which calibration a plot reads, the damage-sign
gate (E327), the staging printout (E328) and the IBGE reader. Pure — no database."""
from __future__ import annotations

import json

import pytest

from services.calibration import gates
from services.intelligence.regional_calibration import cal_of, key_of, weakest_tier
from services.intelligence.supply_cogs import _commodity_risk

FIT = {"slope": -1.0, "intercept": 40.0, "rmse": 8.0, "r2": 0.6, "score_mean": 50.0, "score_sxx": 9000.0,
       "n_years": 16, "r2_oos": 0.55, "band_cov68": 0.7}
HELD = {**FIT, "slope": -0.2, "r2_oos": 0.10}


def _cal(tier: str, fit: dict | None, share: float | None = None) -> dict:
    return {"sensitivity": None, "world_share": share, "hazard_driver": "drought", "calibration_tier": tier, "fit": fit}


ORIGIN_CAL = {"ES": _cal("indicative", HELD, 0.02), "ES24": _cal("ranged", FIT), "ES41": _cal("indicative", HELD)}


def test_a_plot_reads_its_region_only_where_the_region_publishes():
    inside = {"origin": "ES", "region": "ES24"}
    held_region = {"origin": "ES", "region": "ES41"}
    no_region = {"origin": "ES", "region": None}
    other = {"origin": "ES", "region": "ES61"}
    assert key_of(ORIGIN_CAL, inside) == "ES24" and cal_of(ORIGIN_CAL, inside)["calibration_tier"] == "ranged"
    # a held region never stands in for its country — the plot reads the country's calibration
    assert key_of(ORIGIN_CAL, held_region) == "ES" and cal_of(ORIGIN_CAL, held_region) is ORIGIN_CAL["ES"]
    assert key_of(ORIGIN_CAL, no_region) == "ES" and key_of(ORIGIN_CAL, other) == "ES"
    assert cal_of(None, inside) is None


def test_the_weakest_plot_sets_its_origins_tier():
    assert weakest_tier(["ranged", "ranged"]) == "ranged"
    assert weakest_tier(["ranged", "indicative"]) == "indicative"
    assert weakest_tier(["backtested", "ranged"]) == "ranged"
    assert weakest_tier([None]) == "uncalibrated" and weakest_tier([]) == "uncalibrated"


def test_a_regional_fit_gives_a_figure_only_to_its_own_plots():
    """A country held nationally, one region passing: plots inside the region get the region's loss range; a book with
    a plot elsewhere in the country has no yield shock for that origin (never a partial average)."""
    inside = {"spend": 100.0, "origin": "ES", "region": "ES24", "hazards": {"drought": 80.0}}
    outside = {"spend": 100.0, "origin": "ES", "region": "ES61", "hazards": {"drought": 80.0}}
    only_inside = _commodity_risk("Barley", False, 100.0, [inside], origin_cal=ORIGIN_CAL)
    o = only_inside.origins[0]
    assert o["origin"] == "ES" and o["regions"] == ["ES24"] and o["calibration"] == "ranged"
    assert o["yield_shock_pct"] == pytest.approx(-(40.0 - 80.0), abs=0.1)        # the regional line's mid at 80
    assert o["world_share"] == 0.02                                               # the country's share, never a region's
    mixed = _commodity_risk("Barley", False, 200.0, [inside, outside], origin_cal=ORIGIN_CAL)
    assert mixed.origins[0]["calibration"] == "indicative"


def test_e327_a_fit_where_more_hazard_means_more_yield_never_passes():
    floor = gates.RANGED_PUBLISH_FLOOR
    assert gates.downside(floor + 0.1, -0.5)
    assert not gates.downside(floor + 0.1, 0.3)           # cleared the floor, wrong direction: held
    assert not gates.downside(floor + 0.1, 0.0) and not gates.downside(floor + 0.1, None)
    assert not gates.downside(floor - 0.01, -0.5)
    assert gates.publishes is gates.downside              # one rule for every reader of a stored fit


def test_e328_the_staging_printout_reads_the_set_aside_counts():
    from scripts.stage_yield_release import set_aside_lines
    from services.reference.yield_sources import SetAside
    a = SetAside()
    a.add("not_published", why="not available")
    a.add("not_published", why="not available")
    a.add("area_only")
    lines = set_aside_lines(a.counts())
    assert len(lines) == 2 and any(line.endswith(": 2") and "not available" in line for line in lines)


def _sidra(product: str, label: str, rows: list[tuple]) -> list[dict]:
    head = {"D1C": "Unidade da Federação (Código)"}
    return [head] + [{"D1C": uf, "D1N": "x", "D2C": var, "D3C": str(year), "D4C": product, "D4N": label, "MN": unit,
                      "V": v} for uf, var, year, unit, v in rows]


def test_the_ibge_reader_reads_tonnes_and_hectares_and_refuses_anything_else():
    from services.reference import ibge_pam as I
    from services.reference.publisher_errors import PublisherError
    ufs = {"43": "BR-RS", "41": "BR-PR"}
    rows = [("43", "214", 2021, "Toneladas", "20000000"), ("43", "216", 2021, "Hectares", "6000000"),
            ("43", "214", 2022, "Toneladas", "9000000"), ("43", "216", 2022, "Hectares", "6000000"),
            ("41", "214", 2022, "Toneladas", "-"), ("41", "216", 2022, "Hectares", "...")]
    data = json.dumps({"1612/2713": _sidra("2713", "Soja (em grão)", rows)}).encode()
    got = {(r["region_code"], r["season_year"]): r for r in I.parse(data, ufs)}
    assert set(got) == {("BR-RS", 2021), ("BR-RS", 2022)}
    assert got[("BR-RS", 2022)]["yield_tonnes_ha"] == 1.5 and got[("BR-RS", 2022)]["yoy_change_pct"] == -55.0
    assert sum(a["rows"] for a in I.set_aside(data, ufs)) == 2
    for bad in (_sidra("2713", "Soja (em grão)", [("43", "214", 2021, "Mil frutos", "5")]),
                _sidra("2713", "Soja", [("43", "214", 2021, "Toneladas", "5")]),
                _sidra("2713", "Soja (em grão)", [("99", "214", 2021, "Toneladas", "5")])):
        I._read.cache_clear()
        with pytest.raises(PublisherError):
            I.parse(json.dumps({"1612/2713": bad}).encode(), ufs)


def test_e330_the_crop_coverage_routes_load_shapely_at_import():
    """The coverage page asks for the countries and the regions at once; each route used to import shapely on first use,
    and two first imports in two threads raced ('partially initialized module shapely'). Importing the router loads it."""
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-c", "import sys, api.routers.supply; print('shapely' in sys.modules)"],
                         capture_output=True, text=True, timeout=300)
    assert out.stdout.strip().endswith("True"), out.stderr[-500:]

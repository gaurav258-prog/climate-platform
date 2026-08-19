"""Pillar 3 transition Templates 3 & 4 (ITS 2022/2453, Annex XL) — the IEA-alignment distance + top-20 match."""
from services.governance.transition_alignment import (
    CARBON_MAJORS_TOP20,
    IEA_NZE2050,
    _iea_sector,
    template3_grid,
    template4_top20,
)


def _a(nace, val, name="Co", intensity=None):
    d = {"nace_code": nace, "value_eur": val, "asset_name": name}
    if intensity is not None:
        d["emission_intensity"] = intensity
    return d


def test_nace_to_iea_sector_mapping():
    assert _iea_sector("35.11") == "power"        # electricity
    assert _iea_sector("50.20") == "maritime"     # water transport
    assert _iea_sector("23.51") == "cement"       # non-metallic minerals
    assert _iea_sector("24.10") == "iron_steel"   # basic metals
    assert _iea_sector("05.10") == "coal"         # coal mining
    assert _iea_sector("62.01") is None           # software — no IEA transition sector


def test_template3_distance_matches_its_formula():
    # ITS §39 worked example: maritime current 28.8 gCO2/MJ vs IEA NZE2050 2030 target 23.4 → 23%
    assert IEA_NZE2050["maritime"]["target_2030"] == 23.4
    g = template3_grid([_a("50.20", 1000, intensity=28.8)])
    row = next(r for r in g["rows"] if r["sector"] == "maritime")
    assert row["current_intensity"] == 28.8 and row["iea_2030"] == 23.4
    assert row["distance_pct"] == 23.1            # 100*((28.8-23.4)/23.4) = 23.076..→23.1
    assert row["gross"] == 1000


def test_template3_pending_when_no_benchmark_or_no_intensity():
    # power has no citable IEA target yet (pending ingest) → distance stays None even with an intensity
    g = template3_grid([_a("35.11", 500, intensity=400)])
    row = next(r for r in g["rows"] if r["sector"] == "power")
    assert row["iea_2030"] is None and row["distance_pct"] is None
    # cement with a benchmark but NO provided intensity → current + distance None (not fabricated)
    g2 = template3_grid([_a("23.51", 300)])
    row2 = next(r for r in g2["rows"] if r["sector"] == "cement")
    assert row2["current_intensity"] is None and row2["distance_pct"] is None and row2["gross"] == 300


def test_template4_top20_match_by_name():
    assets = [_a("06.10", 900, name="Saudi Aramco Refining SA"),
              _a("35.11", 100, name="Valencia Energy 33")]      # fictional → no match
    g = template4_top20(assets)
    assert g["matched_count"] == 1 and g["total_exposure"] == 900
    assert g["rows"][0]["firm"] == "Saudi Aramco"
    assert g["list_size"] == len(CARBON_MAJORS_TOP20) == 20

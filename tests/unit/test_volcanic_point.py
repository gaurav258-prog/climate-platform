"""Any-address volcanic screening: pure physics + catalogue scorer, no DB / no network."""
import json
from pathlib import Path

import pytest

from core.hazard_taxonomy import EXTRA_CHANNELS, MaturityTier
from ml.scoring.volcanic_physics import (
    ashfall_score,
    blended_volcanic_score,
    proximal_score,
    vei_to_zone_radii,
)
from ml.scoring.volcanic_point import INFLUENCE_KM, volcanic_exposure
from scripts.fetch_gvp_catalogue import build_catalogue

CAT = Path(__file__).resolve().parents[2] / "data" / "reference" / "gvp_holocene_volcanoes.json"


def _vol(n, name, lat, lon, vei=None, last=None, n1900=0):
    return {"volcano_number": n, "name": name, "lat": lat, "lon": lon, "max_vei": vei,
            "last_eruption_year": last, "n_eruptions_since_1900": n1900, "country": "X", "type": "Stratovolcano"}


def test_physics_monotone_and_bounded():
    r_p, r_a = vei_to_zone_radii(4)
    assert (r_p, r_a) == (8.0, 40.0)
    assert vei_to_zone_radii(6) == (16.0, 80.0)          # +2 VEI doubles the radius
    ds = [0, 2, 5, 10, 20, 50, 100, 150]
    prox = [float(proximal_score(d, r_p)) for d in ds]
    ash = [float(ashfall_score(d, r_a)) for d in ds]
    assert prox == sorted(prox, reverse=True) and ash == sorted(ash, reverse=True)
    assert all(0.0 <= x <= 100.0 for x in prox + ash)
    b, p, a = blended_volcanic_score(1.0, r_p, r_a)
    assert b == max(p, a) and b > 95


def test_worst_volcano_wins_and_radii_source_is_disclosed():
    vols = [_vol(1, "Big", 10.0, 10.0, vei=5.0), _vol(2, "Unknown", 10.3, 10.0, vei=None), _vol(3, "Far", 30.0, 10.0, vei=7.0)]
    out = volcanic_exposure(10.05, 10.0, vols)
    assert out["shap"]["volcano"] == "Big" and out["shap"]["radii_source"] == "vei_scaled_from_catalogue"
    assert out["shap"]["vei_reference"] == 5.0 and out["shap"]["volcanoes_within_influence"] == 2
    assert out["shap"]["tier"] == "screening" and out["risk_score"] > 90
    out2 = volcanic_exposure(10.32, 10.0, vols)
    assert out2["shap"]["volcano"] == "Unknown" and out2["shap"]["radii_source"] == "vei_unknown_default3"
    assert out2["shap"]["vei_reference"] is None


def test_curated_zone_overrides_vei_default():
    vols = [_vol(9, "Mapped", 0.0, 0.0, vei=2.0)]
    default = volcanic_exposure(0.0, 0.2, vols)["risk_score"]
    curated = volcanic_exposure(0.0, 0.2, vols, curated=lambda n: (30.0, 120.0, "curated:paper-X"))
    assert curated["shap"]["radii_source"] == "curated:paper-X" and curated["risk_score"] > default


def test_no_volcano_in_range_is_a_zero_answer_not_missing_data():
    vols = [_vol(1, "Lonely", 0.0, 0.0, vei=4.0)]
    out = volcanic_exposure(0.0, 1.0, vols)          # ~111 km: in range, low score
    assert 0 < out["risk_score"] < 20
    out = volcanic_exposure(0.0, 1.4, vols)          # ~156 km: beyond INFLUENCE_KM
    assert out["risk_score"] == 0.0 and out["shap"]["reason"] == f"no Holocene volcano within {INFLUENCE_KM:.0f} km"
    assert out["shap"]["nearest_volcano"] == "Lonely"


def test_build_catalogue_only_counts_confirmed_eruptions():
    volcs = [{"properties": {"Volcano_Number": 1, "Volcano_Name": "A", "Country": "C", "Region": "R",
                             "Primary_Volcano_Type": "Caldera", "Last_Eruption_Year": 1991},
              "geometry": {"type": "Point", "coordinates": [120.35, 15.13]}}]
    erup = [{"properties": {"Volcano_Number": 1, "Activity_Type": "Confirmed Eruption", "ExplosivityIndexMax": 6, "StartDateYear": 1991}},
            {"properties": {"Volcano_Number": 1, "Activity_Type": "Confirmed Eruption", "ExplosivityIndexMax": None, "StartDateYear": 1500}},
            {"properties": {"Volcano_Number": 1, "Activity_Type": "Uncertain Eruption", "ExplosivityIndexMax": 8, "StartDateYear": 1800}}]
    cat = build_catalogue(volcs, erup)
    v = cat["volcanoes"][0]
    assert (v["lat"], v["lon"]) == (15.13, 120.35)
    assert v["n_confirmed_eruptions"] == 2 and v["n_eruptions_since_1900"] == 1
    assert v["max_vei"] == 6.0 and v["max_vei_since_1900"] == 6.0
    assert cat["n_eruptions_confirmed"] == 2


@pytest.mark.skipif(not CAT.exists(), reason="GVP catalogue not landed")
def test_landed_catalogue_is_global_and_sane():
    cat = json.loads(CAT.read_text())
    assert cat["n_volcanoes"] >= 1000 and "Smithsonian" in cat["source"]
    by_name = {v["name"]: v for v in cat["volcanoes"]}
    assert by_name["Etna"]["country"] == "Italy" and by_name["Etna"]["max_vei"] is not None
    naples = volcanic_exposure(40.85, 14.27, cat["volcanoes"])
    berlin = volcanic_exposure(52.52, 13.40, cat["volcanoes"])
    assert naples["risk_score"] > 50 and berlin["risk_score"] == 0.0


def test_taxonomy_row_is_screening_with_real_disclosure():
    row = next(h for h in EXTRA_CHANNELS if h.id == "volcanic")
    assert row.tier == MaturityTier.SCREENING and "GVP" in row.source and "never a €" in row.source

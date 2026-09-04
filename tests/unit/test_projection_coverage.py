"""The projection-posture map must declare a forward mechanism for EVERY hazard the engine scores — no peril
silently undeclared — and must stay grounded in the real engine sensitivities (no drifted duplicate numbers)."""
from __future__ import annotations

from ml.scoring.physical_projection import SENSITIVITY
from ml.scoring.projection_coverage import projection_coverage
from services.scoring.on_demand import SYNC_ON_DEMAND_SCORERS


def test_every_scored_hazard_has_a_declared_projection_posture():
    cov = {it["hazard"] for it in projection_coverage()["items"]}
    # every on-demand-scored peril must appear in the projection map (plus flood/storm/wildfire from the batch engine)
    for hz in SYNC_ON_DEMAND_SCORERS:
        assert hz in cov, f"{hz} is scored but has no declared projection posture"
    for hz in ("flood", "storm", "wildfire"):
        assert hz in cov


def test_flat_by_design_are_only_the_geophysical_and_susceptibility():
    flat = {it["hazard"] for it in projection_coverage()["items"] if not it["projects"]}
    # geophysical (no climate response) + present-state susceptibility/environment layers that don't project
    # forward by scenario: terrain/ground-failure predisposition, periglacial state, marine pH, convective env.
    assert flat == {
        "seismic", "volcanic", "landslide", "subsidence", "permafrost", "solifluction",
        "avalanche", "glacial_lake_outburst", "soil_erosion", "soil_degradation",
        "ocean_acidification", "severe_convective",
    }


def test_climate_perils_project_and_key_ones_carry_a_band():
    items = {it["hazard"]: it for it in projection_coverage()["items"]}
    for hz in ("flood", "storm", "wildfire", "coastal_flood", "heavy_precip", "frost", "drought", "soil_water"):
        assert items[hz]["projects"] is True
    for hz in ("flood", "storm", "wildfire", "coastal_flood"):   # CMIP6 / AR6 carry a real spread band
        assert items[hz]["band"] is True


def test_frost_projects_downward_honest_inverse():
    frost = next(it for it in projection_coverage()["items"] if it["hazard"] == "frost")
    assert frost["mode"] == "parametric_warming_inverse"


def test_grounded_in_engine_sensitivities_not_redrifted():
    # the flood mechanism text must reflect the ACTUAL SENSITIVITY constant, so the map can't drift
    flood = next(it for it in projection_coverage()["items"] if it["hazard"] == "flood")
    assert f"{SENSITIVITY['flood'].per_c*100:.0f}%/°C" in flood["mechanism"]

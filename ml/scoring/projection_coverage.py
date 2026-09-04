"""Projection posture — the single, auditable statement of HOW each hazard is projected forward in time.

Forward projection is built across many scorers (each peril carries the mechanism appropriate to its physics);
this module is the one place that declares, per hazard, WHICH forward mechanism applies, its cited basis, and
any disclosed follow-on gap. It is the projection analog of the hazard-coverage map: coverage says whether we
score a hazard; this says whether — and how honestly — we project it to 2030/2050/2100.

Grounded, not re-typed: the flood/storm/wildfire elasticities are imported from `physical_projection.SENSITIVITY`
and the extreme-precip rate from `heavy_precip_climatology.CC_PER_C`, so the map cannot drift from the engine.
A `flat` posture is a deliberate, honest choice (a geophysical hazard has no climate response; a terrain
susceptibility is not a triggering nowcast), never an omission — stated as such so a reviewer sees the reasoning.
"""
from __future__ import annotations

from ml.scoring.heavy_precip_climatology import CC_PER_C
from ml.scoring.physical_projection import PROJECTION_VERSION, SENSITIVITY

PROJECTION_COVERAGE_VERSION = "proj-cov-v1"

# scenario × horizon axis the whole engine shares (canonical_scores.scenario / time_horizon)
SCENARIOS = ["baseline", "orderly_1_5c", "disorderly_2c", "hot_house_3_5c"]
HORIZONS = ["current", "2030", "2050", "2100"]

# mode → what the reader should understand by it
_MODE_LABEL = {
    "cmip6_band": "CMIP6 per-cell warming/precip change, with an across-model band",
    "parametric_cc": "parametric Clausius–Clapeyron warming shift",
    "parametric_warming": "parametric per-°C warming shift (NGFS scenario archetype)",
    "parametric_warming_inverse": "parametric per-°C warming shift — hazard FALLS with warming",
    "ar6_slr_band": "IPCC AR6 global-mean sea-level rise, with a likely-range band",
    "geophysical_flat": "no climate response — flat by design (geophysical)",
    "susceptibility_flat": "terrain susceptibility — flat by design (predisposition, not a triggering nowcast)",
    "projection_channel": "the channel IS a projection — only meaningful under a forward scenario",
    "variability": "interannual-variability channel — parametric widening under warming",
}


def _entry(hazard, mode, mechanism, basis, band=False, gaps=None):
    projects = mode not in ("geophysical_flat", "susceptibility_flat")
    return {"hazard": hazard, "projects": projects, "mode": mode, "mode_label": _MODE_LABEL[mode],
            "mechanism": mechanism, "basis": basis, "band": band, "gaps": gaps or []}


def projection_coverage() -> dict:
    """The per-hazard forward-projection posture — a static registry (no tenant data)."""
    fl, st, wf = SENSITIVITY["flood"], SENSITIVITY["storm"], SENSITIVITY["wildfire"]
    items = [
        _entry("flood", "cmip6_band", f"extreme-rainfall intensity ~{fl.per_c*100:.0f}%/°C of local warming",
               fl.basis, band=True, gaps=["mean-precip and coastal terms deliberately excluded (separate mechanisms)"]),
        _entry("storm", "cmip6_band", f"peak intensity ~{st.per_c*100:.0f}%/°C; severity scaled, not counts",
               st.basis, band=True),
        _entry("wildfire", "cmip6_band", f"fire weather ~{wf.per_c*100:.0f}%/°C warming plus a drying term",
               wf.basis, band=True),
        _entry("coastal_flood", "ar6_slr_band", "freeboard vs projected global-mean sea-level rise",
               "IPCC AR6 WG1 Ch.9/SPM global-mean SLR vs 1995–2014", band=True,
               gaps=["regional SLR variation + local land subsidence are disclosed follow-ons (v1 = global-mean)"]),
        _entry("heavy_precip", "parametric_cc", f"extreme-precip total intensified by (1+{CC_PER_C:.2f})^ΔT",
               "Clausius–Clapeyron ~7%/°C (IPCC AR6 WG1 Ch.11)"),
        _entry("frost", "parametric_warming_inverse", "warming raises the coldest night → fewer frost events",
               "IPCC AR6 WG1 Ch.11 (frost-day decline with warming)"),
        _entry("heat_acute", "parametric_warming", "acute-heat exceedance rises with the per-°C warming shift",
               "parametric NGFS-archetype ΔT (heat_climatology)"),
        _entry("heat_chronic", "parametric_warming", "chronic-heat load rises with the per-°C warming shift",
               "parametric NGFS-archetype ΔT (heat_climatology)"),
        _entry("drought", "parametric_warming", "aridity rises with the per-°C warming/drying shift",
               "parametric NGFS-archetype ΔT (drought_climatology)"),
        _entry("soil_water", "parametric_warming", "root-zone drying rises with the per-°C warming shift",
               "parametric NGFS-archetype ΔT + drying-per-°C (soil_water_climatology)"),
        _entry("temp_variability", "variability", "interannual temperature variability widens under warming",
               "climate_variability_point (parametric)"),
        _entry("precip_variability", "variability", "interannual precipitation variability widens under warming",
               "climate_variability_point (parametric)"),
        _entry("changing_temp", "projection_channel", "the projected warming trend itself (Δ vs baseline)",
               "climate_change_point (projection channel)"),
        _entry("changing_precip", "projection_channel", "the projected precipitation-trend itself (Δ vs baseline)",
               "climate_change_point (projection channel)"),
        _entry("changing_wind", "projection_channel", "the projected near-surface wind-speed trend itself (Δ vs baseline)",
               "climate_change_point (CMIP6 sfcWind projection channel)"),
        _entry("subsidence", "susceptibility_flat", "Global Subsidence Susceptibility is geophysical predisposition, not scenario-varying",
               "Herrera-García et al. (2021) susceptibility class; screening-tier predisposition"),
        _entry("coastal_erosion", "projection_channel", "projected shoreline retreat rises with the SLR scenario × horizon",
               "Vousdoukas et al. (2020, JRC LISCOAST) scenario × horizon retreat"),
        _entry("permafrost", "susceptibility_flat", "permafrost probability is a present physical state, not a scenario response",
               "Obu et al. (2019) permafrost probability (1 km, NH); screening-tier state"),
        _entry("soil_erosion", "susceptibility_flat", "GloSEM present-day soil-loss rate is a mapped state, not scenario-varying here",
               "GloSEM (Borrelli/Panagos) soil-loss rate; screening-tier (raster is an infra-scale fetch)"),
        _entry("saline_intrusion", "projection_channel", "intrusion susceptibility is amplified by the AR6 SLR at scenario × horizon",
               "low-elevation-coastal-zone × SLR proxy; screening-tier"),
        _entry("glacial_lake_outburst", "susceptibility_flat", "proximity to a mapped glacial lake is a present exposure, not scenario-varying here",
               "GIGLak glacial-lake proximity; screening-tier (a warming trend grows lakes — a disclosed follow-on)"),
        _entry("ocean_acidification", "susceptibility_flat", "surface-ocean pH climatology sampled as present state (marine assets only)",
               "OceanSODA-ETHZ surface pH; screening-tier marine layer"),
        _entry("avalanche", "susceptibility_flat", "terrain release-angle × snow-climate proxy is a present predisposition",
               "DEM slope × snow-climate proxy; screening-tier"),
        _entry("solifluction", "susceptibility_flat", "permafrost × gentle-slope periglacial setting is a present state",
               "permafrost probability × slope; screening-tier derived"),
        _entry("soil_degradation", "susceptibility_flat", "UNCCD SDG 15.3.1 degraded-land status is a mapped present state",
               "Trends.Earth SDG 15.3.1 (on-demand COG read); screening-tier"),
        _entry("severe_convective", "susceptibility_flat", "the ERA5 CAPE×shear climatology is a standing environment field",
               "ERA5 convective potential (Taszarek 2021); screening-tier (climatology is an infra build)"),
        _entry("seismic", "geophysical_flat", "earthquake hazard has no climate-scenario response",
               "geophysical — not climate-attributable"),
        _entry("volcanic", "geophysical_flat", "volcanic hazard has no climate-scenario response",
               "geophysical — not climate-attributable"),
        _entry("landslide", "susceptibility_flat", "NASA/LHASA terrain susceptibility does not vary by scenario",
               "screening-tier predisposition (slope/geology/roads); rainfall triggering is a disclosed follow-on"),
    ]
    n_proj = sum(1 for it in items if it["projects"])
    n_band = sum(1 for it in items if it["band"])
    return {
        "version": PROJECTION_COVERAGE_VERSION, "projection_engine_version": PROJECTION_VERSION,
        "scenarios": SCENARIOS, "horizons": HORIZONS,
        "n_hazards": len(items), "n_projected": n_proj,
        "n_flat_by_design": len(items) - n_proj, "n_with_band": n_band,
        "items": items,
        "note": ("How each hazard is carried forward to 2030/2050/2100. Climate-driven perils project by a "
                 "physically-grounded, cited mechanism (CMIP6 per-cell, Clausius–Clapeyron, AR6 sea-level rise, "
                 "or a parametric per-°C shift); geophysical perils and terrain susceptibility are flat by "
                 "design, stated as a choice, not an omission. 'band' marks where a real model/level "
                 "disagreement range is carried, not a false point."),
    }

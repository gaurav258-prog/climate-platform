"""The single definition of which hazards are climate-related (audit T8).

ESRS E1 (climate report) and the EU-Taxonomy climate-adaptation objective must scope the *same* asset
the same way: both cover climate-related physical hazards only. Seismic / volcanic / pollution are
geophysical, not climate-attributable, and belong to other risk lenses. Keeping this list in one place
means the two reports can never silently diverge on whether a given asset is materially exposed.
"""
from __future__ import annotations

# ACUTE = event-driven; CHRONIC = gradual. Their union is the climate-hazard scope.
# coastal_flood (sea-level rise) and frost (cold-wave) are climate-attributable temperature/sea
# extremes and are explicitly acute climate hazards under ESRS E1 AR.11 → ACUTE (NOT geophysical).
# heavy_precip (extreme rainfall) and landslide (rainfall-triggered mass movement) are acute EU-Taxonomy
# climate hazards; temperature/precipitation variability and the projected-change channels are chronic ones.
ACUTE = {"flood", "coastal_flood", "storm", "wildfire", "heat_acute", "frost", "heavy_precip", "landslide",
         "subsidence"}
CHRONIC = {"drought", "heat_chronic", "soil_water", "water_stress",
           "temp_variability", "precip_variability", "changing_temp", "changing_precip", "changing_wind",
           "coastal_erosion", "permafrost", "soil_erosion"}
CLIMATE = ACUTE | CHRONIC


def hazard_class(h: str) -> str:
    """acute | chronic | other — 'other' is a non-climate (geophysical/pollution) hazard."""
    return "acute" if h in ACUTE else "chronic" if h in CHRONIC else "other"

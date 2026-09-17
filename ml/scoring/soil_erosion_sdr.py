"""Sediment-delivery-ratio (SDR) adjustment for the soil_erosion channel — a disclosed, cited correction, not a
fitted one.

Why this exists: GloSEM (ml/scoring/soil_erosion_point.py) predicts GROSS point-scale hillslope erosion
(t ha⁻¹ yr⁻¹, RUSLE-family). The two independent backtests (services/validation/validators/
soil_erosion_eusedcollab.py, soil_erosion_grilss.py) instead observe catchment-OUTLET sediment yield — what
actually leaves the catchment after in-transit storage, floodplain deposition and re-deposition. The ratio
between the two, the sediment delivery ratio (SDR), is well established in the geomorphology/hydrology
literature to decline with catchment (drainage) area: small, steep catchments deliver a much larger share of
their gross erosion to the outlet than large ones, where more of the eroded material is re-stored en route.

Formula used — Boyce (1975), the commonly-cited power-law extension of the Vanoni (1975) drainage-area vs SDR
curve (300 worldwide watersheds; reproduced e.g. in the USDA/SCS sediment-yield literature and in de Vente &
Poesen 2005, "Predicting soil erosion and sediment yield at the basin scale", Earth-Science Reviews):

    SDR = 0.5656 * A_km2 ** -0.11

with A the catchment drainage area in km². This is a CITED, off-the-shelf curve — nothing here is fitted to
EUSEDcollab or GRILSS. Same posture as flood_jrc.py citing the Huizinga (2017) depth-damage table: the exponent
and coefficient are the published ones, used as-is.

Disclosed limits: this is a single mean global curve; actual SDR varies with relief, channel/floodplain
storage, land use, and climate far more than area alone explains (de Vente & Poesen 2005 report scatter of
1-2 orders of magnitude around any area-only curve). It is applied here ONLY to correct the systematic gross-
vs-net scale mismatch before a RANK test — not claimed as a per-catchment-accurate delivery estimate. SDR is
clipped to (0, 1] as a physical bound (delivery cannot exceed 100% or be negative/zero).
"""
from __future__ import annotations

SDR_SOURCE = ("Boyce (1975) power-law extension of the Vanoni (1975) drainage-area SDR curve (300 worldwide "
              "watersheds); reproduced in de Vente & Poesen (2005), Earth-Science Reviews 71:95-125. "
              "SDR = 0.5656 * A_km2^-0.11, a cited curve, not fitted to EUSEDcollab/GRILSS.")


def sediment_delivery_ratio(area_km2: float) -> float:
    """Boyce (1975) SDR as a fraction (0, 1], from catchment drainage area in km²."""
    a = max(float(area_km2), 1e-6)
    sdr = 0.5656 * a ** -0.11
    return max(1e-6, min(1.0, sdr))


def delivered_yield(gross_erosion_t_ha_yr: float, area_km2: float) -> float:
    """Gross point-scale erosion rate (t ha⁻¹ yr⁻¹) scaled by the area-dependent SDR to an estimated
    catchment-outlet-delivered yield (t ha⁻¹ yr⁻¹), the quantity comparable to observed SSY/sedimentation."""
    return float(gross_erosion_t_ha_yr) * sediment_delivery_ratio(area_km2)

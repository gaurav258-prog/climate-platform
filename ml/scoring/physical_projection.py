"""Physically-grounded forward projection for the non-crop hazards (flood / storm / wildfire).

Replaces the old flat `score × (1 + warming_intensity × horizon_weight)` uplift — which had no
physical basis and no uncertainty — with a per-hazard response driven by each cell's OWN CMIP6
warming + precipitation change (from the global delta field), scaled by a documented, cited
sensitivity, and carrying a real across-model band from the CMIP6 spread.

Sensitivities (published, disclosed — not fitted):
  • FLOOD   — extreme-rainfall intensity scales with warming per the Clausius–Clapeyron relation,
              ~7 %/°C (IPCC AR6 WG1 Ch.11: heavy precipitation intensifies ~7 %/°C, and does so even
              in regions whose MEAN precip falls). Flood hazard is driven by that extreme, so we scale
              it by local warming only. Coastal sea-level-rise and mean-precip terms are deliberately
              NOT included yet (separate documented mechanisms) — disclosed, not fabricated.
  • STORM   — tropical-cyclone / windstorm PEAK intensity rises ~5 %/°C and the Cat4-5 share grows
              (IPCC AR6 WG1 Ch.11). Frequency is ~flat/declining, so we scale severity, not counts.
  • WILDFIRE— fire weather rises with warming AND drying (IPCC AR6 WG1 Ch.12 / Ch.11 fire-weather):
              a warming term plus a drying term on the local mean-precip change.

These are transparent first-order elasticities on a 0–100 severity index, applied MULTIPLICATIVELY
(matching the existing convention) and capped at 100. The point is not a bias-free damage model —
it is that the forward number now comes from the LOCAL, model-derived climate signal with an honest
model-disagreement band, instead of a single global multiplier.
"""
from __future__ import annotations
from typing import NamedTuple, Optional, Tuple

from ml.scoring.cmip6 import Cmip6Delta


class Sensitivity(NamedTuple):
    per_c: float        # fractional hazard change per °C of local warming
    precip_w: float     # weight on local fractional mean-precip change (drying/wetting); 0 = unused
    basis: str          # cited source


PROJECTION_VERSION = "phys-proj-v1"

# only climate-driven hazards are projected; seismic/volcanic are geophysical, heat/drought/soil_water
# have their own dedicated climatology paths.
SENSITIVITY = {
    "flood":    Sensitivity(0.07, 0.0,  "Clausius–Clapeyron ~7%/°C extreme precip (IPCC AR6 WG1 Ch.11)"),
    "storm":    Sensitivity(0.05, 0.0,  "TC peak-intensity ~5%/°C, Cat4-5 share rises (IPCC AR6 WG1 Ch.11)"),
    "wildfire": Sensitivity(0.06, -0.40, "fire weather: warming + drying (IPCC AR6 WG1 Ch.11/12)"),
}


def _uplift(sens: Sensitivity, dtas: float, dpr: float) -> float:
    return sens.per_c * dtas + sens.precip_w * dpr


def project(base_score: float, hazard: str, delta: Optional[Cmip6Delta]
            ) -> Tuple[float, Optional[float], Optional[float]]:
    """(projected_score, ci_lower, ci_upper). Returns the base score with NO band when the hazard
    isn't climate-projected or CMIP6 doesn't cover the cell/combo (an honest point, not a fake band)."""
    sens = SENSITIVITY.get(hazard)
    if sens is None or delta is None:
        return (round(base_score, 2), None, None)
    central = min(100.0, max(0.0, base_score * (1.0 + _uplift(sens, delta.dtas_c, delta.dpr_frac))))
    if delta.n_models <= 1 or (delta.dtas_std_c == 0 and delta.dpr_std == 0):
        return (round(central, 2), None, None)   # a mean with no spread → no honest band
    corners = []
    for st in (1.0, -1.0):
        for sp in (1.0, -1.0):
            u = _uplift(sens, delta.dtas_c + st * delta.dtas_std_c, delta.dpr_frac + sp * delta.dpr_std)
            corners.append(min(100.0, max(0.0, base_score * (1.0 + u))))
    return (round(central, 2), round(min(corners), 2), round(max(corners), 2))

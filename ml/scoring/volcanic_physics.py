"""
Physics-based volcanic hazard scoring — mirrors ml/scoring/seismic_physics.py's
approach (transparent, distance-decay physics; not an ML black box) for the same
reason: volcanic risk is a point-source event, not a smooth climate field, and
there are no real damage labels to train against.

Two components, blended into ONE hazard_type='volcanic' score (see
docs/VOLCANIC_HAZARD_METHODOLOGY.md for why this isn't split into two hazard
types the way heat_acute/heat_chronic is):

1. Proximal destruction (lava flow / pyroclastic density current / lahar) —
   genuinely near-binary in reality (you're in the flow's path or you're not).
   A steep exponential decay with a high power `p` approximates that shape while
   staying a smooth, scoreable function: near 100 inside the hazard-zone radius,
   dropping off sharply at the boundary, ~0 well beyond it.

2. Ashfall load — the component that DOES fit the gradual/probabilistic damage
   pattern the agriculture impact chain already assumes (see supply_cogs.py).
   Modelled as an inverse-power distance decay, radius scaled by VEI (higher VEI
   -> larger ashfall footprint, a well-established relationship).

Known simplification (stated up front, same honesty convention as seismic's own
docstring): both components are modelled as radially symmetric. Real ashfall is
wind-direction-modulated and real PDC/lahar paths follow topography (valleys),
not a circle. This is a v0 approximation, not a claim of directional accuracy.
"""
from __future__ import annotations

import numpy as np

# Proximal destruction: steep, near-binary falloff within the hazard-zone radius.
_PROXIMAL_POWER = 3.5

# Ashfall: gradual inverse-power falloff.
_ASHFALL_POWER = 1.5

# VEI-scaled DEFAULT radii (km) for volcanoes without a curated volcanic_hazard_zones
# row — a rough order-of-magnitude fallback, not a substitute for published hazard
# maps. Anchored loosely to VEI 3-4 events (Fuego/Taal) being on the order of a few
# km (proximal) / tens of km (ashfall); scales down for smaller VEI, up for larger.
_DEFAULT_PROXIMAL_KM_AT_VEI4 = 8.0
_DEFAULT_ASHFALL_KM_AT_VEI4 = 40.0


def vei_to_zone_radii(vei: int | float | None) -> tuple[float, float]:
    """Default (proximal_km, ashfall_km) scaled from VEI when no curated zone exists.

    Roughly doubles per +1 VEI step (each VEI step is a ~10x increase in erupted
    volume, but hazard-zone RADIUS grows much more slowly than volume — an order-
    of-magnitude-in-radius-per-2-VEI-steps approximation, not a fitted curve).
    """
    v = float(vei) if vei is not None else 3.0
    scale = 2 ** ((v - 4.0) / 2.0)
    return _DEFAULT_PROXIMAL_KM_AT_VEI4 * scale, _DEFAULT_ASHFALL_KM_AT_VEI4 * scale


def proximal_score(distance_km, r_proximal_km: float, p: float = _PROXIMAL_POWER):
    """0-100 proximal-destruction risk. ~100 inside r_proximal_km, steep dropoff at
    the boundary, ~0 well beyond it (lava flow / PDC / lahar)."""
    d = np.maximum(np.asarray(distance_km, dtype=float), 0.0)
    r = max(float(r_proximal_km), 0.1)
    return np.clip(100.0 * np.exp(-((d / r) ** p)), 0.0, 100.0)


def ashfall_score(distance_km, r_ash_km: float, q: float = _ASHFALL_POWER):
    """0-100 ashfall-load risk. Gradual inverse-power decay from the vent, radius
    already VEI-scaled by the caller (see vei_to_zone_radii)."""
    d = np.maximum(np.asarray(distance_km, dtype=float), 0.0)
    r = max(float(r_ash_km), 0.1)
    return np.clip(100.0 * (r / (r + d)) ** q, 0.0, 100.0)


def blended_volcanic_score(distance_km, r_proximal_km: float, r_ash_km: float):
    """Combine proximal + ashfall into one hazard_type='volcanic' score.

    max(), not additive — avoids double-counting the near-vent zone where both
    components are already high, and matches the worst-hazard-wins philosophy
    supply_cogs.py already uses when aggregating multiple hazards per plot.
    """
    prox = proximal_score(distance_km, r_proximal_km)
    ash = ashfall_score(distance_km, r_ash_km)
    return np.maximum(prox, ash), prox, ash

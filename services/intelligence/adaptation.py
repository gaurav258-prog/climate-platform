"""Adaptation actions per hazard — the 'so what do I do' layer.

Honest scope: these are recognised, reference-backed adaptation MEASURES for each hazard, not a
site-specific engineering prescription. They turn a diagnosis ('this site is drought-exposed') into
a short, credible action list a risk owner can act on or hand to operations. Sources are the usual
public adaptation literature (EU Climate-ADAPT, IPCC AR6 WGII, UNDRR). We deliberately keep them
generic + few — better to point at the right lever than to fake bespoke advice.
"""
from __future__ import annotations

# hazard_type (as scored in canonical_scores) → ordered, most-leverage-first adaptation measures
_ACTIONS: dict[str, list[str]] = {
    "drought": [
        "Secure water rights / diversify supply (storage, reuse, alternative sources)",
        "Drip / precision irrigation and soil-moisture monitoring",
        "Drought-tolerant varieties or a second sourcing origin as a hedge",
    ],
    "soil_water": [
        "Soil-moisture sensors + irrigation scheduling to buffer deficits",
        "Cover cropping / mulching to retain soil water",
        "Reservoir or shared-irrigation access where available",
    ],
    "heat_chronic": [
        "Shade / canopy management and heat-tolerant varieties",
        "Cooling for storage & processing (cold chain resilience)",
        "Shift labour and harvest windows away from peak heat",
    ],
    "heat_acute": [
        "Heat-action plan for staff and livestock (cooling, hydration, downtime rules)",
        "Backup power / cooling for temperature-sensitive stock",
        "Bring forward harvest / dispatch ahead of forecast heatwaves",
    ],
    "flood": [
        "Site-level flood defences (barriers, raised critical equipment, drainage)",
        "Avoid new siting in the floodplain; relocate high-value stock above flood level",
        "Flood emergency + business-continuity plan with early-warning triggers",
    ],
    "storm": [
        "Structural hardening (roofing, cladding, windbreaks) to design wind loads",
        "Secure / shelter equipment and stock ahead of storm warnings",
        "Redundant power and comms for post-storm continuity",
    ],
    "wildfire": [
        "Defensible space / vegetation management around the site",
        "Non-combustible construction and ember-proofing of openings",
        "Wildfire response plan + insurance review in the wildland-urban interface",
    ],
    "seismic": [
        "Seismic assessment and retrofit of critical structures/racking",
        "Anchor plant, tanks and high-value inventory",
        "Business-continuity + supplier redundancy for a prolonged outage",
    ],
    "water_stress": [
        "Water-efficiency programme and reuse/recycling",
        "Diversify water supply; engage on basin-level allocation risk",
        "Site water-balance monitoring against local availability",
    ],
}

_LABELS = {
    "drought": "Drought", "soil_water": "Soil-water deficit", "heat_chronic": "Chronic heat",
    "heat_acute": "Acute heat", "flood": "Flood", "storm": "Storm / wind", "wildfire": "Wildfire",
    "seismic": "Seismic", "water_stress": "Water stress",
}


def actions_for(hazard_types: list[str]) -> list[dict]:
    """Return de-duplicated {hazard, label, actions} for the given hazard types (order preserved)."""
    out, seen = [], set()
    for h in hazard_types:
        if h in seen or h not in _ACTIONS:
            continue
        seen.add(h)
        out.append({"hazard": h, "label": _LABELS.get(h, h), "actions": _ACTIONS[h]})
    return out

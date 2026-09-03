"""Model limitations — the single, auditable statement of what the engine deliberately does NOT model yet.

Honesty is only credible if the gaps are named. Coverage maps say what we score; the projection map says how
we carry it forward; this says where we stop, why, and exactly what would let us go further. Every item is one
of three kinds:

  • tested_rejected     — a hypothesis was tested against the honesty gate and did NOT hold; wiring it would
                          fabricate signal that isn't there. The evidence (and the numbers) travel with it.
  • deferred_needs_data — honestly buildable, but only with an authoritative feed we don't yet hold; the
                          `unlock` names that feed. The current treatment is the conservative interim.
  • disclosed_scope     — a deliberate modelling-scope boundary (a mechanism left out by design, or an
                          illustrative-vs-calibrated basis), stated so a number is never read for more than it is.

A limitation leaving this registry means it was either closed (built + validated) or re-tested and still held —
never quietly dropped.
"""
from __future__ import annotations

MODEL_LIMITATIONS_VERSION = "limits-v1"

_STATUS_LABEL = {
    "tested_rejected": "Tested & rejected — not wired (would fabricate signal)",
    "deferred_needs_data": "Deferred — buildable only with an authoritative feed we don't yet hold",
    "disclosed_scope": "Disclosed scope boundary — a mechanism left out by design",
}

_LIMITATIONS = [
    {
        "id": "water_management",
        "area": "Agriculture · water",
        "status": "tested_rejected",
        "title": "Irrigation / reservoir buffering does not beat rainfall",
        "summary": ("Water stress is scored from meteorological drought (SPEI) and root-zone soil moisture — "
                    "the sky, not the reservoir a farmer irrigates from. We tested whether basin storage "
                    "explains an irrigated crop's yield BETTER than rainfall; it does not."),
        "evidence": ("Leave-one-out CV, Spanish basins (scripts/compare_reservoir_driver.py): sugar beet "
                     "(Duero) LOO r²=-0.12 with the WRONG sign (higher fill → lower yield); rice "
                     "(Guadalquivir) LOO r²≈0.00. Re-tested across two sessions — same null result."),
        "current_treatment": ("Irrigation is captured QUALITATIVELY: an irrigated plot's drought score is "
                              "shown as an UPPER BOUND (irrigation_context) and its € is deliberately left "
                              "unchanged — disclosed, never a fabricated buffer."),
        "unlock": ("A water-management signal (basin allocation, canal delivery, or a global irrigation-water "
                   "dataset) that clears the r²≥0.40 out-of-sample floor over the same years SPEI is scored on."),
    },
    {
        "id": "regional_sea_level",
        "area": "Coastal · sea-level rise",
        "status": "deferred_needs_data",
        "title": "Regional SLR now carries the ocean-dynamic term; the ice-fingerprint + GIA remainder is pending",
        "summary": ("Coastal-flood projections apply IPCC AR6 global-mean SLR PLUS the ocean-DYNAMIC regional "
                    "deviation (from CMIP6 `zos`), the largest spatially-varying piece — so local sea level now "
                    "differs from the global mean. The gravitational 'fingerprint' of ice-mass loss and glacial "
                    "isostatic adjustment are the remaining regional terms, not yet applied per cell."),
        "evidence": ("ml/scoring/sea_level.py (v2) + sea_level_regional.py add the CMIP6 zos ensemble offset "
                     "(built by scripts/build_cmip6_zos.py) — e.g. the US East coast and NW Europe read ~+0.1 m "
                     "above the global mean, matching AR6's documented amplification there."),
        "current_treatment": ("The dominant ocean-dynamic pattern is now local and disclosed; the fingerprint + "
                              "GIA terms default to the global-mean rise until the full field is ingested."),
        "unlock": ("The full IPCC AR6 regional SLR grid (~9 GB Zenodo archive, which also carries VLM) for the "
                   "gravitational-fingerprint + GIA components — a bounded bulk-data pull."),
    },
    {
        "id": "land_subsidence",
        "area": "Coastal · vertical land motion",
        "status": "deferred_needs_data",
        "title": "Coastal freeboard is now subsidence-aware; the InSAR rate feed is pending",
        "summary": ("Effective coastal exposure = SLR + local land subsidence. In several major deltas (Jakarta, "
                    "the US Gulf, parts of the North Sea coast) the land sinks faster than the sea rises. The "
                    "freeboard screen now SUBTRACTS a per-cell subsidence rate accumulated to the horizon; the "
                    "rate is populated only where an InSAR feed provides it."),
        "evidence": ("ml/scoring/sea_level.py (v2) subtracts subsidence_m = rate × years-to-horizon; "
                     "coastal_exposure.subsidence_mm_yr (migration coastal_subsidence_20260903) holds the rate, "
                     "NULL until fed → treated as 0."),
        "current_treatment": ("The model handles subsidence; with no rate the term is 0 "
                              "(conservative-optimistic in subsiding zones) and disclosed — never silently assumed."),
        "unlock": ("Copernicus EGMS (European Ground Motion Service, InSAR vertical velocity) for EU coasts, "
                   "or a global InSAR VLM product, to populate coastal_exposure.subsidence_mm_yr."),
    },
    {
        "id": "financial_euro_basis",
        "area": "Financial · damage basis",
        "status": "disclosed_scope",
        "title": "Financial € uses a disclosed peril schedule, not a loss-fitted model",
        "summary": ("The agri crop € is CALIBRATED (regression on observed yield, gated at r²≥0.40 "
                    "out-of-sample). The financial € (collateral haircut / insurance MDR) uses an "
                    "ILLUSTRATIVE, literature-consistent severity schedule (df-v1.0) × a bounded vulnerability "
                    "factor — it is NOT fitted to a loss dataset."),
        "evidence": ("ml/scoring/damage_function.py: RECOMMENDED_DISCOUNT_PCT / PERIL_DISCOUNT_PCT are "
                     "disclosed anchors consistent with published stress-test guidance, versioned df-v1.0."),
        "current_treatment": ("The distinction is stated wherever the € surfaces; the number is a transparent, "
                              "disclosed schedule, never presented as a fitted expected loss."),
        "unlock": ("A per-peril observed loss/impairment dataset (e.g. realised LGDs by hazard) to move the "
                   "financial € from illustrative to calibrated — the same r²-gated treatment as the crops."),
    },
    {
        "id": "flood_mechanism_scope",
        "area": "Flood · projection mechanism",
        "status": "disclosed_scope",
        "title": "Flood projection scales extreme rainfall only",
        "summary": ("The forward flood projection scales the hazard by Clausius–Clapeyron extreme-rainfall "
                    "intensification (~7%/°C). Mean-precipitation change and the coastal/compound terms are "
                    "deliberately excluded — they are separate, documented mechanisms."),
        "evidence": "ml/scoring/physical_projection.py SENSITIVITY['flood'], basis IPCC AR6 WG1 Ch.11.",
        "current_treatment": "Extreme-precip scaling is the dominant flood driver and is applied with a real CMIP6 band.",
        "unlock": "Add the mean-precip term and a compound coastal+pluvial interaction, each cited and banded.",
    },
]


def model_limitations() -> dict:
    """The disclosed-limitations registry — a static, auditable list (no tenant data)."""
    by_status: dict = {}
    for lim in _LIMITATIONS:
        by_status[lim["status"]] = by_status.get(lim["status"], 0) + 1
    items = [{**lim, "status_label": _STATUS_LABEL[lim["status"]]} for lim in _LIMITATIONS]
    return {
        "version": MODEL_LIMITATIONS_VERSION,
        "n_limitations": len(items),
        "counts": {"tested_rejected": by_status.get("tested_rejected", 0),
                   "deferred_needs_data": by_status.get("deferred_needs_data", 0),
                   "disclosed_scope": by_status.get("disclosed_scope", 0)},
        "statuses": [{"status": k, "label": v} for k, v in _STATUS_LABEL.items()],
        "items": items,
        "note": ("What the engine deliberately does not model yet, and why. A tested-rejected item was measured "
                 "against the honesty gate and left out rather than fabricated; a deferred item names the "
                 "authoritative feed that would close it; a scope item is a boundary stated so a number is never "
                 "read for more than it is."),
    }

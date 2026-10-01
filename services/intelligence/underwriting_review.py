"""Underwriting review — observed loss experience per policy + frequency validation of the priced return period.

The insurance product line built on Realized Exposure. An underwriter prices a policy against a *modelled*
return period ("1-in-50-year loss"). Tellumen holds the *observed* record — the real storms and earthquakes
that have actually crossed each policy's location. This module puts the two side by side, per policy:

  * OBSERVED LOSS EXPERIENCE (every located policy): the real, named events that have already passed over
    this exact risk — an underwriting data point the carrier does not otherwise hold. Always grounded in the
    catalogue; never projected.
  * FREQUENCY VALIDATION (perils we hold an observed catalogue for — wind/storm, seismic): does the observed
    hit-rate at this location match the modelled return period the policy is priced on? Where observed
    frequency materially exceeds the priced assumption, the risk is flagged as potentially under-priced; where
    it is far below, potentially conservative. This is the empirical check behind a parametric-trigger book.

Honest by construction. Frequency is validated ONLY for perils with a real observed catalogue (storm, seismic);
for a policy priced against a peril we do not yet observe directly (drought, soil-water, flood, wildfire) the
review says so and withholds the comparison rather than inventing one. Coverage is reported explicitly.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.intelligence.realized_exposure import events_near_point

# headline priced peril -> the observed event kind that validates it
_CATALOGUED = {"storm": "storm", "seismic": "earthquake"}
# what counts as an observed event at a policy: a storm track within STORM_RADIUS_KM, an earthquake of at least
# MIN_MAGNITUDE within QUAKE_RADIUS_KM — the review's stated definition, returned with every review
STORM_RADIUS_KM = 120.0
QUAKE_RADIUS_KM = 150.0
MIN_MAGNITUDE = 5.0


def _catalogue_windows(session: Session, min_magnitude: float) -> tuple[int | None, int | None]:
    """The observed span (years) of each event catalogue — the denominator for observed annual frequency."""
    sw = session.execute(text("SELECT MIN(season_year), MAX(season_year) FROM storm_events")).first()
    qw = session.execute(text(
        "SELECT MIN(EXTRACT(YEAR FROM origin_time))::int, MAX(EXTRACT(YEAR FROM origin_time))::int "
        "FROM seismic_events WHERE CAST(magnitude AS FLOAT) >= :m"), {"m": min_magnitude}).first()
    storm_window = (sw[1] - sw[0] + 1) if sw and sw[0] and sw[1] else None
    quake_window = (qw[1] - qw[0] + 1) if qw and qw[0] and qw[1] else None
    return storm_window, quake_window


def _frequency_check(peril: str, rp: float | None, n_storm: int, n_quake: int,
                     storm_window: int | None, quake_window: int | None, tolerance: float | None) -> dict | None:
    """Compare the observed hit-rate at a location to the return period the policy is priced on (the insurer's stated
    event probability). Returns None when the priced peril has no observed catalogue (comparison withheld). The verdict
    uses the insurer's stated tolerance (method.frequency_review_tolerance): observed ≥ (1 + t) × priced → possibly
    under-priced, ≤ (1 − t) × → possibly conservative; without it, the ratio is shown and no verdict is given."""
    kind = _CATALOGUED.get(peril)
    if not kind or not rp:
        return None
    window = storm_window if kind == "storm" else quake_window
    observed = n_storm if kind == "storm" else n_quake
    if not window:
        return None
    modelled_annual = 1.0 / rp
    observed_annual = observed / window
    ratio = (observed_annual / modelled_annual) if modelled_annual else None
    verdict = (None if ratio is None or tolerance is None
               else "under_priced" if ratio >= 1 + tolerance
               else "conservative" if ratio <= 1 - tolerance
               else "in_line")
    return {
        "peril": peril,
        "catalogue": kind,
        "observed_events": observed,
        "observed_window_years": window,
        "modelled_return_period_years": rp,
        "expected_events_in_window": round(window / rp, 2),
        "implied_observed_return_period_years": round(window / observed, 1) if observed else None,
        "observed_vs_modelled_ratio": round(ratio, 2) if ratio is not None else None,
        "verdict": verdict,
    }


def underwriting_review(session: Session, org_id: str) -> dict:
    """Per-policy observed loss experience + frequency validation for an insurer's book."""
    from api.routers.insurance import build_disclosure_snapshot
    from services.money.params import for_org

    storm_radius_km, quake_radius_km, min_magnitude = STORM_RADIUS_KM, QUAKE_RADIUS_KM, MIN_MAGNITUDE
    tolerance = for_org(session, org_id).get("method.frequency_review_tolerance")
    storm_window, quake_window = _catalogue_windows(session, min_magnitude)
    snap = build_disclosure_snapshot(session, org_id, "baseline", "current")
    policies = [p for p in snap.get("policies", []) if p.get("lat") is not None and p.get("lon") is not None]

    reviewed: list[dict] = []
    for p in policies:
        near = events_near_point(session, p["lat"], p["lon"], storm_radius_km, quake_radius_km, min_magnitude)
        evs = near["events"]
        n_storm = sum(1 for e in evs if e["kind"] == "storm")
        n_quake = sum(1 for e in evs if e["kind"] == "earthquake")
        pricing = p.get("pricing") or {}
        peril = p.get("headline_hazard")
        freq = _frequency_check(peril, pricing.get("return_period_years"), n_storm, n_quake,
                                storm_window, quake_window, tolerance)
        # closest events first, a handful for display
        top = sorted(evs, key=lambda e: e.get("closest_km") if e.get("closest_km") is not None else float("inf"))[:6]
        reviewed.append({
            "policy_id": p.get("policy_id"),
            "policy_name": p.get("policy_name"),
            "region": p.get("region"),
            "country": p.get("country"),
            "lat": p["lat"], "lon": p["lon"],
            "sum_insured_eur": p.get("sum_insured_eur"),
            "headline_hazard": peril,
            "headline_bucket": p.get("headline_bucket"),
            "technical_premium_eur": pricing.get("technical_premium_eur"),
            "rate_on_line_pct": pricing.get("rate_on_line_pct"),
            "n_observed_events": len(evs),
            "n_storm": n_storm, "n_quake": n_quake,
            "events": top,
            "frequency": freq,
        })

    # ---- rollups --------------------------------------------------------
    hit = [r for r in reviewed if r["n_observed_events"] > 0]
    freq_checks = [r for r in reviewed if r["frequency"]]
    under = [r for r in freq_checks if r["frequency"]["verdict"] == "under_priced"]
    conservative = [r for r in freq_checks if r["frequency"]["verdict"] == "conservative"]
    n_priced_uncatalogued = sum(1 for r in reviewed if r["frequency"] is None)

    # most physically-exposed policies (real event history) — the underwriting attention list
    most_exposed = sorted(hit, key=lambda r: (-r["n_observed_events"], -(r["sum_insured_eur"] or 0)))[:12]

    headline = (
        f"{len(hit)} of {len(reviewed)} policies sit where real climate events have already struck — "
        f"{sum(r['n_observed_events'] for r in hit)} observed storm/earthquake crossings across the book."
        if hit else
        f"No catalogued storm or earthquake has crossed the {len(reviewed)} located policies in this book."
    )

    return {
        "available": True,
        "headline": headline,
        "n_policies": len(reviewed),
        "n_policies_hit": len(hit),
        "n_events_observed": sum(r["n_observed_events"] for r in reviewed),
        "sum_insured_hit_eur": round(sum(r["sum_insured_eur"] or 0 for r in hit)),
        "frequency": {
            "n_validatable": len(freq_checks),
            "n_under_priced": len(under),
            "n_conservative": len(conservative),
            "n_priced_against_uncatalogued_peril": n_priced_uncatalogued,
            "catalogue_windows": {"storm_years": storm_window, "seismic_years": quake_window},
            "under_priced": [
                {"policy_id": r["policy_id"], "policy_name": r["policy_name"], "region": r["region"],
                 "sum_insured_eur": r["sum_insured_eur"], **r["frequency"]}
                for r in sorted(under, key=lambda r: -(r["frequency"]["observed_vs_modelled_ratio"] or 0))
            ],
        },
        "most_exposed": most_exposed,
        "definition": {"storm_radius_km": storm_radius_km, "quake_radius_km": quake_radius_km, "min_magnitude": min_magnitude,
                       "verdict_tolerance": tolerance,
                       **({} if tolerance is not None else {"gap": "method.frequency_review_tolerance not stated — ratios "
                                                                   "shown without a verdict"})},
        "note": ("Observed loss experience is real catalogued events (IBTrACS storms + USGS earthquakes) within "
                 "the felt radius of each policy's location — an underwriting data point, not a projection. "
                 "Frequency validation compares the observed hit-rate to the modelled return period the policy "
                 "is priced on, and is available ONLY for perils Tellumen holds an observed catalogue for "
                 f"(storm, seismic); {n_priced_uncatalogued} policies priced against a peril without an observed "
                 "catalogue are shown with their event experience but no frequency verdict."),
    }

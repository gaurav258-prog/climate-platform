"""Underwriting review — the observed record at each policy, beside the frequency the policy is priced on.

The insurance product line built on Realized Exposure. A policy is priced, peril by peril, on the insurer's stated
annual probability of a damaging event (method.annual_event_probability; its return period is one over it). The
platform holds the observed record — the storms and earthquakes that have crossed each policy's location. Per policy:

  * CROSSINGS (every located policy): the catalogued events that have passed within reach of this risk — information
    the policy file does not otherwise hold. Never projected; a crossing is not a loss.
  * FREQUENCY CHECK (each peril the policy is priced on that has an observed catalogue: storm, earthquake): the
    crossings counted over the years the catalogue covers, beside the number the priced return period expects in those
    years (years ÷ return period). Every such peril is checked with its OWN priced return period (E246: only the
    headline hazard was checked, with the return period of the peril driving the price, so 124 of a book's 145 policies
    priced on earthquake were reported as priced on a peril with no catalogue).

The reading uses the insurer's stated tolerance (method.frequency_review_tolerance): crossings ≥ (1 + t) × expected →
crossed more often than priced; ≤ (1 − t) × expected → less often — only when the priced frequency expects at least
one event over the catalogue's years: below that, seeing none is what the price predicts, and no 'less often' is read.
Without the tolerance the numbers are shown and no reading is given. A crossing is broader than a damaging event (an
earthquake of magnitude 5 at 150 km is counted), so a flag is a prompt to check the price, never a finding.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from core import messages
from services.intelligence.realized_exposure import catalogue_spans, events_near_point, sources

# priced peril -> the observed catalogue that records it
_CATALOGUED = {"storm": "storm", "seismic": "earthquake"}
# what counts as an observed event at a policy: a storm track within STORM_RADIUS_KM, an earthquake of at least
# MIN_MAGNITUDE within QUAKE_RADIUS_KM — the review's stated definition, returned with every review
STORM_RADIUS_KM = 120.0
QUAKE_RADIUS_KM = 150.0
MIN_MAGNITUDE = 5.0


def frequency_check(peril: str, rp: float | None, observed: int, window_years: float | None,
                    tolerance: float | None) -> dict | None:
    """One priced peril at one location: the crossings over the catalogue's years beside the number its priced return
    period expects in them. None when the peril has no observed catalogue, or no priced return period or window."""
    kind = _CATALOGUED.get(peril)
    if not kind or not rp or not window_years:
        return None
    expected = window_years / rp
    ratio = observed / expected
    if tolerance is None:
        verdict, why = None, "no_tolerance"
    elif ratio >= 1 + tolerance:
        verdict, why = "more_often", None
    elif ratio <= 1 - tolerance:
        verdict, why = ("less_often", None) if expected >= 1 else (None, "window_short")
    else:
        verdict, why = "in_line", None
    return {
        "peril": peril, "peril_name": messages.name("hazard", peril), "catalogue": kind,
        "observed_events": observed, "window_years": window_years, "priced_return_period_years": rp,
        "expected_events": round(expected, 3), "ratio": round(ratio, 2),
        "verdict": verdict, "verdict_name": messages.name("realized.verdict", verdict) if verdict else None,
        "no_verdict": messages.render(f"realized.review.{why}", years=f"{window_years:g}") if why else None,
    }


def underwriting_review(session: Session, org_id: str) -> dict:
    """Per-policy crossings and frequency checks for an insurer's book."""
    from api.routers.insurance import build_disclosure_snapshot
    from services.money.params import for_org

    method = for_org(session, org_id)
    tolerance = method.get("method.frequency_review_tolerance")
    spans = catalogue_spans(session, MIN_MAGNITUDE)
    window = {k: (v or {}).get("years") for k, v in spans.items()}
    snap = build_disclosure_snapshot(session, org_id, "baseline", "current")
    policies = [p for p in snap.get("policies", []) if p.get("lat") is not None and p.get("lon") is not None]

    reviewed: list[dict] = []
    for p in policies:
        near = events_near_point(session, p["lat"], p["lon"], STORM_RADIUS_KM, QUAKE_RADIUS_KM, MIN_MAGNITUDE)
        evs = near["events"]
        n = {"storm": near["n_storms"], "earthquake": near["n_earthquakes"]}
        pricing = p.get("pricing") or {}
        checks = [c for c in (frequency_check(c["hazard"], c.get("return_period_years"), n.get(_CATALOGUED.get(c["hazard"]), 0),
                                              window.get(_CATALOGUED.get(c["hazard"])), tolerance)
                              for c in pricing.get("perils") or []) if c]
        priced_catalogued = any(c["hazard"] in _CATALOGUED for c in pricing.get("perils") or [])
        reviewed.append({
            "policy_id": p.get("policy_id"), "policy_name": p.get("policy_name"),
            "region": p.get("region"), "country": p.get("country"), "lat": p["lat"], "lon": p["lon"],
            "sum_insured_eur": p.get("sum_insured_eur"),
            "n_observed_events": len(evs), "n_storm": near["n_storms"], "n_quake": near["n_earthquakes"],
            "events": sorted(evs, key=lambda e: e["closest_km"])[:6],
            "checks": checks,
            "standing": "checked" if checks else "unpriced" if not pricing.get("perils") else
                        "no_return_period" if priced_catalogued else "uncatalogued",
        })

    # ---- rollups --------------------------------------------------------
    hit = [r for r in reviewed if r["n_observed_events"] > 0]
    checks = [{"policy_id": r["policy_id"], "policy_name": r["policy_name"], "region": r["region"],
               "sum_insured_eur": r["sum_insured_eur"], **c} for r in reviewed for c in r["checks"]]
    count = lambda v: sum(1 for c in checks if c["verdict"] == v)                       # noqa: E731
    standing = {k: sum(1 for r in reviewed if r["standing"] == k)
                for k in ("checked", "unpriced", "no_return_period", "uncatalogued")}
    by_peril = []
    for peril in sorted({c["peril"] for c in checks}):
        cs = [c for c in checks if c["peril"] == peril]
        by_peril.append({"peril": peril, "peril_name": cs[0]["peril_name"], "n_checks": len(cs),
                         **{f"n_{v}": sum(1 for c in cs if c["verdict"] == v) for v in ("more_often", "in_line", "less_often")},
                         "n_no_verdict": sum(1 for c in cs if c["verdict"] is None)})
    most_exposed = sorted(hit, key=lambda r: (-r["n_observed_events"], -(r["sum_insured_eur"] or 0)))[:12]
    params = {"storm_km": round(STORM_RADIUS_KM), "quake_km": round(QUAKE_RADIUS_KM), "min_mag": f"{MIN_MAGNITUDE:g}"}

    return {
        "available": True,
        "n_policies": len(reviewed),
        "n_policies_hit": len(hit),
        "n_events_observed": sum(r["n_observed_events"] for r in reviewed),
        "sum_insured_hit_eur": round(sum(r["sum_insured_eur"] or 0 for r in hit)),
        "frequency": {
            "n_checks": len(checks), "n_policies_checked": standing["checked"],
            "n_more_often": count("more_often"), "n_in_line": count("in_line"), "n_less_often": count("less_often"),
            "n_no_verdict": sum(1 for c in checks if c["verdict"] is None),
            "n_unpriced": standing["unpriced"], "n_no_return_period": standing["no_return_period"],
            "n_uncatalogued": standing["uncatalogued"],
            "by_peril": by_peril,
            "flagged": sorted((c for c in checks if c["verdict"] == "more_often"), key=lambda c: -c["ratio"]),
        },
        "most_exposed": most_exposed,
        "verdict_names": messages.names()["realized.verdict"],
        "sources": sources(spans),
        "definition": {"storm_radius_km": STORM_RADIUS_KM, "quake_radius_km": QUAKE_RADIUS_KM,
                       "min_magnitude": MIN_MAGNITUDE, "verdict_tolerance": tolerance, "gap": method.gap_text()},
        "messages": {
            "crossed": messages.render("realized.review.crossed", **params),
            "check": messages.render("realized.review.check", **params),
            "rule": messages.render("realized.review.rule", tolerance=f"{100 * tolerance:g}") if tolerance is not None else None,
            "uncatalogued": messages.render("realized.review.uncatalogued"),
            "unpriced": messages.render("realized.review.unpriced"),
            "no_return_period": messages.render("realized.review.no_return_period"),
        },
    }

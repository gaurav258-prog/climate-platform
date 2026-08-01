"""Input-quality fail-safe signals for a filing (audit T4b).

Three signals that must reach the filing gate, not just the dashboard — same two-layer policy as feed
staleness: FLAG + EXCLUDE, but surfaced as a pre-filing control so the operator FIXES the input first
(re-geocode, supply coordinates, wait for scoring) rather than silently filing a degraded number.

  1. low_confidence  — an asset located only coarsely (confidence below the floor, or precision at
                       region/country level). Its cell — and therefore its hazard — is imprecise.
  2. insufficient_data — a located, in-scope asset with NO standing hazard score yet: a euro cannot be
                       computed for it, so it must not silently read as zero risk.
  3. degraded        — a score produced by a rule-based fallback rather than the canonical golden source.

All three are LATENT on the demo today (every asset is coordinate-exact and scored); this wires them so
that when such data appears it is caught before it reaches a filing.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

LOW_CONFIDENCE_BELOW = 0.5           # matches the geocoder's own low-confidence threshold
COARSE_PRECISIONS = ("region", "country")


def _low_conf_pred(alias: str) -> str:
    # a located asset is low-confidence if its geocode confidence is below the floor OR its precision is coarse
    return (f"({alias}.latitude IS NOT NULL AND "
            f"(COALESCE({alias}.confidence, 1) < {LOW_CONFIDENCE_BELOW} "
            f"OR {alias}.geocode_precision IN {COARSE_PRECISIONS!r}))")


def input_quality_status(session: Session, org_id: str,
                         scenario: str = "baseline", horizon: str = "current") -> dict:
    """Pre-filing input-quality summary for one org: coarse-located assets, unscored in-scope assets."""
    low_sites = session.execute(text(
        f"SELECT name FROM sc_company_sites s WHERE s.org_id=:o AND {_low_conf_pred('s')}"),
        {"o": org_id}).scalars().all()
    low_plots = session.execute(text(
        f"SELECT plot_name FROM sc_sourcing_plots p WHERE p.org_id=:o AND {_low_conf_pred('p')}"),
        {"o": org_id}).scalars().all()

    # insufficient_data: a located site with no standing score on the reporting basis (can't produce a euro)
    unscored_sites = session.execute(text("""
        SELECT s.name FROM sc_company_sites s
        WHERE s.org_id=:o AND s.latitude IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM v_sc_site_physical_risk v
            WHERE v.site_id=s.site_id AND v.scenario=:sc AND v.time_horizon=:hz)
    """), {"o": org_id, "sc": scenario, "hz": horizon}).scalars().all()

    low_confidence = ([{"kind": "site", "name": n} for n in low_sites]
                      + [{"kind": "plot", "name": n} for n in low_plots])
    insufficient = [{"kind": "site", "name": n} for n in unscored_sites]
    return {
        "low_confidence_count": len(low_confidence),
        "insufficient_data_count": len(insufficient),
        "low_confidence": low_confidence,
        "insufficient_data": insufficient,
        "all_clear": not low_confidence and not insufficient,
    }

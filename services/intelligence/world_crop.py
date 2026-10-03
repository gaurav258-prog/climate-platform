"""What happened to the world crop, year by year — CONTEXT, never a forecast and never part of volume at risk.

For a commodity, from FAOSTAT world and origin production (crop_yield_observations), each year shows three figures
(ml.features.world_shock):

  reported   the world total's change on the year, as FAOSTAT reports it (trend, bearing cycle, weather — all of it)
  net        each origin's deviation from its own trend with its bearing cycle removed, weighted by its share of the
             world crop the year before, summed over every origin that can be decomposed — so one origin's good year
             offsets another's bad one
  losses     the same, summing only the origins that fell below trend: the crop that was lost. This is the figure the
             platform's damage-only model is validated against; volume at risk stays damage-only (a good year
             elsewhere does not un-fail a buyer's own plots)

Stated limits, shown with the figures (idea_climate_platform_upside_model, the user's 2026-07-18 decision):
  * the deviation is 'not explained by trend or cycle' — weather, but also pests, policy, new plantings, irrigation;
    for gains a larger share is likely not weather, so the net is not a 'climate gain'
  * coverage: the share of the world crop (previous year) held by the origins that could be decomposed — shown with
    every year, no threshold invented; a year whose coverage is 0 has no net or losses figure
  * the latest years cannot be decomposed yet: the trend is centred, so a year needs TREND_K later years of data
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

SOURCE = "FAOSTAT QCL bulk"
YEARS = 15                       # the years shown, ending at the latest year of the world series
TOP_ORIGINS = 6                  # the origins that moved the latest decomposable year most, by weighted deviation


def world_crop(session: Session, commodity: str, years: int = YEARS) -> dict:
    from ml.features.crop_cycle import TREND_K
    from ml.features.world_shock import world_shock
    held = session.execute(text("""
        SELECT max(season_year) AS last, max(ingested_at) AS loaded FROM crop_yield_observations
        WHERE commodity = :c AND source = :s AND country = 'WLD' AND production_tonnes IS NOT NULL"""),
        {"c": commodity, "s": SOURCE}).mappings().first()
    last = held["last"]
    base = {"commodity": commodity, "source": SOURCE, "trend_years_after": TREND_K,
            "basis": "context — what happened to world supply; not a forecast, not part of volume at risk",
            # how fresh the figures are: the latest year FAOSTAT reports, and when it was loaded here
            "data_to_year": last, "loaded_at": held["loaded"].date().isoformat() if held["loaded"] else None}
    if last is None:
        return {**base, "available": False,
                "reason": f"no FAOSTAT world production series is held for {commodity}", "years": [], "origins": None}
    rows, latest = [], None
    for y in range(int(last) - years + 1, int(last) + 1):
        w = world_shock(session, commodity, y, source=SOURCE)
        decomposed = w.n_origins_usable > 0
        rows.append({"year": y, "reported_pct": w.raw_world_shock_pct,
                     "net_pct": w.decomposed_net_shock_pct, "losses_pct": w.decomposed_damage_shock_pct,
                     "coverage_pct": round(100 * w.coverage, 1), "origins_used": w.n_origins_usable,
                     "origins_total": w.n_origins_total,
                     "why_not": None if decomposed else
                     f"not decomposable yet — the trend needs {TREND_K} later years of data"})
        if decomposed:
            latest = w
    origins = None
    if latest is not None:
        moved = sorted((c for c in latest.contributions if c.usable),
                       key=lambda c: -abs(c.climate_pct * c.base_year_share))[:TOP_ORIGINS]
        origins = {"year": latest.target_year, "rows": [
            {"origin": c.origin, "world_share_pct": round(100 * c.base_year_share, 1),
             "deviation_pct": round(c.climate_pct, 1),
             "weighted_pct": round(c.climate_pct * c.base_year_share, 2)} for c in moved]}
    return {**base, "available": True, "years": rows, "origins": origins}

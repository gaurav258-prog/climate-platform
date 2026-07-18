"""The CLIMATE-ATTRIBUTABLE world supply shock — the honest validation target for a cyclical crop.

WHY THIS EXISTS. Cocoa can be validated against FAO's raw world shock because cocoa has no
alternate-bearing cycle: its bad year IS a climate signal. Olive, wine and almonds do not work
that way. Spain 2012 olives fell 51%, but ~two-thirds of that was the tree's off-year, not the
weather; reconciled across origins, the world crop dropped 16% while only ~9-10 points of that
were climate. A climate-attributable model validated against the raw 16% would look like it
under-predicts by 40% and get "fixed" by inflating its sensitivity — manufacturing precisely
the over-attribution that failed coffee 2021.

So for a cyclical crop the target must be the world shock with the cycle removed FROM EVERY
material origin, weighted by each origin's share of world production:

    decomposed_world_shock = Σ_origins( origin_climate_pct × origin_base_year_world_share )

CRITICAL HONESTY GUARD — COVERAGE. The sum is only meaningful if the origins we can decompose
cover most of the world crop. We compute the covered share explicitly and return it. A caller
that publishes a target below a coverage threshold is asserting a world number it cannot see;
the whole point of the exercise is not to do that. An origin that is an EDGE year for the
target (trend extrapolated, trend_full_window=False) is refused and drops out of BOTH the sum
and the coverage — it is a gap, not a zero.

Base-year share, not target-year share: an origin's weight in the world crop is what it was
BEFORE the shock (year t-1). Using the post-shock share would let the origin that just
collapsed shrink its own contribution.

THREE WORLD NUMBERS, AND WHICH ONE IS THE TARGET. Olive 2012 makes the distinction concrete:

    raw       -16.08%   what FAO reports: cycle + climate + everything, all origins netted
    net        -4.06%   cycle removed: Spain's climate loss NETTED against other origins'
                        good years (Italy/Greece/Turkey/Syria all had ABOVE-trend 2012s)
    damage    -12.98%   cycle removed, LOSSES ONLY: the climate-attributable crop that was
                        destroyed, summed over the origins that actually lost

Our model is DAMAGE-ONLY: a hazard score drives a yield LOSS, never a gain, so the engine's
world-shock roll-up can only go down. It is structurally blind to the +8.92% of upside that
other origins enjoyed in 2012. Therefore:

  * the DAMAGE figure is the validation target — it is the only one the model can reproduce,
    and it is exactly what "physical volume at risk" means: the crop climate destroyed, not
    the net market outcome after other regions' luck.
  * the NET is honest context (what actually happened to world supply, and hence to price —
    which we do not forecast anyway).
  * the RAW is what you must NOT validate against: it charges Spain's whole alternate-bearing
    off-year to climate and would inflate the coefficient ~4x.

For cocoa 2023/24 all three coincide (both origins lost, no cycle), which is why cocoa passed
against the raw figure. A cyclical, regionally-offsetting crop is where they diverge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ml.features.crop_cycle import decompose

# FAO rows that are aggregates of other rows we already sum — including them double-counts.
# WLD is the world total we compare AGAINST; EU re-adds its member states.
_AGGREGATE_ORIGINS = {"WLD", "EU"}


@dataclass
class OriginContribution:
    origin: str
    base_year_share: float          # origin production (t-1) / world production (t-1)
    climate_pct: Optional[float]    # cycle-removed anomaly in the target year; None if unusable
    raw_yoy_pct: Optional[float]
    usable: bool                    # decomposable AND not an edge year AND has a base-year share
    reason: Optional[str] = None    # why not usable, when usable is False


@dataclass
class WorldShock:
    commodity: str
    target_year: int
    raw_world_shock_pct: Optional[float]         # WLD series — what FAO reports (cycle + climate)
    decomposed_net_shock_pct: Optional[float]    # cycle removed, losses NET of other origins' gains
    decomposed_damage_shock_pct: Optional[float]  # cycle removed, LOSSES ONLY — the validation target
    coverage: float                              # share of world crop the usable origins cover
    n_origins_usable: int
    n_origins_total: int
    contributions: list = field(default_factory=list)

    def is_publishable(self, min_coverage: float) -> bool:
        """A decomposed target may drive a euro only if the origins we could decompose cover
        at least `min_coverage` of the world crop. Below that we are guessing at the part we
        cannot see. Keys off the DAMAGE figure — the one the model can reproduce."""
        return (self.decomposed_damage_shock_pct is not None
                and self.coverage >= min_coverage)


def _series(session, commodity: str, source: str) -> dict[str, dict[int, float]]:
    """{origin: {year: production_tonnes}} for one commodity, aggregates excluded."""
    from sqlalchemy import text

    rows = session.execute(text("""
        SELECT country, season_year, production_tonnes
        FROM   crop_yield_observations
        WHERE  commodity = :c AND source = :s AND production_tonnes IS NOT NULL
    """), {"c": commodity, "s": source}).fetchall()
    out: dict[str, dict[int, float]] = {}
    for country, year, prod in rows:
        if country in _AGGREGATE_ORIGINS:
            out.setdefault("WLD" if country == "WLD" else country, {})
        out.setdefault(country, {})[int(year)] = float(prod)
    return out


def world_shock(session, commodity: str, target_year: int, *,
                source: str = "FAOSTAT QCL bulk") -> WorldShock:
    """Decompose the world supply shock for `commodity` in `target_year` into its
    climate-attributable part, weighted by each origin's base-year world share."""
    series = _series(session, commodity, source)
    wld = series.get("WLD", {})
    base = target_year - 1

    raw = None
    if wld.get(target_year) and wld.get(base):
        raw = round((wld[target_year] - wld[base]) / wld[base] * 100, 2)

    world_base = wld.get(base)
    contributions: list[OriginContribution] = []
    net = 0.0        # all usable origins, losses and gains
    damage = 0.0     # usable origins with a climate LOSS only
    covered = 0.0
    n_usable = 0

    origins = [o for o in series if o not in _AGGREGATE_ORIGINS]
    for origin in sorted(origins):
        s = series[origin]
        share = (s[base] / world_base) if (world_base and s.get(base)) else None
        d = decompose(s, target_year)
        t = d.get("target")

        usable, reason, climate = True, None, None
        if share is None:
            usable, reason = False, "no base-year production to weight by"
        elif t is None:
            usable, reason = False, "target year not in this origin's series"
        elif not t.get("trend_full_window"):
            usable, reason = False, "edge year — trend extrapolated, refused"
        else:
            climate = t["climate_pct"]

        contributions.append(OriginContribution(
            origin=origin,
            base_year_share=round(share, 5) if share is not None else None,
            climate_pct=climate,
            raw_yoy_pct=(t or {}).get("raw_yoy_pct") if t else None,
            usable=usable, reason=reason,
        ))
        if usable:
            net += climate * share
            if climate < 0:
                damage += climate * share
            covered += share
            n_usable += 1

    return WorldShock(
        commodity=commodity,
        target_year=target_year,
        raw_world_shock_pct=raw,
        decomposed_net_shock_pct=round(net, 2) if n_usable else None,
        decomposed_damage_shock_pct=round(damage, 2) if n_usable else None,
        coverage=round(covered, 4),
        n_origins_usable=n_usable,
        n_origins_total=len(origins),
        contributions=contributions,
    )

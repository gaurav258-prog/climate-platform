"""Tier-1 plausibility band: judge a submitted template with no granular data at all.

Every submitted cell (geography × sector) carries a sensitive share. The geography prior (services.supervision
.geo_prior) says what share of that geography's scored land sits in High/Very high under the same basis, and how
that share spreads across the geography's regions. A submitted share inside the spread is plausible; above it is
high for the geography; below it is low. The band is location-only — sector does not move it — and says so.
No figure is invented: a geography without enough scored cells gets 'no reference', never a guess.
"""
from __future__ import annotations

from typing import Optional

from services.supervision.geo_prior import prior_for

PLAUSIBLE, ABOVE, BELOW, NO_REF = "plausible", "above_band", "below_band", "no_reference"
LABEL = {PLAUSIBLE: "Plausible", ABOVE: "High for the geography", BELOW: "Low for the geography", NO_REF: "No reference"}
GEO_ALIAS = {"GR": "EL", "UK": "UK", "GB": "UK"}   # template codes → GISCO codes


def _share(cell: dict) -> Optional[float]:
    g = float(cell.get("gross_carrying_amount_eur") or 0)
    if g <= 0:
        return None
    return max(0.0, min(1.0, float(cell.get("sensitive_physical_eur") or 0) / g))


def judge(share: Optional[float], prior: Optional[dict]) -> tuple[str, str]:
    """→ (verdict, reason). Pure: the whole rule is here. Band = interquartile spread of the regional share."""
    if share is None:
        return NO_REF, "No gross carrying amount in this cell."
    if not prior or prior.get("p25") is None or prior.get("p75") is None:
        return NO_REF, "Not enough scored land in this geography to form a band."
    lo, hi = float(prior["p25"]), float(prior["p75"])
    pct = lambda x: f"{round(100 * x)}%"  # noqa: E731
    if share > hi:
        return ABOVE, (f"Submitted share {pct(share)} sits above the geography's regional spread ({pct(lo)}–{pct(hi)}): "
                       "either the book is concentrated in its riskiest areas, or the sensitivity is overstated.")
    if share < lo:
        return BELOW, (f"Submitted share {pct(share)} sits below the geography's regional spread ({pct(lo)}–{pct(hi)}): "
                       "either the book avoids the exposed areas, or the sensitivity is understated.")
    return PLAUSIBLE, f"Submitted share {pct(share)} sits inside the geography's regional spread ({pct(lo)}–{pct(hi)})."


def assess(session, cells: dict[str, dict], scenario: str, horizon: str) -> dict:
    rows = []
    for key, c in cells.items():
        geo = (c.get("geography") or key.split("|")[0]).strip().upper()
        geo = GEO_ALIAS.get(geo, geo)
        prior = prior_for(session, geo, scenario, horizon)
        share = _share(c)
        verdict, reason = judge(share, prior)
        rows.append({"key": key, "geography": c.get("geography"), "sector": c.get("sector"),
                     "gross_carrying_amount_eur": c.get("gross_carrying_amount_eur"), "sensitive_physical_eur": c.get("sensitive_physical_eur"),
                     "submitted_share_pct": round(100 * share, 1) if share is not None else None,
                     "band": ({"p10": round(100 * prior["p10"], 1), "p25": round(100 * prior["p25"], 1), "p50": round(100 * prior["p50"], 1),
                               "p75": round(100 * prior["p75"], 1), "p90": round(100 * prior["p90"], 1),
                               "share_sensitive_pct": round(100 * prior["share_sensitive"], 1), "n_cells": prior["n_cells"],
                               "n_regions": prior["n_regions"], "hazard_mix": prior.get("hazard_mix") or {}, "built_at": prior["built_at"]}
                              if prior and prior.get("p25") is not None else None),
                     "verdict": verdict, "verdict_label": LABEL[verdict], "reason": reason})
    rows.sort(key=lambda r: (-(r["gross_carrying_amount_eur"] or 0)))
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in (PLAUSIBLE, ABOVE, BELOW, NO_REF)}
    judged = [r for r in rows if r["verdict"] != NO_REF]
    gross_judged = sum(float(r["gross_carrying_amount_eur"] or 0) for r in judged)
    gross_all = sum(float(r["gross_carrying_amount_eur"] or 0) for r in rows)
    return {"rows": rows, "counts": counts, "n_cells": len(rows),
            "coverage_value_pct": round(100 * gross_judged / gross_all, 1) if gross_all else None,
            "rule": "A cell is plausible when its submitted sensitive share sits inside the interquartile spread (p25–p75) of "
                    "that share across the geography's regions, computed from the platform's own scored land at the same basis. "
                    "The band is location-only: sector does not move it. A geography without enough scored land gets no reference."}

"""Tier-1 plausibility band: judge a submitted template with no granular data at all.

Every submitted cell (geography × sector) carries a sensitive share of the sector's EXPOSURE MEASURE — the template
column the profile names (gross carrying amount for a bank, sum insured for an insurer). The reference is the prior
the profile names for that sector: the scored-land prior (services.supervision.geo_prior — what share of the
geography's scored land sits in High/Very high, and how that share spreads across its regions) or the population-
exposure prior (services.supervision.exposure_prior — the same share over the authority's own supervised population
of the sector, weighted by the measure, the entity under review excluded). A submitted share inside the spread is
plausible; above it is high for the geography; below it is low. The band is location-only — sector does not move
it — and says so. No figure is invented: a cell without the measure, or a geography without enough reference, gets
'no reference', never a guess; the output states the measure and the prior it used.
"""
from __future__ import annotations

from typing import Optional

from services.supervision.exposure_prior import POPULATION, PRIOR_LABEL, SCORED_LAND
from services.supervision.geo_prior import prior_for

PLAUSIBLE, ABOVE, BELOW, NO_REF = "plausible", "above_band", "below_band", "no_reference"
LABEL = {PLAUSIBLE: "Plausible", ABOVE: "High for the geography", BELOW: "Low for the geography", NO_REF: "No reference"}
GEO_ALIAS = {"GR": "EL", "UK": "UK", "GB": "UK"}   # template codes → GISCO codes
DEFAULT_FIELD = "gross_carrying_amount_eur"


def exposure_measure(sector_cfg: Optional[dict]) -> dict:
    """Pure. The sector's exposure measure from its profile block: {cell_field, label, prior}. A profile without
    an explicit `exposure_measure` falls back to the canonical column, labelled by the sector's own intake label
    for that column (else its book-value metric), on the scored-land prior. A prior name the platform does not
    know is an error, not a silent fallback."""
    sec = sector_cfg or {}
    em = dict(sec.get("exposure_measure") or {})
    field = em.get("cell_field") or DEFAULT_FIELD
    label = em.get("label")
    if not label:
        cells = ((sec.get("intake") or {}).get("submission") or {}).get("cell_fields") or []
        label = next((c.get("label") for c in cells if c.get("id") == field), None)
        label = label or next((m.get("label") for m in sec.get("metrics") or [] if m.get("id") == "book_value_eur"), None) or "Exposure"
        label = label.replace(" (€)", "")
    prior = em.get("prior") or SCORED_LAND
    if prior not in PRIOR_LABEL:
        raise ValueError(f"unknown plausibility prior {prior!r} for sector {sec.get('label')!r}; known: {sorted(PRIOR_LABEL)}")
    return {"cell_field": field, "label": label, "prior": prior, "prior_label": PRIOR_LABEL[prior]}


def share_of(cell: dict, measure: dict) -> Optional[float]:
    """Pure. Sensitive share of the exposure measure; None when the measure is missing or non-positive."""
    try:
        g = float(cell.get(measure["cell_field"]) or 0)
    except (TypeError, ValueError):
        return None
    if g <= 0:
        return None
    return max(0.0, min(1.0, float(cell.get("sensitive_physical_eur") or 0) / g))


def judge(share: Optional[float], prior: Optional[dict], measure_label: str = "gross carrying amount") -> tuple[str, str]:
    """→ (verdict, reason). Pure: the whole rule is here. Band = interquartile spread of the regional share."""
    if share is None:
        return NO_REF, f"No {measure_label.lower()} in this cell."
    if not prior or prior.get("p25") is None or prior.get("p75") is None:
        return NO_REF, "Not enough reference in this geography to form a band."
    lo, hi = float(prior["p25"]), float(prior["p75"])
    pct = lambda x: f"{round(100 * x)}%"  # noqa: E731
    if share > hi:
        return ABOVE, (f"Submitted share {pct(share)} sits above the geography's regional spread ({pct(lo)}–{pct(hi)}): "
                       "either the book is concentrated in its riskiest areas, or the sensitivity is overstated.")
    if share < lo:
        return BELOW, (f"Submitted share {pct(share)} sits below the geography's regional spread ({pct(lo)}–{pct(hi)}): "
                       "either the book avoids the exposed areas, or the sensitivity is understated.")
    return PLAUSIBLE, f"Submitted share {pct(share)} sits inside the geography's regional spread ({pct(lo)}–{pct(hi)})."


def _band(prior: Optional[dict]) -> Optional[dict]:
    if not prior or prior.get("p25") is None:
        return None
    return {"p10": round(100 * prior["p10"], 1), "p25": round(100 * prior["p25"], 1), "p50": round(100 * prior["p50"], 1),
            "p75": round(100 * prior["p75"], 1), "p90": round(100 * prior["p90"], 1),
            "share_sensitive_pct": round(100 * prior["share_sensitive"], 1), "n_cells": prior["n_cells"],
            "n_regions": prior["n_regions"], "hazard_mix": prior.get("hazard_mix") or {}, "built_at": prior["built_at"]}


def assess(session, cells: dict[str, dict], scenario: str, horizon: str, measure: Optional[dict] = None,
           population: Optional[dict] = None) -> dict:
    """measure = exposure_measure(sector profile); population = exposure_prior.population_priors(...) when the
    measure's prior is population_exposure (the caller resolves it once; assess never reads land priors then)."""
    m = measure or exposure_measure(None)
    field, label = m["cell_field"], m["label"]
    pop = (population or {}).get("priors") or {}
    lookup = (lambda g: pop.get(g)) if m["prior"] == POPULATION else (lambda g: prior_for(session, g, scenario, horizon))
    rows = []
    for key, c in cells.items():
        geo = (c.get("geography") or key.split("|")[0]).strip().upper()
        geo = GEO_ALIAS.get(geo, geo)
        prior = lookup(geo)
        share = share_of(c, m)
        verdict, reason = judge(share, prior, label)
        exposure = c.get(field)
        rows.append({"key": key, "geography": c.get("geography"), "sector": c.get("sector"),
                     "exposure_eur": exposure, "gross_carrying_amount_eur": c.get("gross_carrying_amount_eur"),
                     "sensitive_physical_eur": c.get("sensitive_physical_eur"),
                     "submitted_share_pct": round(100 * share, 1) if share is not None else None,
                     "band": _band(prior), "verdict": verdict, "verdict_label": LABEL[verdict], "reason": reason})
    rows.sort(key=lambda r: (-float(r["exposure_eur"] or 0)))
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in (PLAUSIBLE, ABOVE, BELOW, NO_REF)}
    judged = [r for r in rows if r["verdict"] != NO_REF]
    val = lambda r: float(r["exposure_eur"] or 0)  # noqa: E731
    total, total_judged = sum(val(r) for r in rows), sum(val(r) for r in judged)
    n_missing = sum(1 for r in rows if r["submitted_share_pct"] is None)
    ref = {"prior": m["prior"], "prior_label": m["prior_label"]}
    if m["prior"] == POPULATION:
        ref.update({k: (population or {}).get(k) for k in ("n_entities", "n_points", "n_used", "n_without_measure", "n_unlocated", "n_unscored")})
        how = (f"computed from the {label.lower()} of the other {ref['n_entities'] or 0} supervised entities of the sector under this "
               f"authority, each located point weighted by its {label.lower()} (the entity under review excluded)")
    else:
        how = "computed from the platform's own scored land at the same basis, every scored cell counting once"
    return {"rows": rows, "counts": counts, "n_cells": len(rows),
            "exposure_measure": {"cell_field": field, "label": label, "n_cells_without_measure": n_missing, **ref},
            "coverage_value_pct": round(100 * total_judged / total, 1) if total else None,
            "rule": f"A cell is plausible when its submitted sensitive share of {label.lower()} sits inside the interquartile spread (p25–p75) "
                    f"of that share across the geography's regions, {how}. The band is location-only: sector does not move it. "
                    f"A cell without {label.lower()}, or a geography without enough reference, gets no verdict."}


def assess_entity(session, reg_org_id: str, subject_org_id: str, cells: dict[str, dict], scenario: str, horizon: str) -> dict:
    """The band for one supervised entity: measure and prior from the authority's profile for the entity's sector."""
    from sqlalchemy import text

    from services.supervision.exposure_prior import population_priors
    from services.supervision.profiles import config_for, sector_config
    t = session.execute(text("SELECT type FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": subject_org_id}).scalar()
    m = exposure_measure(sector_config(config_for(session, reg_org_id), t))
    pop = population_priors(session, reg_org_id, t, scenario, horizon, exclude_org_id=subject_org_id) if m["prior"] == POPULATION else None
    return assess(session, cells, scenario, horizon, m, pop)

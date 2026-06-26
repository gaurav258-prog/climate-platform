"""
CSRD Physical Risk Format Builder.

Produces structured output aligned with:
  - Corporate Sustainability Reporting Directive (EU 2022/2464)
  - ESRS E1 — Climate Change (effective FY2024)
  - ESRS E1-9: Physical risk exposure (acute + chronic)
  - Double materiality assessment framework
  - TCFD pillars: Strategy → Risk Mgmt → Metrics & Targets

CSRD differs from ECB in two key ways:
  1. Double materiality: both financial impact (inside-out) AND environmental
     impact (outside-in) must be disclosed.
  2. Acute vs chronic split: our scores map to acute hazards (floods, wildfires,
     heatwaves). Chronic hazards (sea level, temperature trend) are flagged as
     requiring supplementary long-horizon scores.

Output tables:
  E1_9A — Material physical risks identified (acute)
  E1_9B — Risk assessment by asset / exposure class
  E1_9C — Financial exposure at risk by hazard
  E1_9D — Adaptation measures and residual risk
  E1_9E — Time horizon materiality (current / 2030 / 2050 / 2100)
  E1_9F — Double materiality summary
  methodology — Data lineage and scoring attestation
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# CSRD ESRS E1 hazard classification
CSRD_ACUTE_HAZARDS = {
    "flood":      "Acute — River flooding / pluvial flooding",
    "wildfire":   "Acute — Wildfire",
    "heat_acute": "Acute — Heatwave / extreme heat event",
    "storm":      "Acute — Extreme wind / storm",
}

CSRD_CHRONIC_HAZARDS = {
    "drought":    "Chronic — Drought / water scarcity",
    "sea_level":  "Chronic — Sea level rise",
    "heat_trend": "Chronic — Temperature increase",
}

# Materiality thresholds per CSRD proportionality guidance
MATERIAL_SCORE_THRESHOLD   = 40.0   # MEDIUM+ = material risk
VERY_MATERIAL_THRESHOLD    = 70.0   # HIGH/VERY_HIGH = very material

# Double materiality dimensions
INSIDE_OUT  = "financial_materiality"   # impact on enterprise value
OUTSIDE_IN  = "impact_materiality"      # enterprise's impact on climate/nature


def build(
    session: Session,
    customer_id: str,
    period_start: date,
    period_end: date,
    company_name: Optional[str] = None,
    nace_codes: Optional[list[str]] = None,
    time_horizons: Optional[list[str]] = None,
) -> dict:
    """
    Build the full CSRD ESRS E1-9 physical risk disclosure package.

    Parameters
    ----------
    customer_id   : platform customer UUID
    company_name  : legal name for the disclosure (optional, used in output)
    nace_codes    : EU NACE sector codes (e.g. ["A01", "D35"]) — affects
                    outside-in materiality weighting
    time_horizons : list of horizons; defaults to ["current","2030","2050","2100"]
    """
    time_horizons = time_horizons or ["current", "2030", "2050", "2100"]

    logger.info(f"[CSRD] Building package — customer={customer_id}  "
                f"{period_start}→{period_end}  horizons={time_horizons}")

    location_scores = _fetch_location_scores(
        session, customer_id, period_start, period_end, time_horizons
    )

    if not location_scores:
        logger.warning(f"[CSRD] No scores found for customer {customer_id}")
        return _empty_package(customer_id, period_start, period_end)

    # ── Build ESRS E1-9 tables ─────────────────────────────────
    e1_9a = _e1_9a_material_risks(location_scores)
    e1_9b = _e1_9b_exposure_by_class(location_scores)
    e1_9c = _e1_9c_financial_exposure(location_scores)
    e1_9d = _e1_9d_adaptation()
    e1_9e = _e1_9e_time_horizon_materiality(location_scores, time_horizons)
    e1_9f = _e1_9f_double_materiality(location_scores, nace_codes or [])
    meth  = _methodology(location_scores, nace_codes or [])

    # Summary
    material = [r for r in location_scores
                if r["risk_score"] >= MATERIAL_SCORE_THRESHOLD
                and r["time_horizon"] == "current"]
    n_total = len({r["location_id"] for r in location_scores})

    return {
        "framework":          "CSRD_ESRS_E1-9_2024",
        "customer_id":        customer_id,
        "company_name":       company_name or customer_id,
        "period_start":       str(period_start),
        "period_end":         str(period_end),
        "nace_codes":         nace_codes or [],
        "horizons_covered":   time_horizons,
        "n_locations":        n_total,
        "n_material_risks":   len(e1_9a),
        "pct_locations_material": round(
            len({r["location_id"] for r in material}) / n_total * 100, 1
        ) if n_total else 0,
        "e1_9a_material_risks":         e1_9a,
        "e1_9b_exposure_by_class":      e1_9b,
        "e1_9c_financial_exposure":     e1_9c,
        "e1_9d_adaptation_measures":    e1_9d,
        "e1_9e_time_horizon":           e1_9e,
        "e1_9f_double_materiality":     e1_9f,
        "methodology":                  meth,
    }


def _fetch_location_scores(
    session: Session,
    customer_id: str,
    period_start: date,
    period_end: date,
    time_horizons: list[str],
) -> list[dict]:
    """Fetch location scores across all scenarios and horizons."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (cl.location_id, cs.hazard_type, cs.scenario, cs.time_horizon)
               cl.location_id,
               cl.location_name,
               cl.h3_cell_r8                          AS h3_cell,
               cl.asset_type,
               CAST(cl.asset_value AS FLOAT)           AS asset_value,
               cl.currency,
               cs.hazard_type,
               cs.scenario,
               cs.time_horizon,
               CAST(cs.risk_score AS FLOAT)            AS risk_score,
               cs.risk_bucket,
               CAST(cs.score_ci_lower AS FLOAT)        AS ci_lower,
               CAST(cs.score_ci_upper AS FLOAT)        AS ci_upper,
               CAST(cs.score_velocity_24h AS FLOAT)    AS velocity_24h,
               cs.compound_flag,
               cs.regulatory_fingerprint,
               cs.scored_at
        FROM   customer_locations cl
        JOIN   canonical_scores   cs ON cs.h3_cell = cl.h3_cell_r8
        WHERE  cl.customer_id  = :customer_id
        AND    cl.is_active    = true
        AND    cs.scored_at   >= :period_start
        AND    cs.scored_at   <= :period_end
        AND    cs.time_horizon = ANY(:horizons)
        AND    cs.valid_to     IS NULL
        ORDER BY cl.location_id, cs.hazard_type, cs.scenario, cs.time_horizon,
                 cs.scored_at DESC
    """), {
        "customer_id":  customer_id,
        "period_start": str(period_start),
        "period_end":   str(period_end),
        "horizons":     time_horizons,
    }).mappings().all()

    return [dict(r) for r in rows]


def _e1_9a_material_risks(rows: list[dict]) -> list[dict]:
    """
    E1-9A: Material physical risks identified.
    CSRD requires listing each material risk by type, geography, and time horizon.
    """
    current = [r for r in rows if r["time_horizon"] == "current"
               and r["risk_score"] >= MATERIAL_SCORE_THRESHOLD]

    seen = {}
    for r in current:
        key = (r["hazard_type"], r["time_horizon"])
        if key not in seen or r["risk_score"] > seen[key]["max_score"]:
            seen[key] = {
                "hazard_type":    r["hazard_type"],
                "hazard_label":   CSRD_ACUTE_HAZARDS.get(r["hazard_type"], r["hazard_type"]),
                "hazard_class":   "Acute" if r["hazard_type"] in CSRD_ACUTE_HAZARDS else "Chronic",
                "time_horizon":   r["time_horizon"],
                "max_score":      r["risk_score"],
                "n_locations_at_risk": 0,
                "materiality":    "Very material" if r["risk_score"] >= VERY_MATERIAL_THRESHOLD
                                  else "Material",
                "compound_risk":  r["compound_flag"] or False,
            }
        seen[key]["n_locations_at_risk"] += 1

    return sorted(seen.values(), key=lambda x: -x["max_score"])


def _e1_9b_exposure_by_class(rows: list[dict]) -> list[dict]:
    """E1-9B: Risk by asset class (asset_type). Shows distribution within each class."""
    from collections import defaultdict

    current = [r for r in rows if r["time_horizon"] == "current"]
    by_class: dict[str, dict] = defaultdict(lambda: {
        "n": 0, "material": 0, "very_material": 0, "scores": [],
        "asset_value": 0.0, "hazards": set()
    })

    for r in current:
        asset_class = r["asset_type"] or "Unclassified"
        by_class[asset_class]["n"] += 1
        by_class[asset_class]["scores"].append(r["risk_score"])
        by_class[asset_class]["asset_value"] += (r["asset_value"] or 0)
        by_class[asset_class]["hazards"].add(r["hazard_type"])
        if r["risk_score"] >= MATERIAL_SCORE_THRESHOLD:
            by_class[asset_class]["material"] += 1
        if r["risk_score"] >= VERY_MATERIAL_THRESHOLD:
            by_class[asset_class]["very_material"] += 1

    result = []
    for asset_class, v in sorted(by_class.items()):
        mean_score = sum(v["scores"]) / len(v["scores"]) if v["scores"] else 0
        result.append({
            "asset_class":        asset_class,
            "n_exposures":        v["n"],
            "n_material":         v["material"],
            "n_very_material":    v["very_material"],
            "pct_material":       round(v["material"] / v["n"] * 100, 1) if v["n"] else 0,
            "total_asset_value":  round(v["asset_value"], 2),
            "mean_risk_score":    round(mean_score, 1),
            "hazards_present":    sorted(v["hazards"]),
        })
    return result


def _e1_9c_financial_exposure(rows: list[dict]) -> list[dict]:
    """
    E1-9C: Financial exposure at risk by hazard type.
    Sums asset_value for locations in each risk bucket.
    """
    from collections import defaultdict

    current = [r for r in rows if r["time_horizon"] == "current"]
    exposure: dict[tuple, float] = defaultdict(float)
    counts:   dict[tuple, int]   = defaultdict(int)

    for r in current:
        key = (r["hazard_type"], r["risk_bucket"])
        exposure[key] += (r["asset_value"] or 0)
        counts[key] += 1

    BUCKET_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "VERY_HIGH": 3}

    return sorted([{
        "hazard_type":      hazard,
        "risk_bucket":      bucket,
        "n_exposures":      counts[(hazard, bucket)],
        "total_exposure":   round(exposure[(hazard, bucket)], 2),
        "esrs_e1_category": "Material" if BUCKET_ORDER.get(bucket, 0) >= 1 else "Not material",
    } for (hazard, bucket) in exposure], key=lambda x: (x["hazard_type"], -BUCKET_ORDER.get(x["risk_bucket"], 0)))


def _e1_9d_adaptation() -> list[dict]:
    """
    E1-9D: Adaptation measures.
    CSRD requires disclosing planned adaptation actions.
    This is a template — customers populate via the API when submitting the package.
    """
    return [{
        "measure_id":   "ADM-001",
        "description":  "Physical risk monitoring via continuous score updates",
        "hazards":      ["flood", "wildfire", "heat_acute"],
        "status":       "Implemented — platform operational",
        "lead_time":    "Ongoing",
        "note": ("Adaptation measures at asset level are populated by the reporting "
                 "entity. This entry represents the climate monitoring capability itself."),
    }]


def _e1_9e_time_horizon_materiality(rows: list[dict], horizons: list[str]) -> list[dict]:
    """E1-9E: How materiality changes across time horizons."""
    from collections import defaultdict

    result = []
    for horizon in horizons:
        horizon_rows = [r for r in rows if r["time_horizon"] == horizon]
        if not horizon_rows:
            continue

        by_hazard: dict[str, list] = defaultdict(list)
        for r in horizon_rows:
            by_hazard[r["hazard_type"]].append(r["risk_score"])

        for hazard, scores in by_hazard.items():
            mean = sum(scores) / len(scores)
            material = sum(1 for s in scores if s >= MATERIAL_SCORE_THRESHOLD)
            result.append({
                "time_horizon":    horizon,
                "hazard_type":     hazard,
                "n_locations":     len(scores),
                "mean_score":      round(mean, 1),
                "n_material":      material,
                "pct_material":    round(material / len(scores) * 100, 1) if scores else 0,
                "materiality_level": (
                    "Very material" if mean >= VERY_MATERIAL_THRESHOLD
                    else "Material" if mean >= MATERIAL_SCORE_THRESHOLD
                    else "Not material"
                ),
            })

    return sorted(result, key=lambda x: (x["hazard_type"], x["time_horizon"]))


def _e1_9f_double_materiality(rows: list[dict], nace_codes: list[str]) -> dict:
    """
    E1-9F: Double materiality summary.

    Inside-out (financial materiality): how physical risks affect enterprise value.
    Outside-in (impact materiality): how the enterprise contributes to climate.
    For a SaaS platform customer, outside-in is typically low; we flag the NACE sector.
    """
    current = [r for r in rows if r["time_horizon"] == "current"]
    n_very_material = sum(1 for r in current if r["risk_score"] >= VERY_MATERIAL_THRESHOLD)
    n_material = sum(1 for r in current if r["risk_score"] >= MATERIAL_SCORE_THRESHOLD)
    n_total = len(current)

    # Financial materiality — derived from score distribution
    if n_very_material > n_total * 0.2:
        fm_level = "High"
    elif n_material > n_total * 0.1:
        fm_level = "Medium"
    else:
        fm_level = "Low"

    # Impact materiality — sector-based heuristic (NACE codes)
    HIGH_IMPACT_NACE = {"A", "B", "D", "E", "H"}  # agriculture, mining, energy, water, transport
    sector_letters = {c[0] for c in nace_codes} if nace_codes else set()
    im_level = "High" if sector_letters & HIGH_IMPACT_NACE else "Medium" if nace_codes else "Low"

    return {
        "financial_materiality": {
            "level":       fm_level,
            "rationale":   f"{n_material}/{n_total} exposures at or above material threshold ({MATERIAL_SCORE_THRESHOLD})",
            "n_very_material": n_very_material,
        },
        "impact_materiality": {
            "level":       im_level,
            "rationale":   f"Based on NACE sector classification: {nace_codes or ['not provided']}",
            "nace_codes":  nace_codes,
        },
        "overall_materiality": "Material" if fm_level in ("High", "Medium") or im_level in ("High", "Medium") else "Not material",
        "disclosure_required": True,
        "note": ("Double materiality assessment performed using EFRAG guidance. "
                 "Financial materiality is derived from physical risk scores. "
                 "Impact materiality is based on NACE sector classification and "
                 "should be supplemented with company-specific value chain analysis."),
    }


def _methodology(rows: list[dict], nace_codes: list[str]) -> dict:
    fingerprints = [r["regulatory_fingerprint"] for r in rows if r["regulatory_fingerprint"]]
    return {
        "scoring_model":        "3-model ensemble (XGBoost + LightGBM + Logistic Regression)",
        "spatial_framework":    "Uber H3 resolution 8 (~0.7 km² hexagonal grid)",
        "temporal_coverage":    f"{min(str(r['scored_at']) for r in rows)} to {max(str(r['scored_at']) for r in rows)}" if rows else None,
        "climate_scenarios":    "NGFS Phase 4 (baseline, orderly, disorderly, hot_house_world)",
        "data_sources":         ["ERA5-Land (ECMWF Copernicus)", "GloFAS River Discharge",
                                 "Sentinel-1 SAR (Copernicus EMS)", "NASA FIRMS Active Fire"],
        "hazard_coverage":      "Acute: flooding, wildfire, extreme heat. Chronic: planned for 2025.",
        "esrs_standard":        "ESRS E1 — Climate Change (CSRD delegated regulation 2023/2772)",
        "esrs_disclosure":      "E1-9 Physical risks and opportunities",
        "double_materiality":   "EFRAG IG 1 Materiality Assessment Implementation Guidance",
        "n_scores_underlying":  len(rows),
        "n_fingerprints":       len(fingerprints),
        "fingerprint_algorithm": "SHA-256 (independently verifiable)",
        "audit_note": ("Every score in this package carries a regulatory_fingerprint: "
                       "a SHA-256 hash of all model inputs. The platform operator can "
                       "reproduce any score on demand given its fingerprint, providing "
                       "a cryptographically verifiable audit trail for CSRD attestation."),
    }


def _empty_package(customer_id: str, period_start: date, period_end: date) -> dict:
    return {
        "framework":     "CSRD_ESRS_E1-9_2024",
        "customer_id":   customer_id,
        "period_start":  str(period_start),
        "period_end":    str(period_end),
        "n_locations":   0,
        "warning":       "No canonical scores found for this customer in the reporting period.",
        "e1_9a_material_risks":     [],
        "e1_9b_exposure_by_class":  [],
        "e1_9c_financial_exposure": [],
        "e1_9d_adaptation_measures": [],
        "e1_9e_time_horizon":       [],
        "e1_9f_double_materiality": {},
        "methodology":              {},
    }

"""
The core hazard→€ damage function — ONE place the platform turns a 0–100
physical-risk score into a fraction-of-value lost, shared by every financial
path (collateral valuation, insurance pricing, real-estate NOI, asset-mgmt VaR).

It replaces two honesty weaknesses that existed when each path had its own math:

  1. DISCRETISATION. The collateral path bucketed the score (L/M/H/VH) and read a
     flat % from a 4-row table, so a 51 and a 74 got the identical haircut and
     there was a cliff at every bucket boundary. Here the score drives a
     CONTINUOUS curve — piecewise-linear THROUGH the same disclosed anchor
     schedule (so the published magnitudes are unchanged at the anchors; only the
     cliffs are removed). A higher score always costs at least as much as a lower
     one, smoothly.

  2. IGNORED VULNERABILITY. construction_type / year_built / number_of_stories are
     captured on every asset and were then thrown away. A 1960s unreinforced-
     masonry building and a 2020 reinforced-concrete one got the identical haircut.
     `vulnerability_factor()` is a BOUNDED [0.6, 1.5] multiplier derived from those
     attributes, per hazard, from published vulnerability taxonomies (HAZUS
     construction classes; GEM/PAGER seismic fragility; wind building-code eras;
     JRC flood exposure by storey). It is DERIVED FROM ATTRIBUTES, not fitted to
     any client's loss history — a missing attribute contributes 1.0 (neutral) and
     is flagged incomplete, never guessed.

WITHIN-BAND GUARANTEE. The vulnerability-adjusted collateral haircut is capped at
the disclosed VH value for its peril, so the €-figures move *within* today's
published bands (differentiated around them), never silently inflated. Chronic
perils (heat/drought/pollution/frost/soil-water) are treated as vulnerability-
NEUTRAL for value impairment — we do not pretend a building's material changes how
a chronic-heat score impairs its value.

Everything here is a disclosed modelling assumption, versioned (DAMAGE_FUNCTION_VERSION)
so a change is visible; NONE of it is fitted to a specific institution.
"""
from __future__ import annotations

from typing import Optional

DAMAGE_FUNCTION_VERSION = "df-v1.0"

# ── the disclosed collateral-haircut schedule (unchanged magnitudes, now anchors) ──
# A real rule-of-thumb consistent with published climate-stress-test collateral-haircut
# guidance (0–30%+ by severity) — NOT a fitted or regulator-mandated figure.
RECOMMENDED_DISCOUNT_PCT = {"L": 0.0, "M": 5.0, "H": 15.0, "VH": 30.0}

# OPT-IN peril-specific relative severity (org_calc_settings.severity_model='peril_specific').
# Structural/total-loss perils skew higher; chronic/non-structural skew lower. Illustrative
# relative multipliers consistent with published physical-risk literature, not a fitted schedule.
PERIL_DISCOUNT_PCT = {
    "seismic":      {"L": 0.0, "M": 8.0, "H": 25.0, "VH": 45.0},
    "volcanic":     {"L": 0.0, "M": 8.0, "H": 25.0, "VH": 45.0},
    "wildfire":     {"L": 0.0, "M": 6.0, "H": 20.0, "VH": 38.0},
    "flood":        {"L": 0.0, "M": 5.0, "H": 18.0, "VH": 32.0},
    "coastal_flood": {"L": 0.0, "M": 6.0, "H": 22.0, "VH": 40.0},  # permanent inundation skews to total loss
    "storm":        {"L": 0.0, "M": 5.0, "H": 16.0, "VH": 30.0},
    "drought":      {"L": 0.0, "M": 3.0, "H": 8.0,  "VH": 15.0},
    "heat_acute":   {"L": 0.0, "M": 3.0, "H": 8.0,  "VH": 15.0},
    "heat_chronic": {"L": 0.0, "M": 3.0, "H": 8.0,  "VH": 15.0},
    "pollution":    {"L": 0.0, "M": 2.0, "H": 5.0,  "VH": 10.0},
}

# Insurance / NOI mean-damage-ratio anchor — Emanuel(2011)/CLIMADA sigmoid half-damage point.
HALF_DAMAGE_SCORE = 65.0

# Bucket representative scores — the score each disclosed schedule value is anchored AT. The
# continuous curve interpolates between these and is FLAT outside them, so it can never exceed
# the VH value (within-band) nor drop below L=0 (no negative "risk").
_BUCKET_MIDPOINT = {"L": 12.5, "M": 37.5, "H": 62.5, "VH": 87.5}

# Hazard → vulnerability family. Structural perils differentiate by building attributes; chronic
# perils are value-impairment-neutral to construction (we don't fabricate a material effect there).
_FIRE, _SEISMIC, _WIND, _FLOOD, _CHRONIC = "fire", "seismic", "wind", "flood", "chronic"
_HAZARD_FAMILY = {
    "wildfire": _FIRE, "seismic": _SEISMIC, "volcanic": _SEISMIC, "storm": _WIND, "flood": _FLOOD,
    "coastal_flood": _FLOOD,  # storey/elevation vulnerability — same family as pluvial/riverine flood
    "heat_acute": _CHRONIC, "heat_chronic": _CHRONIC, "drought": _CHRONIC,
    "pollution": _CHRONIC, "frost": _CHRONIC, "soil_water": _CHRONIC,
}

_VF_MIN, _VF_MAX = 0.6, 1.5   # the bounded range of the vulnerability multiplier


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _score_from(score: Optional[float], bucket: Optional[str]) -> float:
    """The continuous score to drive the curve. If only a bucket is known (a legacy caller),
    fall back to its representative score — which reproduces the disclosed schedule value exactly,
    so bucket-only callers are unchanged."""
    if score is not None:
        return _clamp(float(score), 0.0, 100.0)
    return _BUCKET_MIDPOINT.get(bucket or "", 0.0)


def _anchors(schedule: dict) -> list:
    return [(0.0, schedule["L"]), (_BUCKET_MIDPOINT["L"], schedule["L"]),
            (_BUCKET_MIDPOINT["M"], schedule["M"]), (_BUCKET_MIDPOINT["H"], schedule["H"]),
            (_BUCKET_MIDPOINT["VH"], schedule["VH"]), (100.0, schedule["VH"])]


def _interp(x: float, anchors: list) -> float:
    if x <= anchors[0][0]:
        return anchors[0][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x <= x1:
            return y1 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return anchors[-1][1]


# ── vulnerability: bounded, attribute-derived, literature-grounded, per hazard family ──

def _construction_class(construction_type: Optional[str]) -> Optional[str]:
    if not construction_type:
        return None
    s = str(construction_type).lower()
    if any(k in s for k in ("masonr", "brick", "unreinforced", "urm", "stone", "adobe")):
        return "masonry"
    if any(k in s for k in ("reinforced", "concret", "rc", "precast")):
        return "concrete"
    if "steel" in s:
        return "steel"
    if any(k in s for k in ("wood", "timber", "frame", "light")):
        return "wood"
    # ISO/ISO-CGL construction classes (common in insurance books): map to the nearest structural family.
    # "Fire Resistive" (ISO 6) behaves like reinforced concrete; "Non-Combustible" (ISO 3) like steel.
    # (Masonry-bearing ISO classes — Joisted Masonry, Masonry Non-Combustible — already matched above.)
    if "resistive" in s:
        return "concrete"
    if "combustible" in s:  # i.e. non-combustible / noncombustible (combustible-masonry cases matched above)
        return "steel"
    return None  # unknown class → neutral contribution


# Construction multiplier by hazard family (× on the base damage). Grounded in HAZUS building-type
# vulnerability (URM high for seismic), wildfire WUI material studies (wood high), and wind codes.
_CONSTRUCTION_VF = {
    _SEISMIC: {"masonry": 1.30, "wood": 1.05, "concrete": 0.82, "steel": 0.80},
    _FIRE:    {"wood": 1.35, "masonry": 0.85, "concrete": 0.80, "steel": 0.85},
    _WIND:    {"wood": 1.15, "masonry": 0.95, "concrete": 0.90, "steel": 0.90},
    # flood is driven by storey/elevation, not material; chronic is material-neutral.
}


def _age_vf(family: str, year_built: Optional[int]) -> Optional[float]:
    """Older stock is more vulnerable to structural perils (pre-code construction). Thresholds
    mark real building-code eras: modern seismic codes (~1980), post-Andrew wind (1992), modern
    flood-resilient design (~2000/2015)."""
    if not year_built:
        return None
    y = int(year_built)
    if family == _SEISMIC:
        return 1.25 if y < 1980 else (1.05 if y < 2010 else 0.85)
    if family == _WIND:
        return 1.20 if y < 1992 else (1.00 if y < 2010 else 0.85)
    if family == _FLOOD:
        return 1.15 if y < 2000 else (1.00 if y < 2015 else 0.90)
    if family == _FIRE:
        return 1.10 if y < 2008 else 1.00
    return None


def _stories_vf(family: str, stories: Optional[int]) -> Optional[float]:
    """Flood only: a single-storey asset has all its value at flood level; upper storeys escape."""
    if family != _FLOOD or not stories:
        return None
    n = int(stories)
    return 1.15 if n <= 1 else (1.05 if n == 2 else 0.90)


def vulnerability_factor(hazard: Optional[str], attrs: Optional[dict]) -> tuple:
    """Bounded [0.6, 1.5] damage multiplier from an asset's real attributes, for its headline hazard.
    Returns (factor, provenance). provenance = {applied, family, complete, drivers[], missing[]}.
    Derived from published vulnerability taxonomies, NOT fitted to any loss history. A missing
    attribute contributes 1.0 and is listed in `missing`; chronic perils and attribute-less assets
    (e.g. an equity holding) are neutral 1.0."""
    family = _HAZARD_FAMILY.get(hazard or "")
    # Asset ARCHETYPE vulnerability (impact-function library) — composes with the attribute factor below and
    # ALSO applies to chronic perils the attribute model leaves neutral (a data centre to heat, a thermal
    # plant to drought). Neutral 1.0 when the asset type is unknown or has no documented sensitivity.
    from ml.scoring.impact_library import asset_type_factor
    at_factor, at_prov = asset_type_factor((attrs or {}).get("asset_type"), hazard)
    at_driver = ([{"attr": "asset_type", "value": at_prov.get("asset_type"), "tier": at_prov.get("tier"),
                   "factor": round(at_factor, 3)}] if at_prov.get("applied") else [])

    if family is None or family == _CHRONIC:
        applied = at_prov.get("applied", False)
        return _clamp(at_factor, _VF_MIN, _VF_MAX), {"applied": applied, "family": family or "unknown",
            "reason": ("asset-archetype vulnerability (chronic / non-structural peril)" if applied
                       else "vulnerability-neutral (chronic / non-structural peril)"),
            "complete": True, "drivers": at_driver, "missing": []}
    if not attrs:
        return _clamp(at_factor, _VF_MIN, _VF_MAX), {"applied": at_prov.get("applied", False), "family": family,
            "reason": "asset-archetype only (no construction attributes on file)",
            "complete": False, "drivers": at_driver, "missing": ["construction_type", "year_built"]}

    factor = at_factor
    drivers, missing = list(at_driver), []

    # construction
    if family in _CONSTRUCTION_VF:
        cls = _construction_class(attrs.get("construction_type"))
        if cls and cls in _CONSTRUCTION_VF[family]:
            f = _CONSTRUCTION_VF[family][cls]
            factor *= f
            drivers.append({"attr": "construction_type", "value": cls, "factor": round(f, 3)})
        else:
            missing.append("construction_type")

    # age
    af = _age_vf(family, attrs.get("year_built"))
    if af is not None:
        factor *= af
        drivers.append({"attr": "year_built", "value": attrs.get("year_built"), "factor": round(af, 3)})
    else:
        missing.append("year_built")

    # storeys (flood)
    sf = _stories_vf(family, attrs.get("number_of_stories"))
    if sf is not None:
        factor *= sf
        drivers.append({"attr": "number_of_stories", "value": attrs.get("number_of_stories"), "factor": round(sf, 3)})

    factor = _clamp(factor, _VF_MIN, _VF_MAX)
    return round(factor, 3), {
        "applied": bool(drivers), "family": family,
        "complete": len(missing) == 0, "drivers": drivers, "missing": missing,
    }


# ── the two public damage quantities ──

def collateral_haircut_pct(score: Optional[float], bucket: Optional[str], hazard: Optional[str] = None,
                           severity_model: str = "universal", attrs: Optional[dict] = None) -> float:
    """The value impairment % for lending/valuation. Continuous in the score, differentiated by
    building vulnerability, and CAPPED at the peril's disclosed VH value (within-band). Expected
    impairment — deliberately NOT the insurance PML sigmoid, which is a larger worst-case quantity."""
    schedule = (PERIL_DISCOUNT_PCT[hazard] if severity_model == "peril_specific" and hazard in PERIL_DISCOUNT_PCT
                else RECOMMENDED_DISCOUNT_PCT)
    base = _interp(_score_from(score, bucket), _anchors(schedule))
    vf, _ = vulnerability_factor(hazard, attrs)
    return round(min(base * vf, schedule["VH"]), 2)


def mean_damage_ratio(score: float, hazard: Optional[str] = None, attrs: Optional[dict] = None) -> float:
    """Insurance / NOI scenario-loss fraction (PML-style): Emanuel(2011)/CLIMADA sigmoid
    v³/(1+v³), v=score/HALF_DAMAGE_SCORE, times the bounded vulnerability factor, clamped to [0,1].
    With no attrs the factor is 1.0, so the bare-sigmoid callers are unchanged."""
    v = max(0.0, score) / HALF_DAMAGE_SCORE
    base = v ** 3 / (1.0 + v ** 3)
    vf, _ = vulnerability_factor(hazard, attrs)
    return _clamp(base * vf, 0.0, 1.0)

"""Solvency II STANDARD-FORMULA natural-catastrophe SCR — all five perils (Del. Reg. (EU) 2015/35, Art. 120-125).

Prescribed regulatory calculation, not a model: EIOPA's own per-region factors and correlation matrices, cited to
the Official Journal, loaded from data/reference/*.json (never hard-coded). One region-level calculator drives the
four regional perils; subsidence is a France-only constant. The five combine independently (Art. 120):

    SCR_natCAT = sqrt( SCR_windstorm² + SCR_earthquake² + SCR_flood² + SCR_hail² + SCR_subsidence² )

Per peril (region level, gross of reinsurance):
    L_r   = Q(peril,r) · SI_r
    SCR_r = gross_factor(peril) · L_r      windstorm/hail 1.20 (A,B both), flood 1.10, earthquake 1.00 (single)
    SCR_peril = sqrt( ΣΣ Corr(peril,r,s) · SCR_r · SCR_s )

APPROXIMATION (disclosed, same as the windstorm module): sums insured aggregated at COUNTRY level — one risk zone
per region, risk weight W=1, perfect within-country correlation (WSI_r = Σ sum insured in region r). Q and the
inter-region correlation are the EXACT Annex values; the intra-country Annex IX/X zone weights and zone
diversification (Annex XXII-XXVI) are not applied — an approximation of the exact zonal figure. Flood/hail also
add a motor sum-insured component (1.5×/5× LoB 5,17) we do not include — a property-book view. Exposure outside a
peril's Annex regions is reported separately (Art. *(8-9) premium charge not computed), never silently dropped.
"""
from __future__ import annotations

import json
import math
import os
from functools import lru_cache

_WINDSTORM_PATH = os.path.join("data", "reference", "solvency2_windstorm_annex_v.json")
_NATCAT_PATH = os.path.join("data", "reference", "solvency2_natcat_annexes.json")
_ZONAL_PATH = os.path.join("data", "reference", "solvency2_zonal.json")
_SUBSIDENCE_FACTOR = 0.0005   # Art. 125: L_subsidence = 0.0005 · WSI (France only, residential LoB 7/19)
_REGIONAL_PERILS = ("windstorm", "earthquake", "flood", "hail")
# Motor sum-insured multiplier added to the zonal sum insured (LoB 5/17). Only flood and hail carry one:
# Art. 123(7) SI = property + onshore-property + 1.5·motor;  Art. 124(7) SI = property + onshore-property + 5·motor.
# Windstorm (Art.121(7)) and earthquake (Art.122(4)) have NO motor term. Our book is a property Statement of Values
# (LoB 6/7/18/19), so motor is normally absent — but if a policy carries `motor_sum_insured_eur`, it is included here.
_MOTOR_MULTIPLIER = {"flood": 1.5, "hail": 5.0}


def _policy_si(pol: dict, peril: str) -> float:
    """Sum insured for a peril: property TIV plus the prescribed motor multiple where the Article defines one."""
    si = pol.get("sum_insured_eur") or 0
    m = _MOTOR_MULTIPLIER.get(peril)
    if m:
        si += m * (pol.get("motor_sum_insured_eur") or 0)
    return si


@lru_cache(maxsize=1)
def _windstorm_file() -> dict | None:
    if not os.path.exists(_WINDSTORM_PATH):
        return None
    with open(_WINDSTORM_PATH) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _natcat_file() -> dict | None:
    if not os.path.exists(_NATCAT_PATH):
        return None
    with open(_NATCAT_PATH) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _zonal_file() -> dict | None:
    if not os.path.exists(_ZONAL_PATH):
        return None
    with open(_ZONAL_PATH) as f:
        return json.load(f)


def _zonal_params(peril: str, region: str) -> dict | None:
    """Exact-zonal tables {n_zones, zones:{num:{name,w}}, correlation} for a (peril, region), if loaded/verified."""
    z = _zonal_file()
    if not z or not z.get("verified"):
        return None
    return (z.get(peril) or {}).get(region)


def _exact_zonal_loss(zonal: dict, zone_si: dict[str, float], q: float) -> float | None:
    """Specified loss L_r = Q · sqrt(ΣΣ Corr(i,j)·WSI_i·WSI_j), WSI_z = W_z·SI_z (Art. 121-124(5)).
    Returns None if any exposed zone is not in the region's table (so the caller can fall back honestly)."""
    zones, corr = zonal["zones"], zonal["correlation"]
    exposed = sorted(zone_si)
    wsi = {}
    for z in exposed:
        if z not in zones:
            return None
        wsi[z] = zones[z]["w"] * zone_si[z]
    var = sum(corr[i][j] * wsi[i] * wsi[j] for i in exposed for j in exposed)
    return q * math.sqrt(var) if var > 0 else 0.0


def _peril_params(peril: str) -> dict | None:
    """Unified params {region_order, regions, correlation, iso2_to_region, gross_factor, citation} for a peril."""
    if peril == "windstorm":
        p = _windstorm_file()
        if not p or not p.get("verified"):
            return None
        return {**p, "gross_factor": 1.20, "citation": p.get("_citation", "Del. Reg. (EU) 2015/35, Art. 121 + Annex V"),
                "params_version": p.get("_version")}
    f = _natcat_file()
    if not f or not f.get("verified") or peril not in f:
        return None
    return {**f[peril], "params_version": f.get("_version")}


def standard_formula_peril(policies: list[dict], peril: str) -> dict:
    """Prescribed standard-formula SCR for one regional peril (gross of reinsurance). Honest when it cannot run."""
    p = _peril_params(peril)
    if not p:
        return {"available": False, "reason": f"official Annex factors for {peril} not loaded/verified", "peril": peril}
    order, corr = p["region_order"], p["correlation"]
    idx = {r: i for i, r in enumerate(order)}
    iso2region, regions_meta, gross = p["iso2_to_region"], p["regions"], p["gross_factor"]

    si_by_region: dict[str, float] = {}
    n_by_region: dict[str, int] = {}
    zone_si: dict[str, dict[str, float]] = {}   # region -> {cresta_zone label -> sum insured}
    unzoned_si: dict[str, float] = {}           # region -> sum insured on policies with no cresta_zone
    other_si = 0.0
    motor_included = 0.0
    for pol in policies:
        si = _policy_si(pol, peril)   # property TIV + prescribed motor multiple (flood 1.5×, hail 5×) where applicable
        if si <= 0:
            continue
        if peril in _MOTOR_MULTIPLIER:
            motor_included += _MOTOR_MULTIPLIER[peril] * (pol.get("motor_sum_insured_eur") or 0)
        reg = iso2region.get(str(pol.get("country") or "").strip().upper())
        if reg is None:
            other_si += si
            continue
        si_by_region[reg] = si_by_region.get(reg, 0.0) + si
        n_by_region[reg] = n_by_region.get(reg, 0) + 1
        raw = pol.get("cresta_zone")
        zn = str(raw).strip().upper() if raw not in (None, "") else None   # a LABEL: "20", "AB", "07" — never parsed as a number
        if zn is not None and zn.isdigit():
            zn = str(int(zn))   # normalise numeric labels ("07" -> "7") to match the table keys
        if zn is not None:
            zone_si.setdefault(reg, {})[zn] = zone_si.setdefault(reg, {}).get(zn, 0.0) + si
        else:
            unzoned_si[reg] = unzoned_si.get(reg, 0.0) + si

    if not si_by_region:
        return {"available": False, "peril": peril, "reason": f"no sum insured in an Annex {peril} region",
                "other_regions_sum_insured_eur": round(other_si), "citation": p["citation"]}

    # per region: EXACT zonal (Annex IX/X/XXIII-XXVI) when the region's tables are loaded AND every policy there
    # carries a cresta_zone — the vendor-standard path; otherwise the country-level approximation (Q·SI). Honest
    # per-region method flag, and a fall-back if a policy cites a zone the table doesn't know.
    per_region, scr_r = [], {}
    n_zonal_regions = 0
    for reg, si in sorted(si_by_region.items(), key=lambda kv: -kv[1]):
        q = regions_meta[reg]["q"]
        zonal = _zonal_params(peril, reg)
        loss = None
        method = "country_level"
        if zonal and reg in zone_si and not unzoned_si.get(reg):
            loss = _exact_zonal_loss(zonal, zone_si[reg], q)
            if loss is not None:
                method = "exact_zonal"
        if loss is None:                            # fall back: L_r = Q · SI_r (one zone, W=1, perfect correlation)
            loss = q * si
        scr = gross * loss                          # SCR_r = gross · L_r
        scr_r[reg] = scr
        n_zonal_regions += method == "exact_zonal"
        per_region.append({"region": reg, "region_name": regions_meta[reg]["name"], "sum_insured_eur": round(si),
                           "n_policies": n_by_region[reg], "risk_factor_q": q, "scr_region_eur": round(scr),
                           "method": method})

    var = sum(corr[r][idx[s]] * scr_r[r] * scr_r[s] for r in scr_r for s in scr_r)
    scr_peril = math.sqrt(var) if var > 0 else 0.0
    undiversified = sum(scr_r.values())
    return {
        "available": True, "peril": peril, "basis": "solvency_ii_standard_formula", "gross_of_reinsurance": True,
        "scr_eur": round(scr_peril), "undiversified_scr_eur": round(undiversified),
        "regional_diversification_benefit_eur": round(undiversified - scr_peril),
        "per_region": per_region, "n_regions": len(per_region),
        # how many regions used the EXACT zonal calc (Annex IX/X + zone-correlation) vs the country-level approximation
        "n_exact_zonal_regions": n_zonal_regions,
        "other_regions_sum_insured_eur": round(other_si), "gross_factor": gross,
        # motor sum-insured included per Art. 123(7)/124(7) — 0 for a pure property book (LoB 6/7/18/19)
        "motor_component_eur": round(motor_included) if peril in _MOTOR_MULTIPLIER else None,
        "citation": p["citation"], "params_version": p.get("params_version"),
    }


def subsidence_scr(policies: list[dict]) -> dict:
    """Art. 125 — subsidence risk, FRANCE only, single instantaneous scenario. EXACT zonal when the Annex IX/X/XXVI
    France table is loaded and every French policy carries a cresta_zone: L = 0.0005 · sqrt(ΣΣ Corr(i,j)·W_i·SI_i·W_j·SI_j);
    otherwise the country-level approximation 0.0005 · SI(France) (residential LoB 7/19 not separated) — disclosed."""
    fr = [pol for pol in policies if str(pol.get("country") or "").strip().upper() in ("FR", "MC", "AD")]
    si_fr = sum((pol.get("sum_insured_eur") or 0) for pol in fr)
    if si_fr <= 0:
        return {"available": False, "peril": "subsidence", "reason": "no French sum insured (subsidence is France-only)"}
    zonal = _zonal_params("subsidence", "FR")
    zone_si: dict[str, float] = {}
    unzoned = 0.0
    for pol in fr:
        raw = pol.get("cresta_zone")
        zn = str(raw).strip().upper() if raw not in (None, "") else None
        if zn is not None and zn.isdigit():
            zn = str(int(zn))
        if zn is None:
            unzoned += pol.get("sum_insured_eur") or 0
        else:
            zone_si[zn] = zone_si.get(zn, 0.0) + (pol.get("sum_insured_eur") or 0)
    loss, method = None, "country_level"
    if zonal and zone_si and not unzoned:
        loss = _exact_zonal_loss(zonal, zone_si, _SUBSIDENCE_FACTOR)
        if loss is not None:
            method = "exact_zonal"
    if loss is None:
        loss = _SUBSIDENCE_FACTOR * si_fr
    return {"available": True, "peril": "subsidence", "basis": "solvency_ii_standard_formula",
            "scr_eur": round(loss), "french_sum_insured_eur": round(si_fr), "method": method,
            "gross_factor": _SUBSIDENCE_FACTOR, "citation": "Del. Reg. (EU) 2015/35, Art. 125 + Annexes IX, X, XXVI",
            "approximation": ("exact zonal (Annex X weights + Annex XXVI zone-correlation)" if method == "exact_zonal" else
                              "0.0005 × all French property sum insured — the exact cell is residential LoB 7/19 by "
                              "subsidence zone; tag policies with cresta_zone for the exact zonal figure")}


def natcat_scr(policies: list[dict]) -> dict:
    """Full Solvency II standard-formula natural-catastrophe SCR — the five sub-modules combined (Art. 120):
    SCR_natCAT = sqrt(Σ SCR_peril²). Perils with no exposure contribute 0. Honest and cited throughout."""
    perils = {pk: standard_formula_peril(policies, pk) for pk in _REGIONAL_PERILS}
    perils["subsidence"] = subsidence_scr(policies)
    scrs = {pk: (r.get("scr_eur") or 0) if r.get("available") else 0 for pk, r in perils.items()}
    agg = math.sqrt(sum(v * v for v in scrs.values()))
    undiversified = sum(scrs.values())
    return {
        "available": any(r.get("available") for r in perils.values()),
        "basis": "solvency_ii_standard_formula",
        "regulation": "Commission Delegated Regulation (EU) 2015/35, Art. 120-125 (S.27.01 non-life CAT)",
        "natcat_scr_eur": round(agg),
        "undiversified_sum_eur": round(undiversified),
        "cross_peril_diversification_benefit_eur": round(undiversified - agg),
        "scr_by_peril_eur": {pk: round(v) for pk, v in scrs.items()},
        "perils": perils,
        "aggregation": "SCR_natCAT = sqrt(Σ SCR_peril²) — the five nat-cat sub-modules are independent (Art. 120(2)).",
        "note": ("Prescribed standard-formula NatCat SCR from EIOPA's own per-region factors (Del. Reg. 2015/35, "
                 "Annexes V-VIII + Art. 125), cited — not a model. Flood/hail include the Art. 123(7)/124(7) motor "
                 "term where a policy carries motor sum insured (0 for a pure property book). Gross of reinsurance; "
                 "man-made catastrophe out of scope. Intra-country: the EXACT zonal calc (Annex IX zones, Annex X "
                 "risk weights, Annex XXIII-XXVI zone-correlation) is used for any region whose zone tables are "
                 "loaded AND whose policies carry a cresta_zone — the vendor-standard path (a Statement of Values "
                 "normally already holds the CRESTA/postcode zone per risk). Regions without loaded tables or "
                 "zone-tagged policies use the country-level approximation (Q·SI, perfect within-country "
                 "correlation), a documented, cited upper bound on the exact zonal SCR."),
    }

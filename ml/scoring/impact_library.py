"""Impact-function library — per-asset-archetype hazard vulnerability.

The attribute model in damage_function.py differentiates a building by construction / age / storeys. This
library adds the other axis best-of-breed vendors compete on (S&P's 270+ asset-type curves): the ASSET
ARCHETYPE itself — a data centre, a thermal power plant, a highway bridge, a masonry dwelling, a vineyard —
each with a documented per-hazard vulnerability profile. It also covers the CHRONIC perils the attribute model
leaves neutral (a data centre IS heat-sensitive; a thermal plant IS drought/water-sensitive), where that
sensitivity is documented.

Honest by construction: these are DISCLOSED RELATIVE TIERS grounded in published taxonomies (FEMA HAZUS
occupancy & default damage functions; GEM/PAGER; sector resilience studies), not per-asset loss-fitted curves.
Each archetype cites its basis. Tiers map to a bounded multiplier and compose (capped) with the attribute
factor, so the within-band guarantee of df-v1.0 still holds. Extensible: add an archetype = add one row; the
library version + count are reportable, and every archetype is validatable through the backtesting framework.
"""
from __future__ import annotations

from typing import Optional

IMPACT_LIBRARY_VERSION = "impact-lib-v1.0"

# tier → bounded damage multiplier. VH/H raise, L/VL lower, M/N are neutral.
TIER_MULT = {"VH": 1.45, "H": 1.25, "M": 1.0, "N": 1.0, "L": 0.85, "VL": 0.7}
_BOUND = (0.6, 1.5)

# canonical hazard keys the tiers are quoted against (coastal_flood shares flood; storm == wind)
_ALIAS = {"coastal_flood": "flood", "storm": "wind", "heat_chronic": "heat", "soil_water": "soil_water"}

# ── the archetype catalog ────────────────────────────────────────────────────────────────────────
# (key, category, label, {hazard: tier}, source). Only non-neutral tiers are listed; anything unlisted is M
# for structural perils (flood/seismic/wind/wildfire) and N (neutral) for chronic perils (heat/drought/…).
_A = [
    # ── residential (HAZUS RES) ──
    ("res_wood_frame",      "residential", "Wood-frame dwelling (RES1)",   {"wildfire": "VH", "wind": "H", "seismic": "L"}, "HAZUS RES1 / WUI material studies"),
    ("res_masonry",         "residential", "Masonry dwelling (RES1-URM)",  {"seismic": "VH", "wildfire": "L", "wind": "L"}, "HAZUS URM fragility"),
    ("res_mobile_home",     "residential", "Manufactured / mobile home (RES2)", {"wind": "VH", "flood": "H", "wildfire": "H"}, "HAZUS RES2"),
    ("res_multifamily",     "residential", "Multi-family apartment (RES3)", {"flood": "L"}, "HAZUS RES3 (upper storeys reduce flood loss)"),
    # ── commercial (HAZUS COM) ──
    ("com_retail",          "commercial",  "Retail / storefront (COM1)",    {"flood": "H"}, "HAZUS COM1 (ground-floor contents)"),
    ("com_office",          "commercial",  "Office building (COM4)",        {"flood": "L", "seismic": "M"}, "HAZUS COM4"),
    ("com_hotel",           "commercial",  "Hotel / lodging (COM1)",        {}, "HAZUS COM1"),
    ("com_hospital",        "commercial",  "Hospital (COM6)",               {"flood": "H", "seismic": "H", "heat": "M"}, "HAZUS COM6 (critical facility)"),
    ("com_data_centre",     "commercial",  "Data centre",                   {"flood": "VH", "heat": "VH", "storm": "H", "drought": "M"}, "Uptime Institute / sector cooling-water & heat studies"),
    ("com_warehouse",       "commercial",  "Warehouse / logistics (COM2)",  {"flood": "M", "wind": "H"}, "HAZUS COM2 (large roof span)"),
    # ── industrial (HAZUS IND) ──
    ("ind_heavy_factory",   "industrial",  "Heavy industrial plant (IND1)", {"flood": "H", "seismic": "H"}, "HAZUS IND1"),
    ("ind_light_mfg",       "industrial",  "Light manufacturing (IND2)",    {"flood": "M"}, "HAZUS IND2"),
    ("ind_chemical",        "industrial",  "Chemical / process plant (IND5)", {"flood": "VH", "seismic": "H", "pollution": "H"}, "HAZUS IND5 / process-safety studies"),
    ("ind_refinery",        "industrial",  "Refinery",                      {"flood": "VH", "storm": "H", "seismic": "H", "heat": "M"}, "sector cat-loss studies"),
    ("ind_mine",            "industrial",  "Mine / extraction site",        {"flood": "H", "drought": "H", "soil_water": "H"}, "ICMM water-risk studies"),
    # ── power & utilities ──
    ("pow_thermal",         "power",       "Thermal power plant",           {"drought": "VH", "heat": "H", "flood": "H", "soil_water": "H"}, "IEA/EPRI once-through cooling water-stress studies"),
    ("pow_nuclear",         "power",       "Nuclear power plant",           {"drought": "H", "heat": "H", "flood": "VH", "coastal_flood": "VH", "seismic": "H"}, "IAEA siting / cooling-water studies"),
    ("pow_hydro",           "power",       "Hydropower",                    {"drought": "VH", "flood": "H"}, "IHA drought-generation studies"),
    ("pow_solar",           "power",       "Solar PV farm",                 {"storm": "H", "wildfire": "M", "heat": "L"}, "NREL hail/wind loss studies"),
    ("pow_wind",            "power",       "Wind farm",                     {"storm": "VH", "wildfire": "M"}, "turbine survival wind-speed limits"),
    ("pow_substation",      "power",       "Electrical substation / grid",  {"flood": "VH", "wildfire": "H", "storm": "H", "heat": "H"}, "EPRI grid-resilience studies"),
    # ── transport & infrastructure ──
    ("inf_road_bridge",     "infrastructure", "Road bridge",                {"flood": "VH", "seismic": "H", "soil_water": "H"}, "HAZUS transportation / scour studies"),
    ("inf_highway",         "infrastructure", "Highway / road",             {"flood": "H", "heat": "M", "soil_water": "H"}, "HAZUS transportation"),
    ("inf_railway",         "infrastructure", "Railway line",               {"flood": "H", "heat": "H", "soil_water": "H"}, "rail buckling heat studies"),
    ("inf_port",            "infrastructure", "Port / terminal",            {"coastal_flood": "VH", "flood": "H", "storm": "VH"}, "PIANC coastal-exposure studies"),
    ("inf_airport",         "infrastructure", "Airport",                    {"flood": "H", "coastal_flood": "H", "heat": "M"}, "ICAO climate-resilience studies"),
    ("inf_pipeline",        "infrastructure", "Pipeline",                   {"flood": "H", "seismic": "H", "soil_water": "VH", "wildfire": "H"}, "ground-movement / fault-crossing studies"),
    ("inf_telecom_tower",   "infrastructure", "Telecom tower",              {"storm": "VH", "wildfire": "H"}, "wind-load design studies"),
    ("inf_water_treatment", "infrastructure", "Water/wastewater plant",     {"flood": "VH", "drought": "H"}, "HAZUS lifeline / EPA studies"),
    # ── agriculture ──
    ("agri_cropland_rainfed",  "agriculture", "Rainfed cropland",           {"drought": "VH", "heat": "H", "flood": "H", "soil_water": "VH"}, "FAO/IPCC AR6 WGII agronomic studies"),
    ("agri_cropland_irrigated","agriculture", "Irrigated cropland",          {"drought": "H", "heat": "H", "soil_water": "H"}, "FAO irrigation water-stress studies"),
    ("agri_orchard_perennial", "agriculture", "Orchard / perennial (olive, citrus, cocoa)", {"drought": "VH", "heat": "VH", "frost": "H"}, "permanent-crop climate studies"),
    ("agri_vineyard",          "agriculture", "Vineyard",                   {"heat": "VH", "drought": "H", "frost": "H", "wildfire": "H"}, "viticulture climate studies"),
    ("agri_livestock",         "agriculture", "Livestock / pasture",        {"heat": "VH", "drought": "VH"}, "livestock heat-stress studies"),
    ("agri_greenhouse",        "agriculture", "Greenhouse / protected crop",{"storm": "VH", "heat": "H"}, "protected-cropping wind studies"),
    # ── real-estate & finance-relevant ──
    ("re_commercial",       "real_estate", "Commercial real estate (generic)", {"flood": "H"}, "generic — refine to a specific archetype where known"),
    ("re_residential",      "real_estate", "Residential real estate (generic)", {}, "generic — refine to a specific archetype where known"),
    ("re_land",             "real_estate", "Undeveloped land",              {"wildfire": "H", "flood": "M"}, "land-cover exposure"),
    ("fin_equity_holding",  "financial",   "Equity / securities holding",   {}, "no located structure — vulnerability-neutral"),
    ("fin_sovereign",       "financial",   "Sovereign exposure",            {}, "no located structure — vulnerability-neutral"),
]

IMPACT_LIBRARY: dict = {
    key: {"category": cat, "label": label, "tiers": tiers, "source": src}
    for (key, cat, label, tiers, src) in _A
}


def _clamp(x: float) -> float:
    return max(_BOUND[0], min(_BOUND[1], x))


def asset_type_factor(asset_type: Optional[str], hazard: Optional[str]) -> tuple:
    """Bounded per-archetype vulnerability multiplier for a hazard. (factor, provenance).
    Unknown asset type or an archetype with no tier for this hazard → neutral 1.0 (never fabricated)."""
    if not asset_type or asset_type not in IMPACT_LIBRARY:
        return 1.0, {"applied": False, "reason": "unknown or unspecified asset type"}
    entry = IMPACT_LIBRARY[asset_type]
    hz = _ALIAS.get(hazard or "", hazard or "")
    tier = entry["tiers"].get(hazard or "") or entry["tiers"].get(hz)
    if tier is None:
        return 1.0, {"applied": False, "asset_type": asset_type, "category": entry["category"],
                     "reason": f"no documented {hazard} sensitivity for this archetype"}
    return _clamp(TIER_MULT[tier]), {"applied": True, "asset_type": asset_type, "category": entry["category"],
                                     "tier": tier, "source": entry["source"], "version": IMPACT_LIBRARY_VERSION}


def library_summary() -> dict:
    by_cat: dict = {}
    for e in IMPACT_LIBRARY.values():
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1
    return {"version": IMPACT_LIBRARY_VERSION, "n_asset_types": len(IMPACT_LIBRARY),
            "by_category": dict(sorted(by_cat.items()))}

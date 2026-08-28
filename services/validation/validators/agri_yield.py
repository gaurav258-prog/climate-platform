"""Agri yield backtest — the model's growing-season hazard signal vs real observed yield, over decades.

Option A: for each crop belt we hold ERA5 monthly climate for (data/era5_baseline/{belt}_1991_2024_monthly.nc),
compute the growing-season drought/heat index per year (ml.features.drought), and test whether that signal
tracks the OBSERVED yield anomaly (crop_yield_observations, FAOSTAT-grade). This validates the fundamental
premise the whole agri product rests on — that the hazard drives the yield — against ~30 years of real data,
per commodity. A `rank` test (continuous predictor vs continuous observed), oriented so a higher predicted
yield effect should mean a higher observed yield; honest per-crop, weak where weak.

Drivers are per-crop and cited to the calibration: olive/wheat are drought-driven (SPEI), West-Africa cocoa is
acute-heat driven (Jan–Mar harmattan). Adding a crop = one BELT_CONFIG row (once its ERA5 belt is fetched).
"""
from __future__ import annotations

import os

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

# belt → (commodity, countries, driver, sign, growing-season months). driver='spei' (drought; wetter→+yield,
# sign +1) or 'temp_anom_c' (heat; hotter→−yield, sign −1). Months are the crop's climate-sensitive window.
BELT_CONFIG: dict = {
    "spain_olive":       {"commodity": "Olive oil",   "countries": ["ES"],       "driver": "spei",        "sign": 1,  "months": [4, 5, 6, 7, 8, 9], "src": "olive = drought-driven (SPEI), calibration"},
    "us_cornbelt":       {"commodity": "Maize",       "countries": ["US"],       "driver": "spei",        "sign": 1,  "months": [6, 7, 8],          "src": "US maize summer moisture (SPEI)"},
    "turkey_wheat":      {"commodity": "Wheat",       "countries": ["TR"],       "driver": "spei",        "sign": 1,  "months": [3, 4, 5],          "src": "winter-wheat spring grain-fill moisture"},
    "morocco_wheat":     {"commodity": "Wheat",       "countries": ["MA"],       "driver": "spei",        "sign": 1,  "months": [2, 3, 4],          "src": "Maghreb rainfed wheat (SPEI)"},
    "australia_wheat":   {"commodity": "Wheat",       "countries": ["AU"],       "driver": "spei",        "sign": 1,  "months": [6, 7, 8, 9],       "src": "Australian winter-spring wheat (SPEI)"},
    "west_africa_cocoa": {"commodity": "Cocoa",       "countries": ["CI", "GH"], "driver": "temp_anom_c", "sign": -1, "months": [1, 2, 3],          "src": "cocoa = Jan–Mar harmattan heat, calibration re-fit"},
    # ── expansion: all belts below already have ERA5 on disk + observed yield (FAOSTAT) ──
    "brazil_coffee":     {"commodity": "Coffee",      "countries": ["BR"],       "driver": "spei", "sign": 1, "months": [10, 11, 12, 1, 2, 3], "src": "Brazil coffee SH growing-season moisture"},
    "brazil_soy":        {"commodity": "Soybean",     "countries": ["BR"],       "driver": "spei", "sign": 1, "months": [12, 1, 2],           "src": "Brazil soy SH summer moisture"},
    "bordeaux_wine":     {"commodity": "Wine grapes", "countries": ["FR"],       "driver": "temp_anom_c", "sign": -1, "months": [6, 7, 8, 9],  "src": "Bordeaux vintage summer heat"},
    "india_rice":        {"commodity": "Rice",        "countries": ["IN"],       "driver": "spei", "sign": 1, "months": [6, 7, 8, 9],        "src": "India kharif rice monsoon moisture"},
    "india_cane":        {"commodity": "Cane sugar",  "countries": ["IN"],       "driver": "spei", "sign": 1, "months": [6, 7, 8, 9],        "src": "India cane monsoon moisture"},
    "south_africa_maize":{"commodity": "Maize",       "countries": ["ZA"],       "driver": "spei", "sign": 1, "months": [12, 1, 2],           "src": "South Africa summer maize moisture"},
    "argentina_wheat":   {"commodity": "Wheat",       "countries": ["AR"],       "driver": "spei", "sign": 1, "months": [7, 8, 9, 10],       "src": "Argentina winter-spring wheat"},
    "canada_prairies":   {"commodity": "Wheat",       "countries": ["CA"],       "driver": "spei", "sign": 1, "months": [5, 6, 7],           "src": "Canadian prairies spring wheat"},
    "kazakhstan_wheat":  {"commodity": "Wheat",       "countries": ["KZ"],       "driver": "spei", "sign": 1, "months": [5, 6, 7],           "src": "Kazakh spring wheat"},
    "iran_wheat":        {"commodity": "Wheat",       "countries": ["IR"],       "driver": "spei", "sign": 1, "months": [2, 3, 4],           "src": "Iran rainfed wheat"},
    "tunisia_wheat":     {"commodity": "Wheat",       "countries": ["TN"],       "driver": "spei", "sign": 1, "months": [2, 3, 4],           "src": "Tunisia rainfed wheat"},
    "algeria_wheat":     {"commodity": "Wheat",       "countries": ["DZ"],       "driver": "spei", "sign": 1, "months": [2, 3, 4],           "src": "Algeria rainfed wheat"},
    "syria_wheat":       {"commodity": "Wheat",       "countries": ["SY"],       "driver": "spei", "sign": 1, "months": [3, 4, 5],           "src": "Syria rainfed wheat"},
    "nigeria_sorghum":   {"commodity": "Sorghum",     "countries": ["NG"],       "driver": "spei", "sign": 1, "months": [6, 7, 8, 9],        "src": "Nigeria wet-season sorghum"},
    "spain_beet":        {"commodity": "Sugar beet",  "countries": ["ES"],       "driver": "spei", "sign": 1, "months": [5, 6, 7, 8],        "src": "Spain sugar beet summer moisture"},
    "spain_central":     {"commodity": "Barley",      "countries": ["ES"],       "driver": "spei", "sign": 1, "months": [3, 4, 5],           "src": "Central Spain rainfed barley"},
}


def _detrended_yield_anomaly(session: Session, commodity: str, countries: list[str]) -> dict:
    """Observed yield anomaly with the technology trend removed. Correlating raw yields with climate is
    confounded because yields rise ~1–2%/yr from genetics/inputs; we fit that long-term trend (linear on
    yield_tonnes_ha over the full record) and take the fractional residual as the climate-attributable
    anomaly per year. Standard crop-climate practice, applied uniformly to every crop (not per-crop tuning)."""
    import numpy as np
    rows = session.execute(text("""
        SELECT season_year, AVG(CAST(yield_tonnes_ha AS FLOAT)) AS y
        FROM crop_yield_observations
        WHERE commodity = :c AND country = ANY(:cc) AND yield_tonnes_ha IS NOT NULL
        GROUP BY season_year ORDER BY season_year
    """), {"c": commodity, "cc": countries}).mappings().all()
    yrs = np.array([int(r["season_year"]) for r in rows], float)
    yld = np.array([float(r["y"]) for r in rows], float)
    if len(yrs) < 8 or np.ptp(yld) == 0:
        return {}
    trend = np.polyval(np.polyfit(yrs, yld, 1), yrs)     # linear tech trend
    anom = (yld - trend) / np.where(trend == 0, np.nan, trend)
    return {int(y): float(a) for y, a in zip(yrs, anom) if np.isfinite(a)}


def _pairs(session: Session, cfg: dict, belt: str):
    """(predicted_effect[], detrended_yield_anomaly[], years[]) for a belt, or None if ERA5 isn't on disk."""
    nc = f"data/era5_baseline/{belt}_1991_2024_monthly.nc"
    if not os.path.exists(nc):
        return None
    from ml.features.drought import compute_indices, load_monthly, seasonal_by_year
    by_year = {y["year"]: y for y in seasonal_by_year(compute_indices(load_monthly(nc), scale=3), cfg["months"])}
    obs = _detrended_yield_anomaly(session, cfg["commodity"], cfg["countries"])
    pred, yv, yrs = [], [], []
    for yr, h in by_year.items():
        if yr in obs and h.get(cfg["driver"]) is not None:
            pred.append(cfg["sign"] * float(h[cfg["driver"]]))
            yv.append(obs[yr]); yrs.append(yr)
    return pred, yv, yrs


def _make(belt: str, cfg: dict):
    def run(session: Session) -> ValidationResult:
        got = _pairs(session, cfg, belt)
        pred, yoy, yrs = got if got else ([], [], [])
        return ValidationResult(
            hazard_type=f"agri_{cfg['driver'].split('_')[0]}", kind="rank",
            predicted=pred, observed=yoy, labels=[str(y) for y in yrs],
            target_source=f"FAOSTAT observed yield · {cfg['commodity']} ({'/'.join(cfg['countries'])})",
            scope=belt, method="observational", data_vintage=f"{len(yrs)} paired years (ERA5 ∩ FAOSTAT)",
            notes=(f"growing-season {cfg['driver']} vs observed yield anomaly over ~{len(yrs)} years — "
                   f"{cfg['src']}; oriented so higher predicted effect ⇒ higher observed yield"),
        )
    return run


for _belt, _cfg in BELT_CONFIG.items():
    register(f"agri_yield_{_belt}")(_make(_belt, _cfg))

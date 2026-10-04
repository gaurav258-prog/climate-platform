"""The weather panel of a calibration recipe: {year: 0-100 driver score} and what was read (E162, E163).

One weather source — the global ERA5-Land weather build (services.calibration.crop_weather):
  box         a named region box (services.ingestion.regions), every 0.1° cell inside it, equal weights — the cells its
              regional file held (tests/integration/test_crop_area_weather holds the two to the same figures)
  crop_area   the crop's own growing area in the origin (crop map weights, the origin's season)
Soil water is the one exception: the global files hold no soil moisture, so a soil-water recipe reads its regional
soil-moisture file (ml.features.crop_panel), as before.
"""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache

from sqlalchemy.orm import Session

from ml.features.crop_panel import scores_for
from ml.features.drought import baseline_nc


@lru_cache(maxsize=256)
def _file_sha(path: str, mtime: float, size: int) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _describe(path: str) -> dict:
    if not os.path.exists(path):
        return {"file": os.path.basename(path), "present": False}
    st = os.stat(path)
    return {"file": os.path.basename(path), "sha": _file_sha(path, st.st_mtime, st.st_size)}


def scores(session: Session, sp: dict) -> tuple[dict[int, float], dict]:
    """({year: score}, inputs read) for a recipe; ({}, …) when its weather is not available."""
    if sp["weather_kind"] not in ("box", "crop_area"):
        raise ValueError(f"unknown weather kind '{sp['weather_kind']}'")
    if sp["driver"] == "soil_water":
        if sp["weather_kind"] != "box" or sp["season_prev_months"]:
            raise ValueError("a soil-water recipe reads a regional box file, its season within the calendar year")
        path = baseline_nc(sp["weather_key"], "soilmoisture")
        inputs = {"kind": "box", "key": sp["weather_key"], **_describe(path)}
        if not os.path.exists(path):
            return {}, inputs
        return scores_for(sp["weather_key"], "soil_water", list(sp["season_months"])), inputs
    from services.calibration import crop_area
    return crop_area.scores(session, sp)

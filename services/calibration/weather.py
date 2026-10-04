"""The weather panel of a calibration recipe: {year: 0-100 driver score} and what was read (E162).

  box         a named region box (services.ingestion.regions) read from its regional ERA5-Land file — exactly the
              builder the published fits used (ml.features.crop_panel), so a legacy recipe re-runs on the same panel
  crop_area   the crop's own growing area in the origin (services.calibration.crop_area — weights from the crop map,
              seasons from the crop calendar), read from the global ERA5-Land files
"""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache

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


def scores(sp: dict) -> tuple[dict[int, float], dict]:
    """({year: score}, inputs read) for a recipe; ({}, …) when its weather is not on disk."""
    months = list(sp["season_months"])
    if sp["weather_kind"] == "box":
        if sp["season_prev_months"]:
            raise ValueError("a box recipe reads its season within the calendar year (the legacy builder)")
        kind = "soilmoisture" if sp["driver"] == "soil_water" else "monthly"
        path = baseline_nc(sp["weather_key"], kind)
        inputs = {"kind": "box", "key": sp["weather_key"], **_describe(path)}
        if not os.path.exists(path):
            return {}, inputs
        return scores_for(sp["weather_key"], sp["driver"], months, sp["spei_scale"]), inputs
    if sp["weather_kind"] == "crop_area":
        from services.calibration import crop_area
        return crop_area.scores(sp)
    raise ValueError(f"unknown weather kind '{sp['weather_kind']}'")

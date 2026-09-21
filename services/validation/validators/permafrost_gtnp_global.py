"""Global permafrost validator — the thaw-exposure channel (ml/scoring/permafrost_point.py, Obu et al. 2019
Permafrost Probability Fraction raster) against GTN-P borehole ground temperature OUTSIDE the Europe-only sample
of services/validation/validators/permafrost_gtnp.py (239 sites, rho 0.82). Registers `permafrost_gtnp_global`.

PRE-REGISTERED DESIGN (written before any score was computed; no tuning after seeing results)
  Target — identical to permafrost_gtnp: MAGT at the depth closest to 10 m (>=300 daily readings, >=1 year,
    'suspicious value' rows dropped, plain mean; scripts/build_permafrost_boreholes.py::pick_depth), inverted to
    coldness (-MAGT). Same convention applied to the non-European export by
    scripts/build_permafrost_boreholes_global.py.
  Sites — the union of (a) data/permafrost_val/borehole_magt.csv (the earlier 239-site GTN-P export, of which 195
    are Russian) and (b) data/permafrost_val/borehole_magt_global.csv (US, Canada, China, Antarctica boreholes
    pulled from the public GTN-P API, CC BY 4.0). Sites in (a) are therefore NOT independent of permafrost_gtnp;
    the new independent evidence is the non-Russia/non-Alps regions, which the report should quote separately.
  Predicted — production permafrost score (canonical_scores when present, else score_permafrost_point on demand).
    Sites off the Obu domain (NH >=25N, so every Southern Hemisphere/Antarctic site) or on nodata pixels are
    DROPPED and COUNTED per region, never filled.
  Strata (macro_region, fixed rule on country/coordinates, decided before scoring):
    Southern Hemisphere (lat < 0)                         -> 'Antarctica/Southern Hemisphere'
    country RU                                            -> 'Russia/Siberia'
    lon in [-180, -50), lat >= 25                         -> 'North America'
    lon >= 60 (non-RU)                                    -> 'Central Asia/Tibetan Plateau'
    otherwise (lon in [-50, 60), incl. Alps, Iceland, Svalbard, Greenland) -> 'Europe/Arctic Atlantic'
  Metric — Spearman rank (kind 'rank'), pooled and per stratum through the platform gates
    (core/validation_gates.py + ml/validation/regional.py) unchanged. hazard_type 'permafrost_thaw',
    scope 'global_boreholes', method out_of_sample. No tier/claim is changed by this module.
Caveats as in permafrost_gtnp (plain-mean MAGT, some shallow instruments; sample skews to instrumented sites).
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

import h3
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register
from services.validation.validators.permafrost_gtnp import MAGT_CSV, _coldness, _standing_scores

GLOBAL_CSV = Path("data/permafrost_val/borehole_magt_global.csv")
TARGET = "GTN-P borehole MAGT at ~10 m depth, global boreholes incl. N. America, Asia, Antarctica (data.gtn-p.org, CC BY 4.0)"
SOURCE_URL = "https://data.gtn-p.org/"


def macro_region(lat: float, lon: float, country: Optional[str]) -> str:
    if lat < 0:
        return "Antarctica/Southern Hemisphere"
    if (country or "") == "RU":
        return "Russia/Siberia"
    if lon < -50 and lat >= 25:
        return "North America"
    if lon >= 60:
        return "Central Asia/Tibetan Plateau"
    return "Europe/Arctic Atlantic"


def load_all(paths=(MAGT_CSV, GLOBAL_CSV)) -> list[dict]:
    rows, seen = [], set()
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        with p.open() as f:
            for r in csv.DictReader(f):
                bid = int(r["borehole_id"])
                if bid in seen:
                    continue
                seen.add(bid)
                lat, lon = float(r["lat"]), float(r["lon"])
                rows.append({"borehole_id": bid, "lat": lat, "lon": lon, "country": r.get("country") or "",
                             "depth_m": float(r["depth_m"]), "magt_c": float(r["magt_c"]),
                             "region": macro_region(lat, lon, r.get("country")),
                             "h3_cell": h3.latlng_to_cell(lat, lon, 8)})
    return rows


def _run(session: Session) -> ValidationResult:
    boreholes = load_all()
    if not boreholes:
        return ValidationResult(hazard_type="permafrost_thaw", kind="rank", predicted=[], observed=[], labels=[],
                                target_source=TARGET, scope="global_boreholes", method="out_of_sample",
                                notes="borehole MAGT files absent — run scripts/build_permafrost_boreholes[_global]")
    from ml.scoring.permafrost_point import score_permafrost_point

    have = _standing_scores(session, [b["h3_cell"] for b in boreholes])
    dropped: dict[str, int] = {}
    for b in boreholes:
        if b["h3_cell"] in have:
            continue
        if b["lat"] < 25:
            continue  # off the Obu NH>=25N domain — dropped below and counted
        r = score_permafrost_point(b["lat"], b["lon"])
        if r.get("status") != "insufficient_data" and r.get("risk_score") is not None:
            have[b["h3_cell"]] = float(r["risk_score"])
    pred, obs, labels, strata = [], [], [], []
    for b in boreholes:
        if b["h3_cell"] not in have or b["lat"] < 25:
            dropped[b["region"]] = dropped.get(b["region"], 0) + 1
            continue
        pred.append(have[b["h3_cell"]]); obs.append(_coldness(b["magt_c"]))
        labels.append(f"gtnp_{b['borehole_id']}_{b['country']}"); strata.append(b["region"])
    return ValidationResult(
        hazard_type="permafrost_thaw", kind="rank", predicted=pred, observed=obs, labels=labels, strata=strata,
        target_source=TARGET, scope="global_boreholes", method="out_of_sample",
        data_vintage="GTN-P daily ground temp, per-site (varies)",
        notes=(f"{len(pred)} of {len(boreholes)} GTN-P boreholes scored vs coldness (-MAGT) at ~10 m ({SOURCE_URL}); "
               f"dropped off-domain/nodata (never filled) by region: {dropped or 'none'}. Overlaps the earlier "
               f"239-site Europe/Russia sample; strata by fixed macro_region rule (see module docstring)."),
        extra={"dropped_by_region": dropped},
    )


register("permafrost_gtnp_global")(_run)

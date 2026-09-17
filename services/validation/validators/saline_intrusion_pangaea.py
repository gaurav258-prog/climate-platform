"""Saline-intrusion validator — the low-elevation-coastal-zone (LECZ) susceptibility proxy
(ml/scoring/saline_intrusion_point.py: `saline_susceptibility(elevation_m, dist_km)`) against OBSERVED
coastal groundwater electrical conductivity (EC).

Why this is the honest target: the proxy is explicitly disclosed as a screening indicator — "low AND close
to the coast" — not a hydrogeological aquifer-salinity model. It has never seen a groundwater-chemistry
observation. Thorslund & van Vliet (2020, PANGAEA DOI 10.1594/PANGAEA.913939) is a genuinely independent,
directly-measured salinity record: 208,550 groundwater monitoring stations worldwide, EC in µS/cm, compiled
1980-2019 from national/regional agencies (USGS, AU GwEX, TWDB, WQP, …), with a pre-computed `Coastal_location`
flag (< 10 km from the Natural Earth coastline) and per-station sample statistics. We use the SUMMARY file
(one row per station), not the 16M-row raw database.

Design (kind 'rank' — a continuous observed quantity, not an occurrence/count):
  candidate set     Groundwaters_summary.csv rows with Coastal_location == 'Yes'
  reliability floor  n (sample count per station) >= MIN_STATION_SAMPLES, so a station's EC statistic isn't a
                     single noisy grab sample
  observed          median EC (µS/cm) per station — chosen over mean (more outlier-robust for a skewed
                     hydrochemical variable) and over TDS/EC_conv (only ~69 of the ~25k coastal stations carry
                     TDS/EC_conv; median EC is populated for effectively all of them)
  predicted         100 * saline_susceptibility(elevation_m, dist_km) — the proxy's own two inputs, computed
                     directly at 'baseline'/'current' (no SLR amplification, matching what
                     score_saline_intrusion_point returns for baseline/current — see its docstring)
  elevation         Copernicus GLO-90 DEM via the Open-Meteo elevation API (no key), BATCHED up to 100 points
                     per request — the same public endpoint _ensure_coastal_exposure calls one point at a time,
                     but its batch mode lets thousands of stations be scored in dozens of requests instead of
                     thousands, with courtesy pacing between requests (see avalanche_slf.py for the on-demand-
                     DEM pacing pattern this follows)
  dist_to_coast_km  true great-circle distance to the nearest Natural Earth 10m coastline point (shapely,
                     locally cached geojson — no rate limit), exactly the geometry _ensure_coastal_exposure uses
  not_applicable    stations whose DEM-measured distance exceeds COAST_KM (25 km) are dropped (counted) — the
                     proxy declares itself out of scope there, same as the point scorer's own 'not_applicable'

This intentionally bypasses the DB-caching wrapper (_ensure_coastal_exposure / score_saline_intrusion_point):
with ~5,000 candidate stations, one DB-cached call each would mean ~5,000 individual Open-Meteo requests;
batching is the same physical computation without the waste. Needs data/salinity_val/Groundwaters_summary.csv;
absent -> INSUFFICIENT.
"""
from __future__ import annotations

import time
from pathlib import Path

import h3
from sqlalchemy.orm import Session

from ml.scoring.coastal_flood_point import _coastline
from ml.scoring.saline_intrusion_point import saline_susceptibility
from ml.scoring.sea_level import COAST_KM
from services.validation.engine import ValidationResult, register

SUMMARY_CSV = Path("data/salinity_val/Groundwaters_summary.csv")
TARGET = "Observed coastal groundwater electrical conductivity (median EC, µS/cm), Thorslund & van Vliet (2020)"
SOURCE_DOI = "10.1594/PANGAEA.913939"
MIN_STATION_SAMPLES = 3         # a station's EC statistic must rest on >=3 measurements, not one grab sample
ELEV_BATCH = 100                # Open-Meteo elevation API: 100 points/request is the largest batch that doesn't 400
_PAUSE_S = 0.25                 # courtesy pacing between batched Open-Meteo requests
_TIMEOUT_S = 20


# ── loading + filtering (pure, unit-testable) ───────────────────────────────────────────────────
def load_candidates(csv_path: Path = SUMMARY_CSV, min_n: int = MIN_STATION_SAMPLES) -> list[dict]:
    """Coastal groundwater stations with a usable median EC and >=min_n underlying samples."""
    import pandas as pd
    df = pd.read_csv(csv_path, low_memory=False)
    df = df[(df["Coastal_location"] == "Yes") & df["median"].notna() & (df["n"] >= min_n)]
    out = []
    for r in df.itertuples(index=False):
        lat, lon = float(r.Lat), float(r.Lon)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        out.append({"station_id": r.Station_ID, "lat": lat, "lon": lon, "ec_median": float(r.median),
                    "n": int(r.n), "country": r.Country})
    return out


def _dist_to_coast_km(lat: float, lon: float) -> float:
    from shapely.geometry import Point
    from shapely.ops import nearest_points
    near = nearest_points(_coastline(), Point(lon, lat))[0]
    return float(h3.great_circle_distance((lat, lon), (near.y, near.x), unit="km"))


def add_coast_distance(stations: list[dict]) -> list[dict]:
    """Attach dist_to_coast_km to every station (local shapely lookup, no rate limit)."""
    for st in stations:
        st["dist_to_coast_km"] = _dist_to_coast_km(st["lat"], st["lon"])
    return stations


def fetch_elevations(stations: list[dict], batch: int = ELEV_BATCH, pause_s: float = _PAUSE_S,
                     max_retries: int = 4, backoff_s: float = 8.0) -> dict[str, float]:
    """Elevation per station_id from the Open-Meteo GLO-90 DEM, batched. On a 429 (the public endpoint's
    per-minute limit), backs off and retries the same batch rather than silently dropping it. Missing/failed
    points after retries are absent, never fabricated."""
    import json
    import urllib.error
    import urllib.request

    elev: dict[str, float] = {}
    for i in range(0, len(stations), batch):
        chunk = stations[i:i + batch]
        lats = ",".join(f"{s['lat']:.5f}" for s in chunk)
        lons = ",".join(f"{s['lon']:.5f}" for s in chunk)
        url = f"https://api.open-meteo.com/v1/elevation?latitude={lats}&longitude={lons}"
        vals: list = []
        for attempt in range(max_retries + 1):
            try:
                with urllib.request.urlopen(url, timeout=_TIMEOUT_S) as r:
                    vals = json.load(r).get("elevation") or []
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < max_retries:
                    time.sleep(backoff_s * (attempt + 1))
                    continue
                vals = []
                break
            except Exception:
                vals = []
                break
        for s, v in zip(chunk, vals):
            if v is not None:
                elev[s["station_id"]] = float(v)
        time.sleep(pause_s)
    return elev


# ── run ──────────────────────────────────────────────────────────────────────────────────────────
def _run(session: Session) -> ValidationResult:
    if not SUMMARY_CSV.exists():
        return ValidationResult(hazard_type="saline_intrusion", kind="rank", predicted=[], observed=[], labels=[],
                                target_source=TARGET, scope="global", method="out_of_sample",
                                notes=f"target file {SUMMARY_CSV} not present")
    stations = load_candidates()
    add_coast_distance(stations)

    n_not_applicable = sum(1 for s in stations if s["dist_to_coast_km"] > COAST_KM)
    scoreable = [s for s in stations if s["dist_to_coast_km"] <= COAST_KM]

    elev = fetch_elevations(scoreable)
    n_no_elev = len(scoreable) - len(elev)

    pred, obs, labels = [], [], []
    for s in scoreable:
        e = elev.get(s["station_id"])
        if e is None:
            continue
        pred.append(100.0 * saline_susceptibility(e, s["dist_to_coast_km"]))
        obs.append(s["ec_median"])
        labels.append(s["station_id"])

    return ValidationResult(
        hazard_type="saline_intrusion", kind="rank", predicted=pred, observed=obs, labels=labels,
        target_source=f"Thorslund & van Vliet (2020) observed coastal groundwater EC, PANGAEA {SOURCE_DOI}",
        scope="global (coastal groundwater stations)",
        method="out_of_sample",
        data_vintage="Thorslund & van Vliet 2020, PANGAEA (samples 1980-2019)",   # <=60 chars
        notes=(f"candidates = Groundwaters_summary.csv rows with Coastal_location=Yes and n>={MIN_STATION_SAMPLES} "
               f"samples ({len(stations)} of 25,226 coastal-tagged stations); dist_to_coast recomputed locally "
               f"(shapely vs Natural Earth 10m coastline, matching _ensure_coastal_exposure's own geometry) rather "
               f"than trusting the dataset's own <10km flag; {n_not_applicable} stations fell beyond COAST_KM="
               f"{COAST_KM:.0f} km on that geometry and were dropped as not_applicable (same boundary the point "
               f"scorer itself uses); elevation via batched Open-Meteo GLO-90 DEM calls ({ELEV_BATCH}/request, "
               f"{_PAUSE_S}s courtesy pacing), {n_no_elev} stations returned no elevation and were dropped. "
               f"Predicted = 100 * saline_susceptibility(elevation, dist_to_coast) — the proxy's own two inputs, "
               f"no SLR amplification (baseline/current). Observed = station median EC (µS/cm), the sample "
               f"statistic most completely populated across coastal stations (converted EC / TDS cover <0.3% of "
               f"them). Caveat: EC/salinity is driven by aquifer geology, pumping/abstraction and proximity to a "
               f"specific river mouth or saltwater source — factors this proxy's two inputs (elevation, coastal "
               f"distance) do not encode at all; a weak result here would say as much about those omitted "
               f"drivers as about the proxy."),
    )


register("saline_intrusion_pangaea")(_run)

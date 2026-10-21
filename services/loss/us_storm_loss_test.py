"""The US storm loss test — data/reference/loss_protocol.json 'us_storm_loss_test' (registered 2026-10-21, ce7b572; stated
before any of it was built or run).

Do the tropical-cyclone wind losses the platform models for US forecast office areas rank like the wind damage those
areas reported (NOAA Storm Events)? One NWS forecast office area (its zones in the Atlantic and Gulf coast states) is one
sample — the unit amended before any result (amended_before_run): 39% of the damage sits in zone codes NWS has since
split or renamed, while every record names its office.

  records(types)    NOAA damage records of the given event types, 1996–2025, by forecast office, with what was set aside
  observed()        per office area: wind damage in 2024 dollars (CPI-U yearly averages) ÷ 30 years ÷ its LitPop assets,
                    and the same with storm surge added (shown for information only)
  winds(cells)      the storm_v4_wind layer's wind at its eight return periods at each LitPop cell (one pass, saved)
  modelled(curve)   per office area: the asset-weighted mean over its cells of the curve's expected annual damage ratio, the
                    wind read as 1-minute wind by the layer's registered divisor (÷ 0.88)
  run(session)      both US curves under the registered rule; each result recorded in the ledger and on the curve

The pass over the cells runs offline (scripts/run_us_storm_loss_test.py), never on the API thread.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np

from services.loss import curves, engine, registry

log = logging.getLogger(__name__)

KEY = "us_storm_loss_test"
LAYER = "storm_v4_wind"
FAMILIES = ("eberenz_2021_rmsf", "eberenz_2021_tdr")
ROOT = registry.ROOT
NOAA = ROOT / "data" / "loss_val" / "noaa_storm_events"
ZONES = ROOT / "data" / "windstorm_val" / "nws_zones.zip"
LITPOP = ROOT / "data" / "datasets" / "litpop_usa" / "LitPop_150arcsec_USA.hdf5"
CPI = ROOT / "data" / "datasets" / "bls_cpi_u"
STATE_CODES = ROOT / "data" / "reference" / "regions" / "us_census_county2020.txt"
OUT = ROOT / "data" / "loss_val" / "us_storm_loss_test"
# The registered selection (loss_protocol.json 'us_storm_loss_test'), held here as values; tests/unit/
# test_us_storm_loss_test.py checks the registered text still states each one.
STATES = ("AL", "CT", "DE", "FL", "GA", "LA", "ME", "MD", "MA", "MS", "NH", "NJ", "NY", "NC", "PA", "RI", "SC", "TX", "VA")
YEARS = (1996, 2025)
BASE_YEAR = 2024
WIND = ("Hurricane (Typhoon)", "Hurricane", "Tropical Storm")
SURGE = ("Storm Surge/Tide",)
UNPLACED_MAX = 0.01   # E306: the run refuses when more of the damage than this cannot be placed (a safety check, not the rule)
_MONEY = re.compile(r"^(\d+(?:\.\d*)?|\.\d+)([KMB]?)$")     # NOAA writes '25.00K', '1.5M', '0' and '.5M' (E305)
_SCALE = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9}


def protocol() -> dict:
    return json.loads((registry.REF / "loss_protocol.json").read_text(encoding="utf-8"))[KEY]


def money(v) -> Optional[float]:
    """NOAA's DAMAGE_PROPERTY in dollars ('25.00K' → 25,000); 0 for blank; None when it is not written as NOAA states."""
    if v is None or (isinstance(v, float) and v != v) or str(v).strip() == "":
        return 0.0
    m = _MONEY.match(str(v).strip().upper())
    return float(m.group(1)) * _SCALE[m.group(2)] if m else None


def cpi_yearly() -> dict[int, float]:
    """CPI-U yearly averages: the mean of a year's twelve monthly indexes, for years that have all twelve."""
    months: dict[int, dict[str, float]] = {}
    for f in sorted(CPI.glob("CUUR0000SA0_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"{f.name}: {d.get('status')}")
        for x in d["Results"]["series"][0]["data"]:
            if re.fullmatch(r"M(0[1-9]|1[0-2])", x["period"]) and re.fullmatch(r"\d+(\.\d+)?", x["value"]):
                months.setdefault(int(x["year"]), {})[x["period"]] = float(x["value"])
    return {y: sum(m.values()) / 12 for y, m in months.items() if len(m) == 12}


def _state_codes() -> dict[int, str]:
    rows = STATE_CODES.read_text(encoding="utf-8").splitlines()[1:]
    return {int(r.split("|")[1]): r.split("|")[0] for r in rows if r.count("|") >= 2}


def records(types: tuple[str, ...]):
    """(office, year, nominal dollars) for every record of these types in the listed states, 1996–2025, by zone or by
    county; and what was set aside: records whose damage is not written as NOAA states it."""
    import pandas as pd
    codes = _state_codes()
    keep, aside = [], {"damage_unreadable": 0}
    for y in range(YEARS[0], YEARS[1] + 1):
        f = sorted(NOAA.glob(f"StormEvents_details-ftp_v1.0_d{y}_c*.csv.gz"))
        if len(f) != 1:
            raise RuntimeError(f"NOAA {y}: expected one details file, found {len(f)}")
        d = pd.read_csv(f[0], usecols=["YEAR", "EVENT_TYPE", "STATE_FIPS", "WFO", "DAMAGE_PROPERTY"], low_memory=False)
        d = d[d["EVENT_TYPE"].isin(types)].copy()
        d["state"] = d["STATE_FIPS"].map(codes)
        d = d[d["state"].isin(STATES)]
        d["dollars"] = d["DAMAGE_PROPERTY"].map(money)
        aside["damage_unreadable"] += int(d["dollars"].isna().sum())
        d = d[d["dollars"].notna()]
        keep.append(d[["WFO", "YEAR", "dollars"]].rename(columns={"WFO": "office", "YEAR": "year"}))
    return pd.concat(keep, ignore_index=True), aside


def zones():
    """The listed states' forecast zones as of 18 March 2025, one outline per zone (parts merged), with the office (CWA)
    each belongs to, in WGS84."""
    import geopandas as gpd
    g = gpd.read_file(f"zip://{ZONES}")
    g = g[g["STATE"].isin(STATES)].dissolve(by="STATE_ZONE", aggfunc={"CWA": "first"}).reset_index()
    return g[["STATE_ZONE", "CWA", "geometry"]].rename(columns={"STATE_ZONE": "zone", "CWA": "office"}).to_crs("EPSG:4326")


def cells(z):
    """LitPop cells with an asset value, placed in the zone (of `z`) holding their centre: zone, office, value, lat,
    lon."""
    import geopandas as gpd

    from services.geo import raster_sampler
    if not LITPOP.exists():
        raise RuntimeError(f"{LITPOP} is not held")
    a = raster_sampler.read(f'HDF5:"{LITPOP}"://exposures/block0_values')   # columns value, latitude, longitude
    if a is None:
        raise RuntimeError("the LitPop grid could not be read")
    a = a[a[:, 0] > 0]
    pts = gpd.GeoDataFrame({"value": a[:, 0], "lat": a[:, 1], "lon": a[:, 2]},
                           geometry=gpd.points_from_xy(a[:, 2], a[:, 1]), crs="EPSG:4326")
    j = gpd.sjoin(pts, z, predicate="within", how="inner")
    if j.index.duplicated().any():
        raise RuntimeError("a cell falls in two zones")
    return j[["zone", "office", "value", "lat", "lon"]].reset_index(drop=True)


def observed(c, outlines: set[str], wind=None, surge=None) -> tuple[dict, dict]:
    """({office: {assets, rate, rate_with_surge, records}}, selection counts) for the office areas with assets;
    `outlines` are the offices the 2025 outlines name, against which a record's office is checked."""
    cpi = cpi_yearly()
    if BASE_YEAR not in cpi:
        raise RuntimeError(f"no CPI-U yearly average for {BASE_YEAR}")
    (w, aside_w), (s, aside_s) = (wind or records(WIND)), (surge or records(SURGE))
    assets = c.groupby("office")["value"].sum()
    out = {z: {"assets": float(v), "rate": 0.0, "rate_with_surge": 0.0, "records": 0} for z, v in assets.items() if v > 0}
    years = YEARS[1] - YEARS[0] + 1
    for df, keys in ((w, ("rate", "rate_with_surge")), (s, ("rate_with_surge",))):
        priced = df[df["dollars"] > 0]
        missing = sorted(set(priced["year"]) - set(cpi))
        if missing:
            raise RuntimeError(f"damage recorded in {missing}, which have no twelve CPI-U indexes")
        for r in priced.itertuples():
            if r.office in out:
                v = r.dollars * cpi[BASE_YEAR] / cpi[r.year] / years / out[r.office]["assets"]
                for k in keys:
                    out[r.office][k] += v
                if keys[0] == "rate":
                    out[r.office]["records"] += 1
    off = w[(w["dollars"] > 0) & ~w["office"].isin(outlines)]
    real = off["dollars"] * cpi[BASE_YEAR] / off["year"].map(cpi)
    allw = w[w["dollars"] > 0]
    total = float((allw["dollars"] * cpi[BASE_YEAR] / allw["year"].map(cpi)).sum())
    if total and real.sum() > UNPLACED_MAX * total:      # E306: never a test on damage the unit cannot hold
        raise RuntimeError(f"{real.sum() / total:.1%} of the wind damage names an office the outlines do not hold")
    return out, {"office_areas_in_scope": len(out), "wind_records": int(len(w)), "surge_records": int(len(s)),
                 "wind_set_aside": {**aside_w, "office_not_in_2025_outlines": sorted(set(off["office"])),
                                    "their_damage_2024_usd": round(float(real.sum()))},
                 "surge_set_aside": aside_s, "cpi_base_year": BASE_YEAR}


def _rows(points: list[tuple[float, float]]) -> list[list[float]]:
    from services.loss import storm_events
    out = []
    for la, lo in points:
        r = storm_events.rows(float(la), float(lo))
        out.append([x["value"] for x in sorted(r, key=lambda x: x["rp_years"])] if r else [])
    return out


def winds(c, path: Path = OUT, workers: int = 4) -> np.ndarray:
    """The layer's wind (m/s, 10-minute, as stored) at each cell and return period — made once and saved; reused while
    the layer version, the grid file and the cells are unchanged."""
    from concurrent.futures import ProcessPoolExecutor
    stamp = {"layer": LAYER, "version": registry.layer(LAYER)["version"], "litpop": LITPOP.name, "cells": int(len(c)),
             "first": [float(c["lat"].iloc[0]), float(c["lon"].iloc[0])], "rps": registry.layer(LAYER)["return_periods"]}
    f = path / "winds.npz"
    if f.exists():
        held = np.load(f, allow_pickle=False)
        if json.loads(str(held["stamp"])) == stamp:
            return held["winds"]
    pts = list(zip(c["lat"].tolist(), c["lon"].tolist()))
    chunks = [pts[i:i + 2000] for i in range(0, len(pts), 2000)]
    got: list[list[float]] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, part in enumerate(ex.map(_rows, chunks)):
            got.extend(part)
            log.info("us storm loss test: winds %d of %d chunks", i + 1, len(chunks))
    if any(len(g) != len(stamp["rps"]) for g in got):
        raise RuntimeError("the storm layer gave no wind at some cells (the event set is not built?)")
    arr = np.asarray(got, dtype="float64")
    path.mkdir(parents=True, exist_ok=True)
    np.savez(f, winds=arr, stamp=json.dumps(stamp))
    return arr


def modelled(c, w: np.ndarray, curve: dict) -> dict[str, float]:
    """Per office area: the asset-weighted mean of the cells' expected annual damage ratio."""
    per = registry.divisor(LAYER, curves.families()[curve["key"].split(":")[0]]["metric"])
    if per is None:
        raise RuntimeError(f"{curve['key']}: the storm layer has no registered reading in the curve's metric")
    rps = registry.layer(LAYER)["return_periods"]
    ratio = np.vectorize(lambda x: curves.ratio(curve["points"], float(x)))(w / per)
    ead = np.array([engine.eal(dict(zip(rps, row))) for row in ratio])
    v = c["value"].to_numpy()
    cat = c["office"].astype("category")
    num = np.bincount(cat.cat.codes, weights=v * ead)
    den = np.bincount(cat.cat.codes, weights=v)
    names = cat.cat.categories
    return {z: float(n / d) for z, n, d in zip(names, num, den) if d > 0}


def run(session, *, actor: str = KEY, path: Path = OUT, workers: int = 4) -> dict:
    """The registered test, both US curves; the two results built first, then recorded together (ledger, one
    transaction) and on each curve; the per-office-area rows saved beside the cached winds for the drill-down."""
    from core.validation_gates import MIN_N_REGION_CLAIM, RANK_GATE_SPEARMAN
    from ml.validation.metrics import spearman
    from services.loss import published_test
    from services.loss.europe_loss_test import _pct_rank
    from services.validation.engine import ValidationResult, record_result
    proto = protocol()
    fams = curves.families()
    tested = [next(c for f in FAMILIES for c in fams[f]["curves"] if c["key"] == k) for k in proto["curves"]]
    z = zones()
    c = cells(z)
    obs, selection = observed(c, set(z["office"]))
    w = winds(c, path, workers)
    built = []
    for cv in tested:
        mod = modelled(c, w, cv)
        rows = [{"office": k, "observed_rate": o["rate"], "rate_with_surge": o["rate_with_surge"], "records": o["records"],
                 "assets_usd": round(o["assets"]), "modelled": mod[k]} for k, o in sorted(obs.items()) if k in mod]
        pred, ob = np.array([r["modelled"] for r in rows]), np.array([r["observed_rate"] for r in rows])
        rho = spearman(pred, ob)
        rho_surge = spearman(pred, np.array([r["rate_with_surge"] for r in rows]))
        ok = rho is not None and len(rows) >= MIN_N_REGION_CLAIM and rho >= RANK_GATE_SPEARMAN
        built.append((cv, rows, rho, rho_surge, ok, ValidationResult(
            hazard_type="cyclone_loss", kind="rank", method="out_of_sample", scope=f"us/{cv['key']}",
            predicted=_pct_rank(list(pred)), observed=list(ob),
            target_source="NOAA Storm Events wind damage 1996–2025 per NWS office area, 2024 dollars ÷ LitPop assets",
            data_vintage="NOAA 1996–2025; LitPop 150as v3; STORM v4",
            labels=[r["office"] for r in rows],
            notes=("Pre-registered (loss_protocol.json us_storm_loss_test). Predicted = the curve's expected annual damage "
                   "ratio of each office area's LitPop assets on the STORM wind maps (÷ 0.88), passed as its percentile "
                   f"rank (ρ unchanged; the bands read quartiles). Pass needs ρ ≥ 0.35 with at least {MIN_N_REGION_CLAIM} areas; "
                   "the wind-and-surge ρ is shown for information only."),
            extra={"protocol": KEY, "curve": cv["key"], "min_regions": MIN_N_REGION_CLAIM,
                   "spearman_with_surge_information": rho_surge})))
    ledger = [record_result(session, b[-1], actor=actor, persist_samples=True, commit=False) for b in built]
    session.commit()                # the two results are in the ledger together, or neither is
    out = {}
    for (cv, rows, rho, rho_surge, ok, _res), led in zip(built, ledger):
        result = {"protocol": KEY, "registered": proto["registered"], "run": date.today().isoformat(),
                  "countries": ["US"], "office_areas_tested": len(rows), "spearman": rho,
                  "spearman_with_surge_information": rho_surge,
                  "band_mean_observed": led["metrics"].get("band_mean_observed"),
                  "monotonic": led["metrics"].get("monotonic"), "gate": led["gate"], "min_regions": MIN_N_REGION_CLAIM,
                  "ledger_run": led["run_id"], **selection, "passed": bool(led["passed_gate"] and ok)}
        published_test.record(cv["key"].split(":")[0], cv["key"], result)
        out[cv["key"]] = {**result, "rows": rows}
    path.mkdir(parents=True, exist_ok=True)
    (path / f"result_{date.today().isoformat()}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out

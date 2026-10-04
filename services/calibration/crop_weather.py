"""Monthly weather over a calibration's area, from the global ERA5-Land files (E163) — one weather source for every
recipe.

A target is either a crop's own growing area in an origin ('crop:<commodity>:<origin>', weighted by harvested area —
services.calibration.crop_area_weights) or a named region box ('box:<region>', every 0.1° cell inside its inclusive
bounds, equal weights — the cells a regional ERA5-Land file of that box holds). For every cell: the 6-month water balance
(P − PET) standardised against its own 1991–2020 normal per calendar month (SPEI-6, as ml.features.drought), and the
temperature anomaly against its 1991–2020 monthly normal; a target's monthly figure is the weighted mean over its cells
(cells with no value that month leave both the sum and the weights). A build reads every landed year of the global files
band by band (keeping only the cells it needs), and is recorded with what it read; recipes read the latest build holding
their target.
"""
from __future__ import annotations

import json
import warnings
from datetime import date

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.calibration import crop_area_weights as W

SCALE = 6
BASELINE = (1991, 2020)
BAND_ROWS = 181                 # half a file chunk (361 rows): each chunk is decompressed twice, never more


def crop_target(commodity: str, origin: str) -> str:
    return f"crop:{commodity}:{origin}"


def box_target(region: str) -> str:
    return f"box:{region}"


def box_cells(region: str) -> np.ndarray:
    """The flat ERA5-Land indices inside a region box (bounds included) — the cells a CDS request of its area holds."""
    from services.ingestion.regions import REGIONS
    r = REGIONS[region]
    rows = np.arange(int(round((90 - r.max_lat) * 10)), int(round((90 - r.min_lat) * 10)) + 1)
    cols = np.mod(np.arange(int(round(r.min_lon * 10)), int(round(r.max_lon * 10)) + 1), W.ERA5_NX)
    return (rows[:, None] * W.ERA5_NX + cols[None, :]).ravel().astype(np.int64)


def _files():
    from scripts.fetch_era5_land_global import _files as landed
    held = sorted(landed().items(), key=lambda kv: kv[1].start)
    years = [y for _p, r in held for y in r]
    if not years or years[0] > BASELINE[0] or years != list(range(years[0], years[-1] + 1)):
        raise RuntimeError("the global ERA5-Land files must run without a gap from 1991 — scripts/fetch_era5_land_global")
    if years[-1] < BASELINE[1]:
        raise RuntimeError(f"the global ERA5-Land files end in {years[-1]} — the 1991–2020 normal needs 2020")
    return held


def _read_cells(files, r0: int, r1: int, rr: np.ndarray, cc: np.ndarray) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """({var: (months, cells)}, the months' first days) for the cells (rows rr + r0, columns cc) of ERA5 rows r0..r1-1,
    every landed file in order — each file's band read once, only the cells kept."""
    import netCDF4
    parts = {v: [] for v in ("tp", "pev", "t2m")}
    times = []
    for path, _years in files:
        with netCDF4.Dataset(path) as ds:
            tname = "valid_time" if "valid_time" in ds.variables else "time"
            tv = ds.variables[tname]
            times.append(netCDF4.num2date(tv[:], tv.units, only_use_cftime_datetimes=False,
                                          only_use_python_datetimes=True))
            for v in parts:
                band = np.ma.filled(ds.variables[v][:, r0:r1, :].astype(np.float32), np.nan)
                parts[v].append(band[:, rr, cc])
    months = np.array([np.datetime64(f"{t.year:04d}-{t.month:02d}") for ts in times for t in ts])
    return {v: np.concatenate(p, axis=0).astype(np.float64) for v, p in parts.items()}, months


def standardize(x: np.ndarray, months_of_year: np.ndarray, years: np.ndarray, scale: int) -> np.ndarray:
    """z of the `scale`-month rolling sum against the per-calendar-month 1991–2020 normal (population sd), (t, cells) —
    ml.features.drought._standardize on arrays."""
    acc = np.full_like(x, np.nan)
    for i in range(scale - 1, x.shape[0]):
        acc[i] = x[i - scale + 1:i + 1].sum(axis=0)              # NaN anywhere in the window → NaN (min_periods=scale)
    z = np.full_like(acc, np.nan)
    base = (years >= BASELINE[0]) & (years <= BASELINE[1])
    for m in range(1, 13):
        sel = months_of_year == m
        b = acc[sel & base]
        with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)         # a sea cell has no value in any month
            mean, sd = np.nanmean(b, axis=0), np.nanstd(b, axis=0)
            z[sel] = (acc[sel] - mean) / np.where(sd > 0, sd, np.nan)
    return z


def anomaly(x: np.ndarray, months_of_year: np.ndarray, years: np.ndarray) -> np.ndarray:
    out = np.full_like(x, np.nan)
    base = (years >= BASELINE[0]) & (years <= BASELINE[1])
    for m in range(1, 13):
        sel = months_of_year == m
        with np.errstate(invalid="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            out[sel] = x[sel] - np.nanmean(x[sel & base], axis=0)
    return out


def targets(commodities: list[str], boxes: list[str]) -> list[tuple[str, np.ndarray, np.ndarray]]:
    out = []
    for c in commodities:
        for origin, (idx, w) in W.weights(c).items():
            out.append((crop_target(c, origin), idx.astype(np.int64), w.astype(np.float64)))
    for b in boxes:
        idx = box_cells(b)
        out.append((box_target(b), idx, np.ones(len(idx))))
    return out


def build(session: Session, commodities: list[str], boxes: list[str]) -> str:
    """Compute and record a build for the targets. Returns the build id. Not committed here."""
    files = _files()
    tg = targets(commodities, boxes)
    num: dict = {}
    den: dict = {}
    months = years = moy = None
    for r0 in range(0, W.ERA5_NY, BAND_ROWS):
        r1 = min(r0 + BAND_ROWS, W.ERA5_NY)
        lo, hi = r0 * W.ERA5_NX, r1 * W.ERA5_NX
        in_band = [(k, i[(i >= lo) & (i < hi)], w[(i >= lo) & (i < hi)]) for k, i, w in tg]
        in_band = [t for t in in_band if len(t[1])]
        if not in_band:
            continue
        cells = np.unique(np.concatenate([i for _k, i, _w in in_band]))
        rr, cc = (cells - lo) // W.ERA5_NX, (cells - lo) % W.ERA5_NX
        band, band_months = _read_cells(files, r0, r1, rr, cc)
        if months is None:
            months = band_months
            years = months.astype("datetime64[Y]").astype(int) + 1970
            moy = months.astype(int) % 12 + 1
            num = {k: np.zeros((2, len(months))) for k, _i, _w in tg}
            den = {k: np.zeros((2, len(months))) for k, _i, _w in tg}
        D = band["tp"] * 1000.0 - np.where(band["pev"] < 0, band["pev"], 0.0) * -1000.0
        fields = (standardize(D, moy, years, SCALE), anomaly(band["t2m"] - 273.15, moy, years))
        del band, D
        for k, i, w in in_band:
            p = np.searchsorted(cells, i)
            for j, f in enumerate(fields):
                v = f[:, p]
                ok = np.isfinite(v)
                num[k][j] += np.where(ok, v, 0.0) @ w
                den[k][j] += ok @ w
    if months is None:
        raise RuntimeError("no target has a cell on the grid")
    inputs = {"era5_files": [{"file": p.name, "years": [r.start, r.stop - 1]} for p, r in files],
              "weights": {c: W.fingerprint(c) for c in commodities}, "boxes": boxes, "scale": SCALE,
              "baseline": list(BASELINE)}
    build_id = session.execute(text("""
        INSERT INTO crop_weather_builds (inputs, first_month, last_month) VALUES (CAST(:i AS jsonb), :f, :l)
        RETURNING build_id::text"""), {"i": json.dumps(inputs), "f": months[0].astype(date), "l": months[-1].astype(date)}).scalar()
    rows, wrows = [], []
    for k, i, w in tg:
        with np.errstate(invalid="ignore", divide="ignore"):
            sp, ta = num[k][0] / den[k][0], num[k][1] / den[k][1]
        for t in range(len(months)):
            rows.append({"b": build_id, "k": k, "m": months[t].astype(date),
                         "s": float(sp[t]) if np.isfinite(sp[t]) else None,
                         "t": float(ta[t]) if np.isfinite(ta[t]) else None})
        wrows.append({"b": build_id, "k": k, "n": int(len(i)), "a": float(w.sum())})
    session.execute(text("""INSERT INTO crop_weather_targets (build_id, target, cells, weight) VALUES
                            (CAST(:b AS uuid), :k, :n, :a)"""), wrows)
    for x in range(0, len(rows), 50_000):
        session.execute(text("""INSERT INTO crop_weather_monthly (build_id, target, month, spei6, temp_anom)
                                VALUES (CAST(:b AS uuid), :k, :m, :s, :t)"""), rows[x:x + 50_000])
    return build_id


def latest(session: Session, target: str) -> dict | None:
    r = session.execute(text("""
        SELECT b.build_id::text, t.cells, CAST(t.weight AS FLOAT) AS weight, b.last_month, b.inputs
        FROM crop_weather_targets t JOIN crop_weather_builds b ON b.build_id = t.build_id
        WHERE t.target = :k ORDER BY b.seq DESC LIMIT 1"""), {"k": target}).mappings().first()
    return dict(r) if r else None


def monthly(session: Session, build_id: str, target: str) -> dict[tuple[int, int], tuple]:
    """{(year, month): (spei6, temp_anom)} of one target in a build."""
    return {(m.year, m.month): (s, t) for m, s, t in session.execute(text("""
        SELECT month, CAST(spei6 AS FLOAT), CAST(temp_anom AS FLOAT) FROM crop_weather_monthly
        WHERE build_id = CAST(:b AS uuid) AND target = :k ORDER BY month"""), {"b": build_id, "k": target}).all()}

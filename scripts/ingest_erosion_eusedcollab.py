"""Prep step for the soil_erosion independent backtest — turns the raw EUSEDcollab catchment network
(data/erosion_val/eusedcollab/EUSEDcollab_data_repository/) into a clean per-catchment specific sediment
yield (SSY, t ha⁻¹ yr⁻¹) that is directly comparable to GloSEM's soil-displacement rate (same units).

EUSEDcollab ships one Q_SSL/*.csv per catchment, but the six declared "Data type" values in ALL_METADATA.csv
use different SSL column layouts (monthly/daily/event totals, or a variable-timestep flux); "Q and rating
curve data" catchments carry no measured SSL column at all (sediment load is only implied by a rating curve)
and are skipped — including them would require running someone else's regression, not reading an observation.
For everything else: sum every row's SSL column across the whole file (unit-normalised to tonnes), divide by
the catchment drainage area (ha) and by the record's span in years (from the first/last timestamp in the data
itself, not the metadata's nominal start/end, since real coverage has gaps) to get SSY in t ha⁻¹ yr⁻¹.

Output: data/erosion_val/eusedcollab_ssy.csv — catchment_id, name, country, lat, lon, drainage_ha,
n_records, years, ssy_t_ha_yr, data_type.

Run:  python -m scripts.ingest_erosion_eusedcollab
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd

REPO = Path("data/erosion_val/eusedcollab/EUSEDcollab_data_repository")
METADATA_CSV = REPO / "ALL_METADATA.csv"
Q_SSL_DIR = REPO / "Q_SSL"
OUT_CSV = Path("data/erosion_val/eusedcollab_ssy.csv")

MIN_YEARS = 0.5   # below this a specific yield is mostly measurement-window noise
SKIP_DATA_TYPES = {"Q and rating curve data"}   # no measured SSL column — a rating-curve estimate, not an observation

# SSL column name -> (unit multiplier to tonnes, is a DATE column needed as the row's own time reference)
_SSL_COL_RE = re.compile(r"^SSL \((kg|T)\s")


def _ssl_column(columns: list[str]) -> str | None:
    for c in columns:
        if _SSL_COL_RE.match(c):
            return c
    return None


def _to_tonnes(col_name: str, series: pd.Series) -> pd.Series:
    unit = col_name.split("(")[1].split()[0]   # "kg" or "T"
    vals = pd.to_numeric(series, errors="coerce")
    return vals / 1000.0 if unit == "kg" else vals


def _date_columns(columns: list[str]) -> tuple[str | None, str | None]:
    """(start_col, end_col) — event files have both; timeseries files have one 'Date' column (used as both)."""
    start = next((c for c in columns if c.startswith("Date (") or c.startswith("Start date (")), None)
    end = next((c for c in columns if c.startswith("End date (")), None)
    return start, end or start


def load_catchment_ssy(path: Path) -> dict | None:
    """One catchment's (total_ssy_t_ha_yr, n_records, years, data_span) or None if not usable."""
    try:
        df = pd.read_csv(path, encoding="latin1")
    except Exception:
        return None
    if df.empty:
        return None
    ssl_col = _ssl_column(list(df.columns))
    start_col, end_col = _date_columns(list(df.columns))
    if ssl_col is None or start_col is None:
        return None
    tonnes = _to_tonnes(ssl_col, df[ssl_col])
    total_tonnes = float(tonnes.sum(skipna=True))
    n = int(tonnes.notna().sum())
    if n == 0:
        return None
    starts = pd.to_datetime(df[start_col], errors="coerce", dayfirst=True)
    ends = pd.to_datetime(df[end_col], errors="coerce", dayfirst=True) if end_col else starts
    t0, t1 = starts.min(), ends.max()
    if pd.isna(t0) or pd.isna(t1):
        return None
    years = (t1 - t0).days / 365.25
    if years < MIN_YEARS:
        return None
    return {"total_tonnes": total_tonnes, "n_records": n, "years": years}


def main() -> int:
    meta = pd.read_csv(METADATA_CSV)
    rows_out = []
    n_skipped_rating, n_missing_file, n_bad_area, n_unusable, n_ok = 0, 0, 0, 0, 0
    for _, r in meta.iterrows():
        if r["Data type"] in SKIP_DATA_TYPES:
            n_skipped_rating += 1
            continue
        fpath = Q_SSL_DIR / str(r["File name"])
        if not fpath.exists():
            n_missing_file += 1
            continue
        area_ha = r.get("Drainage area (ha)")
        try:
            area_ha = float(area_ha)
        except (TypeError, ValueError):
            area_ha = None
        if area_ha is None or area_ha != area_ha or area_ha <= 0:   # `!=` self-check catches NaN
            n_bad_area += 1
            continue
        res = load_catchment_ssy(fpath)
        if res is None:
            n_unusable += 1
            continue
        ssy = res["total_tonnes"] / (area_ha * res["years"])
        rows_out.append({
            "catchment_id": int(r["Catchment ID"]), "name": r["Catchment name"], "country": r["Country"],
            "lat": float(r["Latitude (4 decimal places)"]), "lon": float(r["Longitude (4 decimal places)"]),
            "drainage_ha": area_ha, "n_records": res["n_records"], "years": round(res["years"], 2),
            "ssy_t_ha_yr": ssy, "data_type": r["Data type"],
        })
        n_ok += 1

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["catchment_id", "name", "country", "lat", "lon", "drainage_ha",
                                          "n_records", "years", "ssy_t_ha_yr", "data_type"])
        w.writeheader()
        w.writerows(rows_out)
    print(f"wrote {n_ok} catchments -> {OUT_CSV}")
    print(f"skipped: {n_skipped_rating} rating-curve-only, {n_missing_file} missing file, "
          f"{n_bad_area} no/zero drainage area, {n_unusable} no usable SSL/date columns or <{MIN_YEARS}yr span")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Multi-event wildfire training + leave-one-event-out backtest.

Same treatment as flood, for fire. The wildfire model uses fire-WEATHER features
(the FIRMS/NDVI fire-detection inputs were never ingested):
  gfs_wind_speed_ms        — sqrt(u10² + v10²) on the peak day
  gfs_relative_humidity_pct— from 2m temperature + dewpoint (Magnus)
  days_since_last_rain     — consecutive dry days (precip < 1mm) before the peak

Fetches ERA5 for several real European wildfires, builds these features, labels
the documented burned area, and runs leave-one-event-out. Cached to
data/multievent_wildfire.parquet.
"""
import os
import warnings
from datetime import date, timedelta

warnings.filterwarnings("ignore")
import h3
import numpy as np
import pandas as pd
import xarray as xr
from sklearn.metrics import average_precision_score, roc_auc_score

CACHE = "data/multievent_wildfire_fuel.parquet"
# Added the missing physics — FUEL: vegetation density (leaf-area-index, high+low veg)
# and dryness (soil water). Both come from the SAME ERA5-Land/CDS API we already use,
# so no new credentials. FIRMS/NDVI proper need a NASA key; LAI is a fuel proxy we can
# act on now. This is the feature the weather-only model was missing.
FEATS = ["gfs_wind_speed_ms", "gfs_relative_humidity_pct", "days_since_last_rain",
         "fuel_load_lai", "soil_moisture"]
VARS = ["10m_u_component_of_wind", "10m_v_component_of_wind",
        "2m_temperature", "2m_dewpoint_temperature", "total_precipitation",
        "leaf_area_index_high_vegetation", "leaf_area_index_low_vegetation",
        "volumetric_soil_water_layer_1"]
H3_RES = 8
WINDOW = 15  # days before peak (for days-since-rain)

# Real European wildfires. fetch_area / burn_bbox are [N, W, S, E].
EVENTS = [
    {"name": "2017 Pedrógão (Portugal)", "peak": date(2017, 6, 18), "fetch_area": [41.0, -9.0, 39.0, -6.5], "burn_bbox": [40.3, -8.4, 39.7, -7.7]},
    {"name": "2018 Mati/Attica (Greece)", "peak": date(2018, 7, 23), "fetch_area": [39.0, 22.0, 37.0, 25.0], "burn_bbox": [38.2, 23.7, 37.9, 24.2]},
    {"name": "2021 Evia (Greece)",        "peak": date(2021, 8, 8),  "fetch_area": [39.5, 22.0, 38.0, 24.5], "burn_bbox": [39.0, 23.0, 38.5, 24.0]},
    {"name": "2022 Gironde (France)",     "peak": date(2022, 7, 15), "fetch_area": [45.5, -1.7, 44.0, 0.0], "burn_bbox": [44.8, -1.3, 44.3, -0.5]},
    {"name": "2022 Culebra (Spain)",      "peak": date(2022, 6, 15), "fetch_area": [42.5, -7.0, 41.3, -5.3], "burn_bbox": [42.1, -6.6, 41.8, -6.0]},
    {"name": "2023 Alexandroupolis (Greece)", "peak": date(2023, 8, 22), "fetch_area": [41.6, 25.0, 40.5, 26.6], "burn_bbox": [41.2, 25.7, 40.8, 26.3]},
    {"name": "2023 Rhodes (Greece)",      "peak": date(2023, 7, 23), "fetch_area": [36.7, 27.4, 35.8, 28.6], "burn_bbox": [36.3, 27.8, 36.0, 28.2]},
    {"name": "2017 Iberia Oct (Galicia)", "peak": date(2017, 10, 15),"fetch_area": [43.5, -9.0, 41.0, -6.5], "burn_bbox": [42.5, -8.5, 41.5, -7.3]},
]


def fetch(ev):
    import shutil
    import tempfile
    import zipfile

    import cdsapi
    days = [ev["peak"] - timedelta(days=k) for k in range(WINDOW)]
    c = cdsapi.Client(quiet=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False); tmp.close()
    c.retrieve("reanalysis-era5-land", {
        "variable": VARS,
        "year": sorted({str(d.year) for d in days}),
        "month": sorted({f"{d.month:02d}" for d in days}),
        "day": sorted({f"{d.day:02d}" for d in days}),
        "time": ["12:00"],  # midday: hottest/driest, peak fire weather
        "area": ev["fetch_area"], "format": "netcdf",
    }, tmp.name)
    p = tmp.name
    if zipfile.is_zipfile(p):
        z = zipfile.ZipFile(p); nc = [n for n in z.namelist() if n.endswith(".nc")][0]
        o = p + "_d.nc"
        with z.open(nc) as s, open(o, "wb") as d:
            shutil.copyfileobj(s, d)
        os.unlink(p); p = o
    return xr.open_dataset(p)


def _rh(t_k, td_k):
    t, td = t_k - 273.15, td_k - 273.15
    es = np.exp(17.625 * t / (243.04 + t))
    e = np.exp(17.625 * td / (243.04 + td))
    return np.clip(100.0 * e / es, 0, 100)


def features(ds, ev):
    tvar = "valid_time" if "valid_time" in ds else "time"
    lat = ds["latitude"].values; lon = ds["longitude"].values
    u = ds["u10"]; v = ds["v10"]; t2 = ds["t2m"]; d2 = ds["d2m"]; tp = ds["tp"]
    # peak day = last in window
    wind = np.sqrt(u.isel({tvar: -1}) ** 2 + v.isel({tvar: -1}) ** 2).values
    rh = _rh(t2.isel({tvar: -1}).values, d2.isel({tvar: -1}).values)
    # FUEL: leaf-area-index (high+low veg) = how much burnable vegetation;
    #       soil water layer 1 = dryness (low = dry fuel = fire-prone)
    lai = ds["lai_hv"].isel({tvar: -1}).values + ds["lai_lv"].isel({tvar: -1}).values
    sm = ds["swvl1"].isel({tvar: -1}).values
    # days since last rain: walk back from peak, count days with precip < 1mm
    tp_mm = (tp * 1000.0).values  # (time, lat, lon)
    nt = tp_mm.shape[0]
    dslr = np.zeros_like(wind)
    for i in range(wind.shape[0]):
        for j in range(wind.shape[1]):
            cnt = 0
            for k in range(nt - 1, -1, -1):
                if np.isnan(tp_mm[k, i, j]) or tp_mm[k, i, j] >= 1.0:
                    break
                cnt += 1
            dslr[i, j] = cnt
    rows = []
    for i, la in enumerate(lat):
        for j, lo in enumerate(lon):
            if np.isnan(wind[i, j]):
                continue
            in_burn = (ev["burn_bbox"][2] <= la <= ev["burn_bbox"][0]
                       and ev["burn_bbox"][1] <= lo <= ev["burn_bbox"][3])
            rows.append({
                "h3_cell": h3.latlng_to_cell(float(la), float(lo), H3_RES),
                "gfs_wind_speed_ms": float(wind[i, j]),
                "gfs_relative_humidity_pct": float(rh[i, j]),
                "days_since_last_rain": float(dslr[i, j]),
                "fuel_load_lai": float(lai[i, j]) if not np.isnan(lai[i, j]) else 0.0,
                "soil_moisture": float(sm[i, j]) if not np.isnan(sm[i, j]) else 0.0,
                "y": int(in_burn),
            })
    return pd.DataFrame(rows).groupby("h3_cell", as_index=False).agg(
        gfs_wind_speed_ms=("gfs_wind_speed_ms", "max"),
        gfs_relative_humidity_pct=("gfs_relative_humidity_pct", "min"),
        days_since_last_rain=("days_since_last_rain", "max"),
        fuel_load_lai=("fuel_load_lai", "max"),
        soil_moisture=("soil_moisture", "min"),
        y=("y", "max"))


def build():
    cached = pd.read_parquet(CACHE) if os.path.exists(CACHE) else pd.DataFrame()
    have = set(cached.event.unique()) if len(cached) else set()
    frames = [cached] if len(cached) else []
    for ev in EVENTS:
        if ev["name"] in have:
            continue
        print(f"• {ev['name']} ({ev['peak']}) — fetching ERA5 …", flush=True)
        try:
            ds = fetch(ev); df = features(ds, ev); ds.close()
        except Exception as e:
            print(f"   FAILED: {str(e)[:120]}"); continue
        df["event"] = ev["name"]
        print(f"   {len(df)} cells, {int(df.y.sum())} burn cells, "
              f"min RH {df.gfs_relative_humidity_pct.min():.0f}%, max dry {df.days_since_last_rain.max():.0f}d, "
              f"LAI {df.fuel_load_lai.mean():.2f} (burn {df[df.y==1].fuel_load_lai.mean():.2f} vs "
              f"unburn {df[df.y==0].fuel_load_lai.mean():.2f})")
        frames.append(df)
    data = pd.concat(frames, ignore_index=True)
    os.makedirs("data", exist_ok=True); data.to_parquet(CACHE)
    print(f"cached {len(data)} rows across {data.event.nunique()} events")
    return data


def loeo(data):
    from ml.scoring.ensemble import EnsembleScorer
    print(f"\n=== Wildfire leave-one-event-out ({data.event.nunique()} events) ===\n")
    py, ps = [], []
    for held in data.event.unique():
        tr, te = data[data.event != held], data[data.event == held]
        if te.y.sum() == 0 or tr.y.sum() == 0:
            continue
        sc = EnsembleScorer(scale_pos_weight=8.0)
        sc.fit(tr[FEATS].values, tr.y.values.astype(int), feature_cols=FEATS)
        s = (sc.score_dataframe(te[FEATS].copy())["score"] / 100.0).values
        y = te.y.values.astype(int)
        print(f"  hold out {held:28s} AUC={roc_auc_score(y,s):.3f}  AP={average_precision_score(y,s):.3f}  (base {y.mean():.3f})")
        py += y.tolist(); ps += s.tolist()
    py, ps = np.array(py), np.array(ps)
    print(f"\n  POOLED LOEO  ROC-AUC={roc_auc_score(py,ps):.3f}  Avg-Precision={average_precision_score(py,ps):.3f}  base={py.mean():.3f}\n")


if __name__ == "__main__":
    loeo(build())

"""
Daily forecast verification — Venezuela M7.5 aftershock sequence.

Compares our Omori-Utsu / Reasenberg-Jones forecast against reality each day and
reports how many standard deviations off we are (the z-score). Two checks:

1. COUNT: the law predicts an expected cumulative number of M>=4.5 aftershocks
   since the mainshock; for a Poisson process sigma = sqrt(expected), so
   z = (observed - predicted) / sigma. |z|<=1 within one std dev; |z|>2 = the
   model is materially off and the generic RJ parameters need recalibration.
2. LARGEST: our model gave P(M>=5 aftershock) ~ 1.0; we check whether a damaging
   M>=5 aftershock has actually occurred yet.

Queries USGS directly (authoritative, complete to ~M4.5) so it does not depend on
the ingestion watcher. Appends one row per day to forecast_verification.

Usage:  python scripts/verify_venezuela_aftershocks.py
"""
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")
import numpy as np
import requests
from sqlalchemy import text

from core.db.session import get_session
from ml.scoring.seismic_physics import expected_aftershocks

# Mainshock: the M7.5 near Yumare (the M7.2 38s earlier is a foreshock, excluded).
MAIN = {"mag": 7.5, "lat": 10.44, "lon": -68.47,
        "time": datetime(2026, 6, 24, 22, 5, 11, tzinfo=timezone.utc)}
ZONE_KM = 150.0     # aftershock zone (~1-2 rupture lengths for M7.5)
MMIN = 4.5          # catalog completeness / our ingester threshold
USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"

DDL = """
CREATE TABLE IF NOT EXISTS forecast_verification (
    id              serial PRIMARY KEY,
    hazard          text, region text, mainshock_time timestamptz,
    as_of           timestamptz, as_of_date date, elapsed_days numeric, mmin numeric,
    predicted_count numeric, sigma numeric, observed_count int,
    z_score         numeric, within_1sigma boolean, within_2sigma boolean,
    largest_obs_mag numeric, m5_forecast numeric, m5_occurred boolean,
    note            text, created_at timestamptz DEFAULT now(),
    UNIQUE (region, as_of_date)
);
"""


def haversine(la1, lo1, la2, lo2):
    r = 6371.0
    dp, dl = np.radians(la2 - la1), np.radians(lo2 - lo1)
    a = (np.sin(dp / 2) ** 2 + np.cos(np.radians(la1)) * np.cos(np.radians(la2)) * np.sin(dl / 2) ** 2)
    return 2 * r * np.arcsin(np.sqrt(a))


def observed(now):
    """Fetch USGS events in the zone, after the mainshock, M>=MMIN."""
    pad = 1.6  # deg ~ 175 km box, then filter by exact distance
    r = requests.get(USGS, params={
        "format": "geojson", "starttime": MAIN["time"].strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": now.strftime("%Y-%m-%dT%H:%M:%S"), "minmagnitude": MMIN,
        "minlatitude": MAIN["lat"] - pad, "maxlatitude": MAIN["lat"] + pad,
        "minlongitude": MAIN["lon"] - pad, "maxlongitude": MAIN["lon"] + pad,
    }, timeout=40)
    r.raise_for_status()
    n, largest = 0, 0.0
    for f in r.json().get("features", []):
        p = f["properties"]; lon, lat, _ = f["geometry"]["coordinates"]
        t = datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc)
        if t <= MAIN["time"] + timedelta(seconds=60):   # mainshock + immediate doublet
            continue
        if p["mag"] is None or float(p["mag"]) < MMIN:
            continue
        if float(p["mag"]) >= MAIN["mag"] - 0.5:        # M>=7 = the doublet, not an aftershock
            continue
        if haversine(MAIN["lat"], MAIN["lon"], float(lat), float(lon)) > ZONE_KM:
            continue
        n += 1
        largest = max(largest, float(p["mag"]))
    return n, largest


def main():
    now = datetime.now(timezone.utc)
    elapsed = (now - MAIN["time"]).total_seconds() / 86400.0
    predicted = expected_aftershocks(MAIN["mag"], elapsed, 0.0, MMIN)
    sigma = predicted ** 0.5 if predicted > 0 else 0.0
    obs, largest = observed(now)
    z = (obs - predicted) / sigma if sigma > 0 else 0.0
    m5_fc = 1.0 - np.exp(-expected_aftershocks(MAIN["mag"], elapsed, 0.0, 5.0))
    m5_occurred = largest >= 5.0

    verdict = ("WITHIN 1 sigma" if abs(z) <= 1 else
               "within 2 sigma" if abs(z) <= 2 else
               "OUT OF BAND — model materially off")
    print(f"Venezuela M7.5 aftershocks — day {elapsed:.1f}")
    print(f"  count M>={MMIN}: predicted {predicted:.1f} +/- {sigma:.1f}  observed {obs}  "
          f"z = {z:+.1f}  -> {verdict}")
    print(f"  largest aftershock so far: M{largest:.1f}  |  P(M>=5) forecast {m5_fc:.2f}  "
          f"occurred: {m5_occurred}")

    with get_session() as s:
        s.execute(text(DDL))
        s.execute(text("""
            INSERT INTO forecast_verification
              (hazard, region, mainshock_time, as_of, as_of_date, elapsed_days, mmin,
               predicted_count, sigma, observed_count, z_score, within_1sigma, within_2sigma,
               largest_obs_mag, m5_forecast, m5_occurred, note)
            VALUES
              ('seismic','Venezuela M7.5', :mt, :now, :asof_d, :el, :mmin, :pred, :sig, :obs, :z,
               :w1, :w2, :lg, :m5f, :m5o, :note)
            ON CONFLICT (region, as_of_date) DO UPDATE SET
               as_of=EXCLUDED.as_of, elapsed_days=EXCLUDED.elapsed_days,
               predicted_count=EXCLUDED.predicted_count, sigma=EXCLUDED.sigma,
               observed_count=EXCLUDED.observed_count, z_score=EXCLUDED.z_score,
               within_1sigma=EXCLUDED.within_1sigma, within_2sigma=EXCLUDED.within_2sigma,
               largest_obs_mag=EXCLUDED.largest_obs_mag, m5_occurred=EXCLUDED.m5_occurred,
               note=EXCLUDED.note
        """), {"mt": MAIN["time"], "now": now, "asof_d": now.date(), "el": round(elapsed, 2), "mmin": MMIN,
               "pred": round(predicted, 2), "sig": round(sigma, 2), "obs": obs, "z": round(z, 2),
               "w1": abs(z) <= 1, "w2": abs(z) <= 2, "lg": largest, "m5f": round(float(m5_fc), 3),
               "m5o": m5_occurred, "note": verdict})
    print("  recorded to forecast_verification")


if __name__ == "__main__":
    main()

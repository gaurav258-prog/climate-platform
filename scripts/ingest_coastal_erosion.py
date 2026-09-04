"""Preprocess the JRC LISCOAST global shoreline-retreat projections into the coastal_erosion_cell H3 lookup.

Source (authoritative, open) — Vousdoukas et al. (2020), "Sandy coastlines under threat of erosion", Nature
Climate Change; JRC LISCOAST "Global shoreline change projections" (globalErosionProjections.zip, CSV). Each
CSV row is: lat, lon, then the long-term shoreline change (metres; negative = erosion/retreat) at percentiles
1, 5, 17, 50, 83, 95, 99, for one RCP × year. We take the median (P50), bin to H3 res-8, and store the mean
P50 per (cell, rcp, year) so a coastal asset's cell has a scenario-dependent retreat figure.

Run (after scripts/fetch — the zip is downloaded + extracted into data/coastal_erosion/):
  .venv/bin/python -m scripts.ingest_coastal_erosion
"""
from __future__ import annotations

import glob
import os
import re

import h3
import pandas as pd
from sqlalchemy import text

from core.db.session import get_session

DATA_DIR = "data/coastal_erosion"
# res-7 (~1.2 km edge) — transects are spaced 500 m, so res-7 gives near-complete coastal coverage; a coastal
# asset is scored by the res-7 parent of its point (the score itself is still cached at the asset's res-8 cell).
H3_RES = 7
VINTAGE = "JRC LISCOAST / Vousdoukas et al. 2020 (Long-Term Change)"
_FILE_RE = re.compile(r"RCP(\d\d)_(\d{4})", re.IGNORECASE)


def _rcp_year(path: str):
    m = _FILE_RE.search(os.path.basename(path))
    return (f"rcp{m.group(1)}", int(m.group(2))) if m else (None, None)


def main() -> int:
    files = sorted(glob.glob(os.path.join(DATA_DIR, "globalErosionProjections_*_RCP*_*.csv")))
    if not files:
        print(f"no coastal-erosion CSVs in {DATA_DIR} — run the download first "
              f"(curl the JRC LISCOAST globalErosionProjections.zip, extract here).")
        return 2
    total = 0
    for path in files:
        rcp, year = _rcp_year(path)
        if not rcp:
            print(f"skip (no RCP/year in name): {path}"); continue
        df = pd.read_csv(path, header=None,
                         names=["lat", "lon", "p1", "p5", "p17", "p50", "p83", "p95", "p99"])
        df = df[["lat", "lon", "p50"]].dropna()
        df["h3_cell"] = [h3.latlng_to_cell(float(la), float(lo), H3_RES) for la, lo in zip(df["lat"], df["lon"])]
        agg = df.groupby("h3_cell", as_index=False)["p50"].mean().rename(columns={"p50": "retreat_m"})
        rows = [{"c": r.h3_cell, "rcp": rcp, "y": year, "r": float(r.retreat_m), "v": VINTAGE}
                for r in agg.itertuples()]
        with get_session() as s:
            # replace this (rcp, year) slice, then bulk insert
            s.execute(text("DELETE FROM coastal_erosion_cell WHERE rcp=:rcp AND year=:y"), {"rcp": rcp, "y": year})
            for i in range(0, len(rows), 5000):
                s.execute(text("""
                    INSERT INTO coastal_erosion_cell (h3_cell, rcp, year, retreat_m, data_vintage)
                    VALUES (:c, :rcp, :y, :r, :v)
                    ON CONFLICT (h3_cell, rcp, year) DO UPDATE SET retreat_m = EXCLUDED.retreat_m
                """), rows[i:i + 5000])
            s.commit()
        print(f"{os.path.basename(path)}: {rcp} {year} → {len(rows):,} cells", flush=True)
        total += len(rows)
    print(f"done: {total:,} (cell × rcp × year) rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

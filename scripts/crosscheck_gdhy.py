"""Cross-check of the official regional yields against GDHY (Iizumi & Sakai 2020; data/reference/supply_datasets.json
gdhy_v1_2_v1_3) — a check only: GDHY is modelled from satellite vegetation indices and FAO national statistics, so it is
never a calibration target and nothing here is stored or published.

For every regional recipe of a crop GDHY covers (maize, rice, wheat, soybean) with a fitted run: GDHY's yield in the
region (0.5° cells weighted by the crop's harvested area inside the region — the regional weights) beside the official
series the recipe reads, each linearly detrended over the years both hold; the correlation of the two anomalies says
whether the official series' year-to-year signal is the one a satellite sees.

Two steps, so the downloaded file is read only by an isolated interpreter that imports nothing from the project:
    venv/bin/python -m scripts.crosscheck_gdhy export --out <panel.json>
    venv/bin/python -I scripts/crosscheck_gdhy.py compare --zip data/datasets/gdhy_v1_2_v1_3/PANGAEA.909132.zip \
        --panel <panel.json> [--out <result.json>]
"""
from __future__ import annotations

import argparse
import json
import sys

GDHY = {"Maize": "maize", "Rice": "rice", "Wheat": "wheat", "Soybean": "soybean"}


def export(out: str) -> int:
    """The panel: per regional recipe of a GDHY crop with a fitted run, its 0.5° cells with harvested ha and its official
    yields."""
    from sqlalchemy import text

    from core.db.session import get_session
    from ml.features import yield_series
    from services.calibration import crop_area_weights as W
    rows = []
    with get_session() as s:
        for sp in s.execute(text("""
                SELECT s.commodity, s.origin, s.yield_source, s.yield_region, CAST(r.r2_oos AS FLOAT) AS r2_oos,
                       r.downside_pass
                FROM crop_calibration_specs s JOIN LATERAL (SELECT * FROM crop_calibration_runs x WHERE x.spec_id = s.spec_id
                     AND x.outcome = 'fitted' ORDER BY x.seq DESC LIMIT 1) r ON true
                WHERE s.retired_at IS NULL AND s.yield_region <> '' AND s.commodity = ANY(:c)"""),
                {"c": list(GDHY)}).mappings():
            idx, ha = W.regional_weights(sp["commodity"])[sp["yield_region"]]
            lat = 90.0 - (idx // W.ERA5_NX) * W.ERA5_RES
            lon = (idx % W.ERA5_NX) * W.ERA5_RES
            cells: dict[tuple[int, int], float] = {}
            for la, lo, w in zip(lat, lon, ha):
                key = (int((la + 90.0) // 0.5), int((lo % 360.0) // 0.5))
                cells[key] = cells.get(key, 0.0) + float(w)
            ys = yield_series.series(s, sp["commodity"], sp["origin"], sp["yield_source"], sp["yield_region"],
                                     field="yield_tonnes_ha")
            rows.append({**dict(sp), "cells": [[i, j, w] for (i, j), w in sorted(cells.items())],
                         "official": {str(y): v for y, v in ys.items()}})
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    print(f"{len(rows)} regional recipes written to {out}")
    return 0


def _detrended(ys: dict[int, float]) -> dict[int, float]:
    import numpy as np
    yrs = np.array(sorted(ys), dtype=float)
    v = np.array([ys[int(y)] for y in yrs])
    b, a = np.polyfit(yrs, v, 1)
    return {int(y): float(x - (a + b * y)) for y, x in zip(yrs, v)}


def compare(zip_path: str, panel_path: str, out: str | None) -> int:
    """Reads the GDHY archive (numpy, netCDF4 and the standard library only) and correlates each region's anomalies."""
    import zipfile

    import netCDF4
    import numpy as np
    panel = json.load(open(panel_path, encoding="utf-8"))
    z = zipfile.ZipFile(zip_path)
    grids: dict[tuple[str, int], np.ndarray] = {}
    for name in z.namelist():
        parts = name.split("/")
        if len(parts) == 2 and parts[0] in GDHY.values() and parts[1].startswith("yield_"):
            with netCDF4.Dataset("gdhy", memory=z.read(name)) as ds:
                grids[(parts[0], int(parts[1][6:10]))] = np.ma.filled(ds.variables["var"][:].astype(float), np.nan)
    results = []
    for r in panel:
        crop = GDHY[r["commodity"]]
        cells = np.array(r["cells"])
        ii, jj, w = cells[:, 0].astype(int), cells[:, 1].astype(int), cells[:, 2]
        gd = {}
        for (c, year), g in grids.items():
            if c != crop:
                continue
            v = g[ii, jj]
            ok = np.isfinite(v)
            if ok.any() and w[ok].sum() >= 0.5 * w.sum():          # the satellite estimate covers half the crop's area
                gd[year] = float((v[ok] * w[ok]).sum() / w[ok].sum())
        off = {int(y): v for y, v in r["official"].items() if v is not None}
        common = sorted(set(gd) & set(off))
        if len(common) < 10:
            results.append({**{k: r[k] for k in ("commodity", "yield_region", "r2_oos", "downside_pass")},
                            "n": len(common), "r": None})
            continue
        a, b = _detrended({y: gd[y] for y in common}), _detrended({y: off[y] for y in common})
        rr = float(np.corrcoef([a[y] for y in common], [b[y] for y in common])[0, 1])
        results.append({**{k: r[k] for k in ("commodity", "yield_region", "r2_oos", "downside_pass")},
                        "n": len(common), "years": [common[0], common[-1]], "r": round(rr, 3)})
    results.sort(key=lambda x: (x["commodity"], -(x["r2_oos"] or -9)))
    for x in results:
        print(f"{x['commodity']:8} {x['yield_region']:6} fit r2_oos={x['r2_oos']}  pass={x['downside_pass']}  "
              f"GDHY vs official anomalies r={x['r']} (n={x['n']})")
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--out", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--zip", required=True)
    c.add_argument("--panel", required=True)
    c.add_argument("--out")
    a = ap.parse_args()
    return export(a.out) if a.cmd == "export" else compare(a.zip, a.panel, a.out)


if __name__ == "__main__":
    sys.exit(main())

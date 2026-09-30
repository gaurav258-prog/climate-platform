"""Load WRI Aqueduct 4.0 baseline annual water risk (basins with their boundaries) into aqueduct_basins as a new load;
the previous load is retired, never deleted (a filing names the load it read).

    venv/bin/python -m scripts.ingest_aqueduct data/aqueduct/aqueduct-4-0-water-risk-data.zip
The zip is WRI's official download (data/reference/esrs/water_stress.json names its source and licence); it is
unpacked next to it. Fields: bws_* (baseline water stress) and bwd_* (baseline water depletion), as WRI codes them.
"""
from __future__ import annotations

import glob
import hashlib
import sys
import zipfile
from pathlib import Path

import pyogrio
from shapely import wkb
from sqlalchemy import text

from core.db.session import get_session

FIELDS = ["string_id", "pfaf_id", "gid_1", "name_0", "name_1", "bws_raw", "bws_cat", "bws_label", "bwd_raw", "bwd_cat", "bwd_label"]


def main(zip_path: str) -> None:
    z = Path(zip_path)
    sha = hashlib.sha256(z.read_bytes()).hexdigest()
    with zipfile.ZipFile(z) as zf:
        zf.extractall(z.parent)
    gdb = glob.glob(str(z.parent / "Aqueduct40_waterrisk_download_*" / "GDB" / "*.gdb"))[0]
    df = pyogrio.read_dataframe(gdb, layer="baseline_annual", columns=FIELDS)
    print(f"{len(df):,} basins read from {gdb}")
    rows = []
    for r in df.itertuples(index=False):
        g = r.geometry
        if g is None or g.is_empty:
            continue
        minx, miny, maxx, maxy = g.bounds
        rows.append({"s": r.string_id, "p": int(r.pfaf_id) if r.pfaf_id == r.pfaf_id else None, "g1": r.gid_1, "n0": r.name_0,
                     "n1": r.name_1, "br": r.bws_raw, "bc": int(r.bws_cat), "bl": r.bws_label, "dr": r.bwd_raw,
                     "dc": int(r.bwd_cat), "dl": r.bwd_label, "x0": minx, "y0": miny, "x1": maxx, "y1": maxy,
                     "w": wkb.dumps(g)})
    with get_session() as s:
        s.execute(text("UPDATE aqueduct_loads SET retired_at = now() WHERE retired_at IS NULL"))
        load = s.execute(text("""
            INSERT INTO aqueduct_loads (version, data_vintage, source, sha256, n_basins)
            VALUES ('4.0', '2023-07-05', :src, :sha, :n) RETURNING load_id::text
        """), {"src": "https://files.wri.org/aqueduct/aqueduct-4-0-water-risk-data.zip (baseline_annual)", "sha": sha,
               "n": len(rows)}).scalar()
        for i in range(0, len(rows), 2000):
            s.execute(text("""
                INSERT INTO aqueduct_basins (load_id, string_id, pfaf_id, gid_1, name_0, name_1, bws_raw, bws_cat, bws_label,
                                             bwd_raw, bwd_cat, bwd_label, minx, miny, maxx, maxy, geom_wkb)
                VALUES (CAST(:l AS uuid), :s, :p, :g1, :n0, :n1, :br, :bc, :bl, :dr, :dc, :dl, :x0, :y0, :x1, :y1, :w)
            """), [{**r, "l": load} for r in rows[i:i + 2000]])
        s.commit()
    print(f"load {load}: {len(rows):,} basins (sha256 {sha[:12]}…)")


if __name__ == "__main__":
    main(sys.argv[1])

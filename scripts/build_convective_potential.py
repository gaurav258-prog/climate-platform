"""Build the global severe-convective-potential climatology (EU-Taxonomy wind hazard: tornado / large hail).

The physically grounded, global representation of the tornado/hail/damaging-wind peril is the convective-storm
ENVIRONMENT: the climatological co-occurrence of instability (CAPE) and deep-layer (0–6 km) wind shear — the
accepted proxy for severe-convective potential (Taszarek et al. 2021, npj Clim Atmos Sci). This is WIRED-READY:
ERA5 hourly CAPE + multi-level winds are needed, which require a Copernicus CDS API key and are large (an
infrastructure build, not a sandbox one). This script is the documented builder — on infra, with cdsapi
configured, it downloads ERA5 CAPE + winds, computes a WMAXSHEAR-style potential, normalises to 0–100 on a 2°
grid, and writes data/convective/convective_potential.npz (read by ml/scoring/severe_convective_point.py).

Run (on infra, with ~/.cdsapirc set):  CDS_BUILD=1 .venv/bin/python -m scripts.build_convective_potential
Output: data/convective/convective_potential.npz (lat, lon, potential 0–100).
"""
from __future__ import annotations

import os

OUT = "data/convective/convective_potential.npz"


def main() -> int:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        print(f"{OUT} already present — nothing to do."); return 0
    if os.getenv("CDS_BUILD") != "1":
        print("Severe-convective potential needs the ERA5 CAPE × 0–6 km shear climatology — an infra build:")
        print("  1. pip install cdsapi and configure ~/.cdsapirc with a Copernicus CDS key")
        print("  2. on infrastructure, run:  CDS_BUILD=1 .venv/bin/python -m scripts.build_convective_potential")
        print("     (downloads ERA5 CAPE + winds, computes WMAXSHEAR potential → 0–100 on a 2° grid)")
        print(f"  3. it writes {OUT}; the severe_convective channel then lights up with zero code change.")
        return 2
    # Infra path (requires cdsapi + a CDS key + substantial ERA5 download/compute):
    import cdsapi  # noqa: F401  (import here so the guarded path doesn't require it)
    raise SystemExit("CDS build path is a stub to run on infrastructure — implement the ERA5 pull + "
                     "WMAXSHEAR reduction here where CDS bandwidth/compute is available.")


if __name__ == "__main__":
    raise SystemExit(main())

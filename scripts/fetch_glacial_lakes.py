"""Fetch the GIGLak global glacial-lake inventory (EU-Taxonomy water hazard: glacial-lake outburst).

Open source — Global Inventory of Glacial Lakes (GIGLak), figshare doi:10.6084/m9.figshare.26310967;
117k glacial lakes worldwide with area / elevation / location. Downloaded as a .rar and extracted; then
scripts/ingest_glacial_lakes.py preprocesses it into the glacial_lake_cell H3 exposure layer.

Run:  .venv/bin/python -m scripts.fetch_glacial_lakes  &&  .venv/bin/python -m scripts.ingest_glacial_lakes
Output: data/glacial_lakes/GIGLak_dataset/... (gitignored, ~100 MB). Idempotent.
"""
from __future__ import annotations

import glob
import os
import subprocess
import urllib.request

DEST_DIR = "data/glacial_lakes"
RAR = os.path.join(DEST_DIR, "GIGLak.rar")
GIGLAK_URL = "https://ndownloader.figshare.com/files/47713981"


def main() -> int:
    os.makedirs(DEST_DIR, exist_ok=True)
    if glob.glob(os.path.join(DEST_DIR, "**", "Global_Lake_Dataset.shp"), recursive=True):
        print("GIGLak already extracted — nothing to do."); return 0
    if not os.path.exists(RAR):
        print("downloading GIGLak inventory (~100 MB) …", flush=True)
        urllib.request.urlretrieve(GIGLAK_URL, RAR)
    print("extracting …", flush=True)
    subprocess.run(["bsdtar", "-xf", "GIGLak.rar"], cwd=DEST_DIR, check=True)
    print("ready — now run scripts.ingest_glacial_lakes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

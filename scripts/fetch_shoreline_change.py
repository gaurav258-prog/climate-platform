"""Satellite-observed historical shoreline change per transect — the independent coastal-erosion target.

Source (open, CC-BY-4.0): Mentaschi et al. (2020) "Multi-decadal shoreline change in coastal Natural World
Heritage Sites — a global assessment", data on Zenodo record 3751980. The transects carry the Landsat-derived
shoreline change of the Luijendijk et al. (2018, "The State of the World's Beaches", Deltares Shoreline
Monitor) global product — the per-transect linear trend `coeflm` in m/yr (negative = erosion), its residual
`std`, the number of annual shorelines, the observation years (dt_min–dt_max, 1984–2016) and a linearity class.

Why this file and not the full global Shoreline Monitor: the 2018 rates are served only through the Deltares
viewer, and the current ShorelineMonitor series on the CoCliCo Azure store needs a SAS token issued on request
(not an anonymous download). The World Heritage subset is the openly downloadable slice of the same product
(67 sites on every continent) — a small but real, independently observed target.

Lands data/coastal_erosion_val/wh_transects_shorelines_linearity.csv (+ the strong-linear subset). Resumable:
a file already present at its full published size is skipped; a partial file is continued with an HTTP Range.
Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_shoreline_change.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

RECORD = "https://zenodo.org/api/records/3751980"
OUT_DIR = Path("data/coastal_erosion_val")
FILES = {
    "2020_transects_data_shorelines_linearity_geomorphology_final.csv": "wh_transects_shorelines_linearity.csv",
    "2020_transects_data_shorelines_strong_linear_geomorphology_final.csv": "wh_transects_shorelines_strong_linear.csv",
}


def _download(url: str, dest: Path, size: int) -> str:
    """Fetch url → dest; skip when complete, resume when partial. Returns 'skipped' | 'resumed' | 'fetched'."""
    have = dest.stat().st_size if dest.exists() else 0
    if size and have == size:
        return "skipped"
    headers = {"Range": f"bytes={have}-"} if 0 < have < size else {}
    mode = "ab" if headers else "wb"
    with requests.get(url, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        if headers and r.status_code != 206:      # server ignored the range — start over
            mode, headers = "wb", {}
        with dest.open(mode) as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return "resumed" if headers else "fetched"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec = requests.get(RECORD, timeout=60).json()
    meta = rec["metadata"]
    print(f"{meta['title']} · {meta.get('publication_date')} · licence {meta.get('license', {}).get('id')}")
    by_key = {f["key"]: f for f in rec["files"]}
    for key, local in FILES.items():
        f = by_key.get(key)
        if not f:
            print(f"  ! {key} not in record"); continue
        dest = OUT_DIR / local
        how = _download(f["links"]["self"], dest, int(f["size"]))
        print(f"  {how:>7} {dest} ({dest.stat().st_size:,} B of {f['size']:,})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

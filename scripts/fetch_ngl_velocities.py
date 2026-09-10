"""NGL MIDAS GNSS station velocities — observed vertical land motion, the independent target for subsidence.

Nevada Geodetic Laboratory MIDAS velocities (IGS14 frame, ~20k stations worldwide): the vertical rate (m/yr, with
its uncertainty) is an OBSERVED ground-motion measurement independent of the Herrera et al. (2021) susceptibility
model the subsidence channel reads. Lands data/subsidence_val/midas.IGS14.txt (git-ignored).
Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_ngl_velocities.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

URL = "https://geodesy.unr.edu/velocities/midas.IGS14.txt"
OUT = Path("data/subsidence_val/midas.IGS14.txt")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(URL, timeout=300); r.raise_for_status()
    OUT.write_bytes(r.content)
    print(f"wrote {OUT}: {len(r.text.splitlines())} stations")
    return 0


if __name__ == "__main__":
    sys.exit(main())

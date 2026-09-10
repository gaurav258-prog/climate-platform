"""Subsidence validator — the Herrera GSS susceptibility class against observed GNSS vertical land motion.

The subsidence channel publishes a six-level susceptibility class (Herrera-García et al. 2021 global model of
groundwater-driven subsidence potential). The only observed, independent, global ground-motion record that is
reachable without a licence is the GNSS station velocity field (NGL MIDAS, scripts/fetch_ngl_velocities.py):
the vertical rate at ~15k stations with ≥5 years of data. Test: does the class rank stations by their observed
subsidence rate (−vertical velocity, mm/yr)? `rank` kind, gate Spearman ≥ 0.35 with monotone bands.

Known limits, stated: GNSS stations are mounted on bedrock or stable structures by design, so the field
under-samples the soft sediments where subsidence happens; glacial rebound regions are excluded because their
vertical motion is not subsidence. InSAR (Copernicus EGMS) is the better target and needs an EGMS account.
Result 2026-09-10: monotone medians by class (0.14 → 1.56 mm/yr) but rank correlation 0.23 overall, 0.22 CONUS,
−0.05 Europe — below the gate; the channel stays Screening and the result is on the ledger.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

MIDAS = Path("data/subsidence_val/midas.IGS14.txt")
MIN_SPAN_YEARS, MAX_SIGMA_MM = 5.0, 2.0
REGIONS = {
    None: lambda la, lo: ~(((la > 50) & (lo > -100) & (lo < 45)) | ((la > 45) & (lo < -60) & (lo > -140))),   # excl. glacial rebound
    "US": lambda la, lo: (la > 24) & (la < 45) & (lo < -66) & (lo > -125),
    "EU": lambda la, lo: (la > 35) & (la < 50) & (lo > -10) & (lo < 30),
}


def _stations() -> list[tuple]:
    out = []
    for line in MIDAS.read_text().splitlines():
        p = line.split()
        if len(p) < 27:
            continue
        span, vu, su, lat, lon = float(p[4]), float(p[10]) * 1000, float(p[13]) * 1000, float(p[24]), float(p[25])
        if span >= MIN_SPAN_YEARS and su < MAX_SIGMA_MM:
            out.append((p[0], lat, lon - 360 if lon > 180 else lon, -vu))
    return out


def _run_region(region):
    def run(session: Session) -> ValidationResult:
        if not MIDAS.exists():
            return ValidationResult(hazard_type="subsidence", kind="rank", predicted=[], observed=[], labels=[],
                                    target_source="NGL MIDAS GNSS vertical velocities", scope=region or "global", method="out_of_sample",
                                    notes=f"target file {MIDAS} not present — run scripts/fetch_ngl_velocities.py")
        from ml.scoring.subsidence_point import _RASTER_PATH, CLASS_SCORE
        from services.geo.raster_sampler import info, sample
        st = _stations()
        la = np.array([s[1] for s in st]); lo = np.array([s[2] for s in st])
        keep = REGIONS[region](la, lo)
        meta = info(_RASTER_PATH); left, bottom, right, top = meta["bounds"]
        keep &= (lo >= left) & (lo <= right) & (la >= bottom) & (la <= top)
        st = [s for s, k in zip(st, keep) if k]
        pred, obs, labels = [], [], []
        pts = [(s[2], s[1]) for s in st]
        for i in range(0, len(pts), 2000):
            for s, g in zip(st[i:i + 2000], sample(_RASTER_PATH, pts[i:i + 2000]) or []):
                cls = int(g[0]) if g else 0
                if 1 <= cls <= 6:
                    pred.append(CLASS_SCORE[cls]); obs.append(s[3]); labels.append(s[0])
        return ValidationResult(hazard_type="subsidence", kind="rank", predicted=pred, observed=obs, labels=labels,
                                target_source="NGL MIDAS GNSS station vertical velocities (IGS14), observed subsidence rate mm/yr",
                                scope=region or "global excl. glacial rebound", method="out_of_sample",
                                data_vintage=f"{len(pred)} stations, ≥{MIN_SPAN_YEARS:.0f} y span, σ < {MAX_SIGMA_MM:.0f} mm/yr",
                                notes=("GSS susceptibility class (scored 5…95) vs observed −vertical velocity at the station; GNSS mounts favour "
                                       "stable ground, so the target under-samples subsiding sediments (InSAR/EGMS is the better target, licence-gated)"))
    return run


for _r in REGIONS:
    register(f"subsidence_gnss{'_' + _r.lower() if _r else ''}")(_run_region(_r))

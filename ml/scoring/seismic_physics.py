"""
Physics-based seismic scoring — replaces the degenerate ML risk/ETAS models.

The shipped ML models were circular: the risk "target" was a linear formula of the
input features (magnitude·10 + pga·20 + …), trained with pga/population/building held
constant, so the model collapsed to magnitude-only and produced a uniform blanket.
There are also no real damage labels (damage_assessments is empty). ML is the wrong
tool here. Seismic hazard is established physics:

1. Intensity from an Intensity Prediction Equation (IPE) — shaking decays with
   distance, so risk VARIES spatially (the whole point the blanket missed). We use
   the Bakun & Wentworth (1997) form on HYPOCENTRAL distance, so depth matters too
   (a deep M7 is felt far less at the surface than a shallow one).
2. Aftershocks from the Omori-Utsu law with Reasenberg-Jones (1989/94) generic
   parameters — a real statistical-seismology forecast of a damaging aftershock.

This is a transparent, defensible baseline. Production would swap in region-specific
GMPEs with Vs30 site amplification and sequence-calibrated aftershock parameters.
"""
from __future__ import annotations

import numpy as np

# --- Intensity Prediction Equation (Bakun & Wentworth 1997, generic) ---
# MMI = c1 + c2*M + c3*log10(D_hypocentral_km)
_C1, _C2, _C3 = 3.67, 1.17, -3.19
_MIN_D = 4.0  # km, avoids singularity at the epicentre


def ipe_mmi(magnitude: float, epicentral_km, depth_km: float = 10.0):
    """Modified Mercalli Intensity (I–X) at a site, from magnitude + distance + depth."""
    d = np.sqrt(np.asarray(epicentral_km, dtype=float) ** 2 + float(depth_km) ** 2)
    d = np.maximum(d, _MIN_D)
    mmi = _C1 + _C2 * float(magnitude) + _C3 * np.log10(d)
    return np.clip(mmi, 1.0, 10.0)


def mmi_to_risk(mmi):
    """MMI (1–10) → 0–100 risk. Damage onset ~MMI VI; severe ~IX–X."""
    return np.clip(np.asarray(mmi, dtype=float) * 10.0, 0.0, 100.0)


# --- Aftershock forecast (Omori-Utsu + Reasenberg-Jones generic params) ---
_RJ_A, _RJ_B, _RJ_P, _RJ_C = -1.67, 0.91, 1.08, 0.05  # c in days


def aftershock_probability(mainshock_mag: float, t2_days: float,
                           t1_days: float = 0.0, mmin: float = 5.0) -> float:
    """Probability of >=1 aftershock of magnitude >= mmin in (t1, t2] days.

    Expected count N = 10^(a + b(Mm - mmin)) * integral_{t1}^{t2} (t + c)^(-p) dt,
    then Poisson P(>=1) = 1 - exp(-N).
    """
    if t2_days <= t1_days:
        return 0.0
    productivity = 10 ** (_RJ_A + _RJ_B * (float(mainshock_mag) - mmin))
    integ = ((t2_days + _RJ_C) ** (1 - _RJ_P) - (t1_days + _RJ_C) ** (1 - _RJ_P)) / (1 - _RJ_P)
    n_expected = productivity * max(integ, 0.0)
    return float(1.0 - np.exp(-n_expected))


def aftershock_forecast(mainshock_mag: float, mmin: float = 5.0) -> dict:
    """24h / 72h / 7d probabilities of a damaging (>= mmin) aftershock."""
    return {
        "aftershock_24h": round(aftershock_probability(mainshock_mag, 1.0, 0.0, mmin), 4),
        "aftershock_72h": round(aftershock_probability(mainshock_mag, 3.0, 0.0, mmin), 4),
        "aftershock_7d": round(aftershock_probability(mainshock_mag, 7.0, 0.0, mmin), 4),
    }

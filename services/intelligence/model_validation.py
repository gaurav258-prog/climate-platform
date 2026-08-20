"""Model validation — score vs observed-record consistency backtest.

The credibility layer model-validation teams and supervisors (EIOPA, ECB) ask for: don't just publish a score,
show it is consistent with what actually happened. This tests Tellumen's own hazard scores against the observed
event catalogues it holds, for the two perils with a real record (seismic, storm). For every scored cell it
counts the real events that occurred in the cell's NEAR FIELD, then asks: do higher-scored locations carry more
observed events?

It reports a per-band table (mean observed events + share with any event, by score band), a rank discrimination
metric (Spearman between score and observed event count), and a plain verdict. The near field — not the wide
felt radius used for asset-level exposure — is deliberate: at cell resolution a 150 km felt radius saturates
(nearly every cell has *some* event nearby) and measures nothing, whereas the near field separates the active
core from its surroundings and lets the score's ordering be tested.

Honest by construction, in two ways the note makes explicit:
  * This is an IN-SAMPLE CONSISTENCY check — a seismic score is built from the same USGS catalogue it is tested
    against, so a strong result confirms the score faithfully encodes the record (and would catch a broken score
    surface), but it is NOT out-of-sample prediction. A forward predictive backtest needs scores frozen before a
    held-out period; that is flagged as roadmap, not claimed here.
  * It reports weak results as weak. Where the score and the observed record diverge (as storm does), the verdict
    says so rather than dressing a null up as validation. Every cell and event is real; nothing is projected.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

# catalogued peril -> near-field radius (km) at which the score's ordering is testable without saturating,
# and a label. The near field ≈ the cell and its immediate surroundings, not the wide asset felt radius.
_PERILS = {
    "seismic": {"near_field_km": 25.0, "label": "Earthquake (USGS ≥ M5)"},
    "storm": {"near_field_km": 25.0, "label": "Storm (IBTrACS tracks)"},
}
_BANDS = [("VH", 75.0, 100.1), ("H", 50.0, 75.0), ("M", 25.0, 50.0), ("L", 0.0, 25.0)]
_CACHE: dict = {}


def _hav_vec(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    r = 6371.0
    p1, p2 = np.radians(lat), np.radians(lats)
    dp, dl = np.radians(lats - lat), np.radians(lons - lon)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def _event_counts(cell_lat: np.ndarray, cell_lon: np.ndarray, ev_lat: np.ndarray,
                  ev_lon: np.ndarray, radius_km: float) -> np.ndarray:
    """Observed event count in each cell's near field. Binned spatial join — events indexed into ~radius-sized
    lat/lon bins, each cell scans its bin and the eight neighbours."""
    binsize = max(radius_km / 111.0, 1e-6)
    grid: dict = {}
    for i in range(len(ev_lat)):
        grid.setdefault((int(ev_lat[i] // binsize), int(ev_lon[i] // binsize)), []).append(i)
    counts = np.zeros(len(cell_lat))
    for ci in range(len(cell_lat)):
        la, lo = cell_lat[ci], cell_lon[ci]
        bx, by = int(la // binsize), int(lo // binsize)
        cand: list[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cand.extend(grid.get((bx + dx, by + dy), ()))
        if cand:
            idx = np.asarray(cand)
            counts[ci] = int((_hav_vec(la, lo, ev_lat[idx], ev_lon[idx]) <= radius_km).sum())
    return counts


def _rank(x: np.ndarray) -> np.ndarray:
    """Average-tied ranks."""
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), dtype=float)
    ranks[order] = np.arange(1, len(x) + 1)
    xs = x[order]
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return ranks


def _spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return None
    ra, rb = _rank(a), _rank(b)
    return float(np.corrcoef(ra, rb)[0, 1])


def _auc(scores: np.ndarray, pos: np.ndarray) -> float | None:
    n_pos = int(pos.sum()); n_neg = len(scores) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = _rank(scores)
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _load_cells(session: Session, peril: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows = session.execute(text("""
        SELECT h3_cell, CAST(risk_score AS FLOAT) AS score FROM canonical_scores
        WHERE hazard_type = :h AND valid_to IS NULL AND scenario = 'baseline' AND time_horizon = 'current'
    """), {"h": peril}).all()
    import h3
    lat = np.empty(len(rows)); lon = np.empty(len(rows)); score = np.empty(len(rows))
    for i, (cell, sc) in enumerate(rows):
        la, lo = h3.cell_to_latlng(cell)
        lat[i], lon[i], score[i] = la, lo, sc
    return lat, lon, score


def _load_events(session: Session, peril: str) -> tuple[np.ndarray, np.ndarray, int]:
    if peril == "seismic":
        rows = session.execute(text("SELECT CAST(epicentre_lat AS FLOAT), CAST(epicentre_lon AS FLOAT) "
                                    "FROM seismic_events WHERE CAST(magnitude AS FLOAT) >= 5")).all()
        span = session.execute(text("SELECT MIN(EXTRACT(YEAR FROM origin_time))::int, "
                                    "MAX(EXTRACT(YEAR FROM origin_time))::int FROM seismic_events "
                                    "WHERE CAST(magnitude AS FLOAT) >= 5")).first()
    else:
        rows = session.execute(text("SELECT CAST(lat AS FLOAT), CAST(lon AS FLOAT) FROM storm_events")).all()
        span = session.execute(text("SELECT MIN(season_year), MAX(season_year) FROM storm_events")).first()
    if not rows:
        return np.array([]), np.array([]), 0
    lat = np.array([r[0] for r in rows]); lon = np.array([r[1] for r in rows])
    window = (span[1] - span[0] + 1) if span and span[0] and span[1] else 0
    return lat, lon, window


def model_validation(session: Session, peril: str) -> dict:
    """Score vs observed-record consistency backtest for one catalogued peril. Cached (static inputs)."""
    if peril not in _PERILS:
        return {"available": False, "reason": "peril_not_catalogued"}
    if peril in _CACHE:
        return _CACHE[peril]

    radius = _PERILS[peril]["near_field_km"]
    cell_lat, cell_lon, score = _load_cells(session, peril)
    ev_lat, ev_lon, window = _load_events(session, peril)
    if len(cell_lat) == 0 or len(ev_lat) == 0:
        return {"available": False, "reason": "no_data"}

    counts = _event_counts(cell_lat, cell_lon, ev_lat, ev_lon, radius)
    has_event = counts > 0
    n_cells = len(cell_lat)

    bands = []
    for name, lo, hi in _BANDS:
        m = (score >= lo) & (score < hi)
        nb = int(m.sum())
        bands.append({"band": name, "n_cells": nb,
                      "mean_events": round(float(counts[m].mean()), 2) if nb else None,
                      "pct_with_event": round(100.0 * float(has_event[m].mean()), 1) if nb else None})

    spearman = _spearman(score, counts)
    auc = _auc(score, has_event)
    means = [b["mean_events"] for b in bands if b["mean_events"] is not None]
    monotonic = all(means[i] >= means[i + 1] for i in range(len(means) - 1)) if len(means) > 1 else None

    strength = ("strong" if spearman is not None and spearman >= 0.5
                else "moderate" if spearman is not None and spearman >= 0.3
                else "weak")
    passed = strength in ("strong", "moderate") and bool(monotonic)
    verdict = (f"{strength.title()} consistency — Spearman {spearman:.2f} between score and observed near-field "
               f"event count; mean observed events {'do' if monotonic else 'do NOT'} rise monotonically with the "
               f"score band." if spearman is not None else "Insufficient spread to test.")

    result = {
        "available": True,
        "peril": peril,
        "label": _PERILS[peril]["label"],
        "near_field_km": round(radius),
        "n_cells_scored": n_cells,
        "n_events_observed": len(ev_lat),
        "observed_window_years": window,
        "pct_cells_with_event": round(100.0 * float(has_event.mean()), 1),
        "spearman": round(spearman, 3) if spearman is not None else None,
        "auc": round(auc, 3) if auc is not None else None,
        "monotonic": monotonic,
        "passed": passed,
        "bands": bands,
        "verdict": verdict,
        "note": ("A consistency backtest: every scored cell is matched against the real event catalogue "
                 f"({_PERILS[peril]['label']}) in its near field ({round(radius)} km — deliberately tighter than "
                 "the asset felt radius, which saturates at cell resolution). Spearman measures whether higher "
                 "scores carry more observed events. This is an IN-SAMPLE check — a catalogue-derived score is "
                 "tested against the record it is built from — so it validates FAITHFULNESS (does the score "
                 "encode the record, and would a broken surface be caught), not out-of-sample prediction. A "
                 "forward predictive backtest requires scores frozen before a held-out period (roadmap). Weak "
                 "results are reported as weak; every cell and event is real, nothing projected."),
    }
    _CACHE[peril] = result
    return result


def model_validation_all(session: Session) -> dict:
    """Both catalogued perils, for the validation dashboard."""
    return {"perils": [model_validation(session, p) for p in _PERILS]}

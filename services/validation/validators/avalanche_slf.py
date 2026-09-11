"""Avalanche validator — the terrain × snow-climate screening proxy (ml/scoring/avalanche_point.py) against
avalanche accidents the WSL Institute for Snow and Avalanche Research SLF actually recorded in Switzerland.

Target: "Avalanche accidents in Switzerland since 1970/71" (SLF, EnviDat DOI 10.16904/envidat.411, WSL Data
Policy / SLF Terms of Use) — every known avalanche with at least one person caught, with a WGS84 start-zone
point. Landed by scripts/fetch_slf_avalanches.py to data/avalanche_val/slf_accidents.csv; absent → INSUFFICIENT.

Design (kind 'discrimination', Swiss Alps only):
  event cells      H3 res-8 cells inside the Swiss-Alps box with ≥1 recorded accident start zone,
  background cells a FIXED random sample of cells inside the same box (seed 7) with no recorded accident,
  predicted        the platform's avalanche score at the cell centre — read from canonical_scores when the cell
                   is already scored, otherwise scored on demand with the point scorer (counted and reported).
Only the accident LOCATION is used as truth; the SLF's own slope/elevation columns are never fed to the model.
`extra` carries a rank variant (score vs accident count per cell) and an alpine-only AUC (cells ≥ 1500 m) so the
easy lowland-vs-mountain separation is not the only number.
"""
from __future__ import annotations

import csv
import io
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.validation import metrics as M
from services.validation.engine import ValidationResult, register

TARGET_CSV = Path("data/avalanche_val/slf_accidents.csv")
TARGET = "SLF avalanche accidents in Switzerland since 1970/71 (start-zone points)"
SOURCE_DOI = "10.16904/envidat.411"
# Swiss Alps box: south of the Plateau's northern cities, Lake Geneva to the Engadine/Grisons.
ALPS_BBOX = (45.82, 6.80, 46.95, 10.50)      # (lat_min, lon_min, lat_max, lon_max)
H3_RES = 8
SEED = 7
MAX_EVENT_CELLS = 600        # cells scored on demand cost one DEM call each; a fixed sample keeps the run bounded
N_BACKGROUND = 600
ALPINE_ELEV_M = 1500.0
_PAUSE_S = 0.12              # Open-Meteo courtesy pacing for on-demand DEM calls
_WORKERS = 4                 # concurrent on-demand DEM calls (8 made the public endpoint drop ~40%)


# ── pure parsing (shared with the fetch script and the unit tests) ────────────────────────────────
def unwrap_line(line: str) -> str:
    """The SLF export wraps some whole rows in quotes with doubled inner quotes; undo that."""
    s = line.rstrip("\r\n")
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"' and '""' in s:
        return s[1:-1].replace('""', '"')
    return s


def parse_slf_csv(raw: str) -> list[dict]:
    """Rows with a usable WGS84 start-zone point from the raw SLF export (3 banner lines + header + rows)."""
    lines = [unwrap_line(ln) for ln in raw.splitlines() if ln.strip()]
    start = next((i for i, ln in enumerate(lines) if ln.startswith("avalanche.id,")), None)
    if start is None:
        return []
    rdr = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    out = []
    for r in rdr:
        try:
            lat = float(r["start.zone.coordinates.latitude"]); lon = float(r["start.zone.coordinates.longitude"])
        except (TypeError, ValueError, KeyError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        out.append({"avalanche_id": r["avalanche.id"], "date": r["date"], "canton": r.get("canton", ""),
                    "lat": lat, "lon": lon, "n_dead": _int(r.get("number.dead")), "n_caught": _int(r.get("number.caught"))})
    return out


def _int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def in_bbox(lat: float, lon: float, bbox=ALPS_BBOX) -> bool:
    return bbox[0] <= lat <= bbox[2] and bbox[1] <= lon <= bbox[3]


def event_counts(rows: list[dict], bbox=ALPS_BBOX) -> dict[str, int]:
    """Accidents per H3 res-8 cell inside the box."""
    counts: dict[str, int] = {}
    for r in rows:
        if in_bbox(r["lat"], r["lon"], bbox):
            c = h3.latlng_to_cell(r["lat"], r["lon"], H3_RES)
            counts[c] = counts.get(c, 0) + 1
    return counts


def sample_background(exclude: set[str], n: int, seed: int = SEED, bbox=ALPS_BBOX) -> list[str]:
    """A fixed (seeded) random sample of n distinct cells in the box that carry no recorded accident."""
    rng = random.Random(seed)
    out: list[str] = []
    seen: set[str] = set()
    while len(out) < n:
        c = h3.latlng_to_cell(rng.uniform(bbox[0], bbox[2]), rng.uniform(bbox[1], bbox[3]), H3_RES)
        if c in exclude or c in seen:
            continue
        seen.add(c); out.append(c)
    return out


def choose_event_cells(counts: dict[str, int], max_n: int = MAX_EVENT_CELLS, seed: int = SEED) -> list[str]:
    cells = sorted(counts)
    if len(cells) <= max_n:
        return cells
    return sorted(random.Random(seed).sample(cells, max_n))


# ── scoring ──────────────────────────────────────────────────────────────────────────────────────
def _platform_scores(session: Session, cells: list[str]) -> dict[str, float]:
    if not cells:
        return {}
    rows = session.execute(text("""
        SELECT h3_cell, CAST(risk_score AS FLOAT) rs FROM canonical_scores
        WHERE hazard_type='avalanche' AND scenario='baseline' AND time_horizon='current' AND valid_to IS NULL
          AND h3_cell = ANY(:cells)
    """), {"cells": cells}).all()
    return {c: float(rs) for c, rs in rows}


def _elevations(session: Session, cells: list[str]) -> dict[str, float]:
    if not cells:
        return {}
    rows = session.execute(text("SELECT h3_cell, elevation_m FROM terrain_cell WHERE h3_cell = ANY(:cells)"),
                           {"cells": cells}).all()
    return {c: float(e) for c, e in rows if e is not None}


def _score_cells(session: Session, cells: list[str]) -> tuple[dict[str, float], int, int]:
    """(score per cell, n scored on demand, n without DEM coverage). Cells the DEM cannot cover are absent."""
    from ml.scoring.avalanche_point import score_avalanche_point
    scores = _platform_scores(session, cells)
    todo = [c for c in cells if c not in scores]
    n_demand = n_nodem = 0

    def one(c: str):
        r = score_avalanche_point(*h3.cell_to_latlng(c))
        time.sleep(_PAUSE_S)
        return c, r

    # each on-demand cell is one batched DEM call (~3 s at the public endpoint); a small pool keeps a 1,200-cell
    # run to minutes while staying far below the endpoint's per-minute allowance
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        for c, r in pool.map(one, todo):
            if r["status"] == "insufficient_data":
                n_nodem += 1
                continue
            scores[c] = float(r["risk_score"])
            if r["status"] != "cached_hit":
                n_demand += 1
    return scores, n_demand, n_nodem


def _run(session: Session) -> ValidationResult:
    if not TARGET_CSV.exists():
        return ValidationResult(hazard_type="avalanche", kind="discrimination", predicted=[], observed=[], labels=[],
                                target_source=TARGET, scope="Swiss Alps", method="out_of_sample",
                                notes=f"target file {TARGET_CSV} not present — run scripts/fetch_slf_avalanches.py")
    rows = list(csv.DictReader(TARGET_CSV.open()))
    for r in rows:
        r["lat"] = float(r["lat"]); r["lon"] = float(r["lon"])
    counts = event_counts(rows)
    ev_cells = choose_event_cells(counts)
    bg_cells = sample_background(set(counts), N_BACKGROUND)
    scores, n_demand, n_nodem = _score_cells(session, ev_cells + bg_cells)
    elev = _elevations(session, ev_cells + bg_cells)

    pred, obs, labels = [], [], []
    for c in ev_cells + bg_cells:
        if c not in scores:
            continue
        pred.append(scores[c]); obs.append(float(counts.get(c, 0))); labels.append(c)
    n_ev = sum(1 for o in obs if o > 0)
    n_bg = len(obs) - n_ev

    # extras: rank vs accident COUNT (all cells, and among event cells only) + the harder alpine-only AUC
    ev_only = [(p, o) for p, o in zip(pred, obs) if o > 0]
    alp = [(p, o) for p, o, c in zip(pred, obs, labels) if elev.get(c, -1.0) >= ALPINE_ELEV_M]
    extra = {
        "n_accidents_in_box": int(sum(counts.values())), "n_event_cells_total": len(counts),
        "n_event_cells_used": n_ev, "n_background_cells_used": n_bg,
        "n_scored_on_demand": n_demand, "n_no_dem_coverage": n_nodem,
        "rank_spearman_vs_count_all_cells": _r(M.spearman([p for p, _ in zip(pred, obs)], obs)),
        "rank_spearman_vs_count_event_cells": _r(M.spearman([p for p, _ in ev_only], [o for _, o in ev_only])) if len(ev_only) >= M.MIN_N else None,
        "alpine_only_n": len(alp),
        "alpine_only_event_prevalence": _r(M.event_prevalence([o for _, o in alp])) if alp else None,
        "alpine_only_auc": _r(M.auc([p for p, _ in alp], [o > 0 for _, o in alp])) if alp else None,
        "alpine_only_spearman": _r(M.spearman([p for p, _ in alp], [o for _, o in alp])) if len(alp) >= M.MIN_N else None,
    }
    return ValidationResult(
        hazard_type="avalanche", kind="discrimination", predicted=pred, observed=obs, labels=labels,
        target_source=f"{TARGET}, EnviDat DOI {SOURCE_DOI}", scope="Swiss Alps", method="out_of_sample",
        data_vintage=f"SLF 1970/71–2023/24 (EnviDat 2025-02-10), {len(rows)} accidents",   # ≤60 chars
        extra=extra,
        notes=(f"event cells = H3 r8 cells in the Swiss-Alps box {ALPS_BBOX} with ≥1 SLF accident start zone "
               f"({n_ev} of {len(counts)} used, seed {SEED} sample cap {MAX_EVENT_CELLS}); background = {n_bg} seeded "
               f"random cells with none; predicted = platform avalanche score at the cell centre "
               f"({n_demand} cells scored on demand via the point scorer, {n_nodem} without DEM coverage dropped). "
               f"Observed = accidents per cell; only the location is used, never the SLF slope/elevation columns. "
               f"Reporting bias: the register holds accidents with people caught, so it favours toured/inhabited terrain."),
    )


def _r(v):
    return round(v, 4) if isinstance(v, float) else v


register("avalanche_slf")(_run)

"""Model validation — each hazard score tested against what was observed.

The credibility layer model-validation teams and supervisors (EIOPA, ECB) ask for: don't just publish a score, show
it holds up against what actually happened. Three parts, all read from the data; the screen gets numbers, names and
message codes (core/messages.py), never sentences written here (UI standard, 2026-10-16):

  record check   for the two hazards whose observed event catalogue is held (earthquakes, tropical cyclones): do
                 places scored higher carry more observed events within the hazard's near field? A per-band table
                 (mean observed events, share with any event), the rank agreement between score and event count, and
                 a verdict code. The near field — not the wide felt radius used for asset-level exposure — is
                 deliberate: at cell resolution a 150 km felt radius saturates (nearly every cell has *some* event
                 nearby) and measures nothing. An event is counted once per place: an earthquake once, a cyclone
                 once however many of its track positions fall in the near field. This is an IN-SAMPLE
                 CONSISTENCY check — a seismic score is built from the same catalogue it is tested against — so it
                 confirms the score faithfully encodes the record, not that it predicts.
  harvest test   each crop's hazard score regressed on decades of observed yield, out-of-sample; a crop euro is
                 published only where the share explained clears the fixed 0.40 bar. Yield is not an input to the
                 score, so this is out-of-sample skill.
  coverage       every hazard on the register (core/hazard_taxonomy.py, the one source of each hazard's tier) with
                 the tests the validation ledger (validation_run) holds for it, by test design. Counts are read from
                 the ledger, never typed here.

Weak results are reported as weak. Every cell and event is real; nothing is projected.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from core import messages
from core import validation_gates as G
from core.hazard_taxonomy import EU_TAXONOMY, EXTRA_CHANNELS, EUHazard, MaturityTier
from ml.validation.fidelity import fidelity

# catalogued peril -> near-field radius (km) at which the score's ordering is testable without saturating. The radius
# is PERIL-SPECIFIC — it must match the hazard's physical footprint, or the test measures the wrong thing. A quake is
# a point source (~25 km near field); a cyclone is a wide wind-field system (~150 km).
_PERILS = {"seismic": 25.0, "storm": 150.0}
_BANDS = [("VH", 75.0, 100.1), ("H", 50.0, 75.0), ("M", 25.0, 50.0), ("L", 0.0, 25.0)]
_CACHE: dict = {}


def _hav_vec(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    r = 6371.0
    p1, p2 = np.radians(lat), np.radians(lats)
    dp, dl = np.radians(lats - lat), np.radians(lons - lon)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def _event_counts(cell_lat: np.ndarray, cell_lon: np.ndarray, ev_lat: np.ndarray, ev_lon: np.ndarray,
                  ev_id: np.ndarray, radius_km: float) -> np.ndarray:
    """The number of distinct observed events in each cell's near field. ev_id names the event each observation
    belongs to (one id per earthquake; one per cyclone, shared by all its track positions), so an event counts once.
    Binned spatial join — observations indexed into ~radius-sized lat/lon bins, each cell scans its bin and the
    eight neighbours."""
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
            near = idx[_hav_vec(la, lo, ev_lat[idx], ev_lon[idx]) <= radius_km]
            counts[ci] = np.unique(ev_id[near]).size
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


def _load_cells(session: Session, peril: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, list]:
    rows = session.execute(text("""
        SELECT h3_cell, CAST(risk_score AS FLOAT) AS score FROM canonical_scores
        WHERE hazard_type = :h AND valid_to IS NULL AND scenario = 'baseline' AND time_horizon = 'current'
    """), {"h": peril}).all()
    import h3
    lat = np.empty(len(rows)); lon = np.empty(len(rows)); score = np.empty(len(rows))
    cells = []
    for i, (cell, sc) in enumerate(rows):
        la, lo = h3.cell_to_latlng(cell)
        lat[i], lon[i], score[i] = la, lo, sc
        cells.append(cell)
    return lat, lon, score, cells


def _load_events(session: Session, peril: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, Optional[int], Optional[int]]:
    """Observation coordinates, the event each belongs to, and the first and last year of the record."""
    if peril == "seismic":
        rows = session.execute(text("SELECT CAST(epicentre_lat AS FLOAT), CAST(epicentre_lon AS FLOAT), event_id::text, "
                                    "EXTRACT(YEAR FROM origin_time)::int FROM seismic_events "
                                    "WHERE CAST(magnitude AS FLOAT) >= 5")).all()
    else:
        rows = session.execute(text("SELECT CAST(lat AS FLOAT), CAST(lon AS FLOAT), storm_id, season_year "
                                    "FROM storm_events")).all()
    if not rows:
        return np.array([]), np.array([]), np.array([]), None, None
    lat = np.array([r[0] for r in rows]); lon = np.array([r[1] for r in rows])
    _, ev_id = np.unique([str(r[2]) for r in rows], return_inverse=True)
    years = [r[3] for r in rows if r[3] is not None]
    return lat, lon, ev_id, (min(years) if years else None), (max(years) if years else None)


def _verdict(spearman: Optional[float], monotonic: Optional[bool], passed: bool, peril: str) -> dict:
    events = messages.name("peril", peril) + "s"
    if spearman is None:
        return messages.render("validation.record.no_spread", events=events)
    code = ("validation.record.consistent" if passed
            else "validation.record.not_rising" if spearman >= G.RANK_GATE_SPEARMAN and not monotonic
            else "validation.record.weak")
    return messages.render(code, events=events, rho=f"{spearman:.2f}", floor=f"{G.RANK_GATE_SPEARMAN:.2f}")


def model_validation(session: Session, peril: str) -> dict:
    """Score vs observed-record consistency backtest for one catalogued peril. Cached (static inputs)."""
    if peril not in _PERILS:
        return {"available": False, "peril": peril, "message": messages.render("validation.record.no_catalogue")}
    if peril in _CACHE:
        return _CACHE[peril]

    radius = _PERILS[peril]
    cell_lat, cell_lon, score, cells = _load_cells(session, peril)
    ev_lat, ev_lon, ev_id, first, last = _load_events(session, peril)
    if len(cell_lat) == 0 or len(ev_lat) == 0:
        return {"available": False, "peril": peril, "message": messages.render("validation.record.no_data")}

    counts = _event_counts(cell_lat, cell_lon, ev_lat, ev_lon, ev_id, radius)
    has_event = counts > 0

    def _sample(idxs: np.ndarray, k: int = 6) -> list[dict]:
        # representative cells for a band's drill-down: the most-active first, then a couple of quiet ones so
        # the honest misses (high score, no observed event) are visible too. Deterministic (sorted, no rng).
        order = idxs[np.argsort(-counts[idxs], kind="mergesort")]
        pick = list(order[:k])
        quiet = [i for i in order[::-1] if counts[i] == 0][:2]
        for q in quiet:
            if q not in pick:
                pick.append(q)
        return [{"h3_cell": cells[i], "lat": round(float(cell_lat[i]), 4), "lon": round(float(cell_lon[i]), 4),
                 "score": round(float(score[i]), 1), "observed_events": int(counts[i])} for i in pick]

    bands = []
    for name, lo, hi in _BANDS:
        m = (score >= lo) & (score < hi)
        idxs = np.where(m)[0]
        nb = int(m.sum())
        bands.append({"band": name, "n_cells": nb,
                      "mean_events": round(float(counts[m].mean()), 2) if nb else None,
                      "pct_with_event": round(100.0 * float(has_event[m].mean()), 1) if nb else None,
                      "samples": _sample(idxs) if nb else []})

    spearman = _spearman(score, counts)
    # AUC ("was it hit at all") only discriminates when coverage is not saturated. For a frequent, wide peril
    # (cyclone at its 150 km scale hits ~every cell) it saturates to ~1.0 and is MISLEADING — it would look better
    # than a sparse peril it is actually weaker than. Withheld there; the count rank agreement is the honest metric.
    saturated = float(has_event.mean()) > 0.9
    auc = None if saturated else _auc(score, has_event)
    means = [b["mean_events"] for b in bands if b["mean_events"] is not None]
    monotonic = all(means[i] >= means[i + 1] for i in range(len(means) - 1)) if len(means) > 1 else None
    strength = ("strong" if spearman is not None and spearman >= G.STRONG_SPEARMAN
                else "moderate" if spearman is not None and spearman >= G.RANK_GATE_SPEARMAN
                else "weak")
    passed = strength in ("strong", "moderate") and bool(monotonic)

    result = {
        "available": True,
        "peril": peril,
        "name": messages.name("peril", peril),
        "source": messages.name("event_record", peril),
        "near_field_km": round(radius),
        "n_cells_scored": len(cell_lat),
        "n_events_observed": int(len(np.unique(ev_id))),
        "first_year": first, "last_year": last,
        "observed_window_years": (last - first + 1) if first and last else None,
        "pct_cells_with_event": round(100.0 * float(has_event.mean()), 1),
        "spearman": round(spearman, 3) if spearman is not None else None,
        "auc": round(auc, 3) if auc is not None else None,
        "auc_withheld": saturated,
        "monotonic": monotonic,
        "passed": passed,
        "gate_spearman": G.RANK_GATE_SPEARMAN,
        "fidelity": fidelity("discrimination", spearman=spearman, auc=auc),
        "bands": bands,
        "message": _verdict(spearman, monotonic, passed, peril),
    }
    _CACHE[peril] = result
    return result


def _origin_names(session: Session, iso2: set[str]) -> dict[str, str]:
    if not iso2:
        return {}
    return {r[0].strip(): r[1] for r in session.execute(
        text("SELECT iso2, name_en FROM ref_countries WHERE iso2 = ANY(:c)"), {"c": sorted(iso2)}).all()}


def crop_impact_validation(session: Session) -> dict:
    """The ECONOMIC-impact validation — the stronger test where we hold real impact data. Each hazard score is
    regressed on decades of observed crop yield (out-of-sample cross-validated share explained), and separately
    checked against named production-shock events. Yield/production is NOT an input to the score, so unlike the
    record check this is genuinely out-of-sample skill. Fits below the 0.40 bar are shown as held, never published
    as a euro."""
    from services.ingestion.regions import REGIONS
    rows = session.execute(text("""
        SELECT f.region_key, f.origin, f.hazard_driver, c.name AS crop, CAST(f.r2 AS FLOAT) AS r2,
               CAST(f.r2_oos AS FLOAT) AS r2_oos, f.n_years
        FROM sc_commodity_fit f LEFT JOIN sc_commodities c ON c.commodity_id = f.commodity_id
        WHERE f.r2_oos IS NOT NULL
    """)).mappings().all()
    # keep the best fit per (region, hazard driver) so the table reads one row per crop-region
    best: dict = {}
    for r in rows:
        k = (r["region_key"], r["hazard_driver"])
        if k not in best or r["r2_oos"] > best[k]["r2_oos"]:
            best[k] = r

    # The independent challenger's OUT-OF-SAMPLE second opinion, per crop — from the audit ledger.
    from services.intelligence.supply_cogs import load_oos_challengers
    oos_chal = load_oos_challengers(session)
    countries = _origin_names(session, {r["origin"] for r in best.values() if r["origin"]})

    fits = []
    for r in sorted(best.values(), key=lambda x: -x["r2_oos"]):
        oc = oos_chal.get((r["crop"], r["origin"], r["hazard_driver"]))
        challenger = None
        if oc is not None:
            challenger = {
                "challenger_r2_oos": (round(oc["challenger_r2_oos"], 3)
                                      if oc["challenger_r2_oos"] is not None else None),
                "verdict": oc["verdict"], "corroborates_publish": oc["corroborates_publish"],
            }
        region = REGIONS.get(r["region_key"])
        fits.append({"region": r["region_key"], "region_name": region.label if region else None,
                     "origin": r["origin"], "origin_name": countries.get(r["origin"]),
                     "crop": r["crop"], "hazard_driver": r["hazard_driver"],
                     "r2": round(r["r2"], 3) if r["r2"] is not None else None,
                     "r2_oos": round(r["r2_oos"], 3), "n_years": int(r["n_years"]) if r["n_years"] else None,
                     "passed": r["r2_oos"] >= G.REGRESSION_GATE_R2,
                     "fidelity": fidelity("regression", r2_oos=r["r2_oos"]),
                     "challenger": challenger})

    by_hazard: dict[str, dict] = {}
    for f in fits:
        h = by_hazard.setdefault(f["hazard_driver"], {"hazard": f["hazard_driver"], "fits": 0, "passed": 0})
        h["fits"] += 1
        h["passed"] += int(f["passed"])
    years = [f["n_years"] for f in fits if f["n_years"]]

    ev = session.execute(text("""
        SELECT event, commodity, hazard, CAST(observed_prod_shock_pct AS FLOAT) AS observed_shock_pct,
               CAST(model_prod_shock_pct AS FLOAT) AS model_shock_pct, CAST(tolerance_pct AS FLOAT) AS tolerance_pct,
               passed FROM sc_model_validation ORDER BY passed DESC, hazard
    """)).mappings().all()
    events, seen = [], set()
    for e in ev:
        key = (e["event"], e["hazard"])
        if key in seen:
            continue
        seen.add(key)
        events.append(dict(e))

    return {
        "available": bool(fits),
        "gate_r2_oos": G.REGRESSION_GATE_R2,
        "n_fits": len(fits),
        "n_pass": sum(1 for f in fits if f["passed"]),
        "years_min": min(years) if years else None,
        "years_max": max(years) if years else None,
        "by_hazard": sorted(by_hazard.values(), key=lambda h: (-h["passed"], -h["fits"])),
        "fits": fits,
        "events": events,
    }


# ── coverage: the register's tier for every hazard, with the tests the validation ledger holds for it ─────────────
DESIGNS = ("same_record", "held_out", "independent", "harvests", "events")
_DESIGN_OF_METHOD = {"in_sample": "same_record", "temporal_holdout": "held_out", "out_of_sample": "independent",
                     "event_reproduction": "events"}
_HARVEST = ("crop_", "agri_")        # a ledger hazard key testing a score against observed crop yield
# ledger hazard keys that name a test target, not a hazard channel: the channel each one tests
_LEDGER_CHANNEL = {
    "crop_drought": "drought", "agri_spei": "drought", "drought_loss": "drought",
    "crop_heat": "heat_acute", "agri_temp": "heat_acute", "crop_soil_water": "soil_water",
    "flood_loss": "flood", "windstorm_loss": "windstorm", "severe_convective_loss": "severe_convective",
    "storm_parametric": "storm", "permafrost_thaw": "permafrost",
}
ALL_HAZARDS = frozenset({"agri_all"})   # one test of every crop hazard together — not one hazard's


def ledger_design(hazard_type: str, method: str) -> Optional[str]:
    """The test design a ledger run belongs to, or None when its method is not one of the five."""
    if method == "event_reproduction":
        return "events"
    if hazard_type.startswith(_HARVEST):
        return "harvests"
    return _DESIGN_OF_METHOD.get(method)


def hazard_for_channel(channel: str) -> Optional[EUHazard]:
    """The register row (core/hazard_taxonomy.py) a hazard channel serves, or None."""
    for h in (*EU_TAXONOMY, *EXTRA_CHANNELS):
        if any(c.value == channel for c in h.internal):
            return h
    return None


def ledger_hazard(hazard_type: str) -> Optional[EUHazard]:
    """The register row a ledger run tests, or None (a test of every hazard together, or an unknown key)."""
    if hazard_type in ALL_HAZARDS:
        return None
    return hazard_for_channel(_LEDGER_CHANNEL.get(hazard_type, hazard_type))


def validation_coverage(session: Session) -> dict:
    """Every hazard on the register with its tier, and the ledger's tests for it by design: runs, runs that clear
    the bar, distinct observed records, and the date of the last run. Read from validation_run in one pass."""
    groups = session.execute(text("""
        SELECT hazard_type, method, target_source, count(*) AS runs, count(*) FILTER (WHERE passed_gate) AS passed,
               min(created_at) AS first, max(created_at) AS last
        FROM validation_run GROUP BY hazard_type, method, target_source
    """)).mappings().all()
    cells: dict[tuple[str, str], dict] = {}
    totals = {"runs": 0, "passed": 0, "all_hazards_runs": 0, "unmapped_runs": 0, "first": None, "last": None}
    for g in groups:
        totals["runs"] += g["runs"]
        totals["passed"] += g["passed"]
        totals["first"] = g["first"] if totals["first"] is None else min(totals["first"], g["first"])
        totals["last"] = g["last"] if totals["last"] is None else max(totals["last"], g["last"])
        h, design = ledger_hazard(g["hazard_type"]), ledger_design(g["hazard_type"], g["method"])
        if g["hazard_type"] in ALL_HAZARDS:
            totals["all_hazards_runs"] += g["runs"]
            continue
        if h is None or design is None:
            totals["unmapped_runs"] += g["runs"]
            continue
        c = cells.setdefault((h.id, design), {"runs": 0, "passed": 0, "records": set(), "last": None})
        c["runs"] += g["runs"]
        c["passed"] += g["passed"]
        c["records"].add(g["target_source"])
        c["last"] = g["last"] if c["last"] is None else max(c["last"], g["last"])

    def _row(h: EUHazard, beyond_eu: bool) -> dict:
        tests = {d: {"runs": c["runs"], "passed": c["passed"], "records": len(c["records"]),
                     "last": c["last"].date().isoformat()}
                 for d in DESIGNS if (c := cells.get((h.id, d)))}
        tier = messages.render(f"coverage.tier.{h.tier.value}")     # the Coverage page's own tier words
        return {"id": h.id, "name": h.name, "family": h.family.value,
                "family_name": messages.name("coverage.family", "beyond" if beyond_eu else h.family.value),
                "tier": h.tier.value, "tier_name": tier["label"], "tier_message": tier,
                "beyond_eu": beyond_eu, "channels": [c.value for c in h.internal], "tests": tests}

    rows = [_row(h, False) for h in EU_TAXONOMY] + [_row(h, True) for h in EXTRA_CHANNELS]
    return {
        "designs": list(DESIGNS),
        "rows": rows,
        "summary": {
            "hazards": len(rows),
            "validated": sum(1 for h in (*EU_TAXONOMY, *EXTRA_CHANNELS) if h.tier is MaturityTier.CALIBRATED),
            "tested": sum(1 for r in rows if r["tests"]),
            "runs": totals["runs"], "passed": totals["passed"],
            "all_hazards_runs": totals["all_hazards_runs"], "unmapped_runs": totals["unmapped_runs"],
            "first": totals["first"].date().isoformat() if totals["first"] else None,
            "last": totals["last"].date().isoformat() if totals["last"] else None,
        },
    }


def model_validation_all(session: Session) -> dict:
    """Catalogued perils + economic-impact validation + every hazard's tier and ledger tests."""
    return {
        "perils": [model_validation(session, p) for p in _PERILS],
        "economic": crop_impact_validation(session),
        "coverage": validation_coverage(session),
    }

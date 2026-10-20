"""The European flood loss test — data/reference/loss_protocol.json 'europe_loss_test' (registered 2026-10-20 and
amended before the build; stated before any of it was built or run).

Do the flood losses the platform models for European regions rank like the river-flood losses those regions reported
(HANZE)? One NUTS-3 region is one sample.

  observed()           the reported river-flood loss rate: each selected event's loss split between the regions it
                       lists by their asset value in the river-flood zone that year, summed, ÷ 31 years ÷ the region's
                       mean zone asset value over 1990–2020
  profiles(codes)      one pass over the European maps: each region's zone (its cells flooded at the 1-in-100-year
                       period) and, per return period, how many zone cells are wet in each depth interval between the
                       curves' points with their summed depth; and the protection map's design periods over the zone
  modelled(p, curve)   the curve's expected annual damage fraction of the zone, undefended and defended — exact from
                       the interval sums, as the curve is a straight line inside each interval
  run(session)         every registered curve against the observed rates under the registered rule; each result
                       recorded in the validation ledger and on the curve

Raster reads go through the isolated sampler (E170); the pass over the maps runs offline
(scripts/run_europe_loss_test.py), never on the API thread.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np

from services.loss import curves, engine, protection, registry

log = logging.getLogger(__name__)

KEY = "europe_loss_test"
LAYER = "jrc_river_flood_europe"
FAMILY = "jrc_huizinga_2017"
HANZE = registry.ROOT / "data" / "datasets" / "hanze_v2"
OUTLINES = registry.ROOT / "data" / "datasets" / "hanze_v2_regions_v2010" / "Regions_v2010_simplified.zip"
OUT = registry.ROOT / "data" / "loss_val" / "europe_loss_test"
# The registered selection (loss_protocol.json 'europe_loss_test' → selection / observed), held here as values;
# tests/unit/test_europe_loss_test.py checks the registered text still states each one.
TYPES = ("River", "River/Coastal")
YEARS = (1990, 2020)
ASSETS = "Fixed assets (thsd. euro)"
PERCENTILE = 50
LOSS = "Losses (2020 euro)"
REGIONS = "Regions affected (v2010)"         # the region set the exposure uses (amended_before_run)
ZONE_RP = 100
TILE = 4096


def protocol() -> dict:
    return json.loads((registry.REF / "loss_protocol.json").read_text(encoding="utf-8"))[KEY]


# ── observed ────────────────────────────────────────────────────────────────────────────────────────────────
def _exposure():
    """(zone asset value in euro per NUTS code × timestep, the timesteps as years)."""
    import pandas as pd
    e = pd.read_csv(HANZE / "Exposure_river_hazard_zone.csv")
    e = e[(e["Variable"] == ASSETS) & (e["Percentile"] == PERCENTILE)].set_index("NUTS")
    steps = sorted(int(c) for c in e.columns if str(c).isdigit())
    return e[[str(s) for s in steps]].astype(float) * 1000.0, steps


def step_for(year: int, steps: list[int]) -> Optional[int]:
    """The exposure's timestep for the year, else the nearest earlier one; None before the first."""
    earlier = [s for s in steps if s <= year]
    return earlier[-1] if earlier else None


def country_of(code: str) -> Optional[str]:
    from services.reference.iso_country import to_iso2
    return to_iso2(code[:2])


def observed():
    """(one row per region in scope: observed_rate, reported_loss_eur, events, mean_zone_assets_eur, country;
    the selection's counts)."""
    import pandas as pd
    ev = pd.read_csv(HANZE / "HANZE_events.csv")
    sel = ev[ev["Type"].isin(TYPES) & ev["Year"].between(*YEARS) & ev[LOSS].notna()]
    A, steps = _exposure()
    period = [str(s) for s in steps if YEARS[0] <= s <= YEARS[1]]
    mean_assets = A[period].mean(axis=1)
    covered = registry.coverage_countries(LAYER)
    scope = mean_assets[(mean_assets > 0) & np.array([country_of(c) in covered for c in mean_assets.index])]
    loss, events = Counter(), Counter()
    unsplit, unknown = [], set()
    for r in sel.to_dict("records"):
        codes = [c.strip() for c in str(r[REGIONS] if r[REGIONS] == r[REGIONS] else "").split(";") if c.strip()]
        known = [c for c in codes if c in A.index]
        unknown |= set(codes) - set(known)
        w = A.loc[known, str(step_for(int(r["Year"]), steps))] if known else None
        if w is None or w.sum() <= 0:
            unsplit.append(int(r["ID"]))
            continue
        for c, share in (float(r[LOSS]) * w / w.sum()).items():
            loss[c] += share
            events[c] += 1
    years = YEARS[1] - YEARS[0] + 1
    out = pd.DataFrame({"country": [country_of(c) for c in scope.index], "mean_zone_assets_eur": scope.values,
                        "reported_loss_eur": [loss.get(c, 0.0) for c in scope.index],
                        "events": [events.get(c, 0) for c in scope.index]}, index=scope.index)
    out["observed_rate"] = out["reported_loss_eur"] / years / out["mean_zone_assets_eur"]
    return out, {"events_selected": int(len(sel)), "events_not_split": unsplit,
                 "codes_not_in_exposure": sorted(unknown), "regions_in_scope": int(len(out)),
                 "timesteps": [int(p) for p in period]}


def region_set_gaps(not_in_exposure: list[str], exposure: set[str], outlines: set[str]) -> list[str]:
    """Why the events, the exposure and the outlines do not use one region set — empty when they do (E301: the
    registration first named the v2021 regions, which the exposure does not use)."""
    out = []
    if not_in_exposure:
        out.append(f"{len(not_in_exposure)} regions the events list have no exposure (e.g. {not_in_exposure[:3]})")
    if exposure - outlines:
        out.append(f"{len(exposure - outlines)} exposure regions have no outline (e.g. {sorted(exposure - outlines)[:3]})")
    if outlines - exposure:
        out.append(f"{len(outlines - exposure)} outlines have no exposure (e.g. {sorted(outlines - exposure)[:3]})")
    return out


def check_region_sets(selection: dict) -> None:
    """Refuse the run unless the three files share one region set."""
    import geopandas as gpd
    A, _steps = _exposure()
    outlines = set(gpd.read_file(f"zip://{OUTLINES}", ignore_geometry=True)["Code"])
    gaps = region_set_gaps(selection["codes_not_in_exposure"], set(A.index), outlines)
    if gaps:
        raise RuntimeError("the region sets disagree: " + "; ".join(gaps))


# ── the maps ────────────────────────────────────────────────────────────────────────────────────────────────
def _paths() -> dict:
    L = registry.layer(LAYER)
    d = registry.ROOT / L["files"]["dir"]
    return {"rps": [int(rp) for rp in L["return_periods"]], "dry": float(L["dry_below"]),
            "zone": str(d / L["files"]["pattern"].format(rp=ZONE_RP)), "water": str(d / L["files"]["water"]),
            "stack": [str(d / L["files"]["pattern"].format(rp=rp)) for rp in L["return_periods"]]}


def valid_outline(geom):
    """The outline repaired (E302: most HANZE outlines have rings that touch or cross themselves — a side effect of
    their simplification, and clipping such a ring fails): shapely's make_valid, polygon parts only. The repair must
    cover the same area; a repair that does not is refused, never used."""
    import shapely
    from shapely.geometry import MultiPolygon, Polygon
    if geom.is_valid:
        return geom
    fixed = shapely.make_valid(geom)
    if not isinstance(fixed, (Polygon, MultiPolygon)):
        fixed = shapely.unary_union([p for p in getattr(fixed, "geoms", [fixed]) if isinstance(p, (Polygon, MultiPolygon))])
    if abs(fixed.area - geom.area) > 1e-9 * max(geom.area, 1e-12):
        raise ValueError(f"repairing the outline changed its area ({geom.area} → {fixed.area})")
    return fixed


def _regions(codes: list[str]):
    import geopandas as gpd
    g = gpd.read_file(f"zip://{OUTLINES}")
    g = g[g["Code"].isin(codes)].to_crs("EPSG:4326").reset_index(drop=True)
    g["geometry"] = [valid_outline(x) for x in g.geometry]
    return g


def profiles(codes: list[str], edges: list[float]) -> dict[str, dict]:
    """One pass over the maps, tile by tile: {code: {zone, counts[rp][interval], sums[rp][interval], lookup, off}}
    with lookup = [[design period, cells]] of the protection map over the zone. A failed read stops the run."""
    from shapely.geometry import box, mapping

    from services.geo import raster_sampler
    P = _paths()
    info = raster_sampler.info(P["zone"])
    if info is None:
        raise RuntimeError(f"cannot read {P['zone']}")
    a, _b, c, _d, e, f = info["transform"]
    g = _regions(codes)
    acc: dict[str, dict] = {}
    tiles = [(col, row) for row in range(0, info["height"], TILE) for col in range(0, info["width"], TILE)]
    for i, (col, row) in enumerate(tiles):
        w, h = min(TILE, info["width"] - col), min(TILE, info["height"] - row)
        tbox = box(c + col * a, f + (row + h) * e, c + (col + w) * a, f + row * e)
        hit = g.sindex.query(tbox, predicate="intersects")
        if not len(hit):
            continue
        shapes = []
        for j in hit:
            part = g.geometry.iloc[j].intersection(tbox)
            if not part.is_empty:
                shapes.append((mapping(part), int(j) + 1))
        got = raster_sampler.zone_bins(P["zone"], (col, row, w, h), shapes, P["stack"], edges, P["dry"],
                                       exclude={"path": P["water"], "value": 1}, lookup=protection._path())
        if got is None:
            raise RuntimeError(f"the read of tile ({col}, {row}) failed")
        for sid, s in got.items():
            code = g["Code"].iloc[int(sid) - 1]
            t = acc.setdefault(code, {"zone": 0, "counts": None, "sums": None, "lookup": Counter(), "off": 0})
            t["zone"] += s["zone"]
            t["off"] += s["off"]
            t["counts"] = np.add(t["counts"], s["counts"]) if t["counts"] is not None else np.asarray(s["counts"])
            t["sums"] = np.add(t["sums"], s["sums"]) if t["sums"] is not None else np.asarray(s["sums"], float)
            for v, n in s["lookup"]:
                t["lookup"][v] += n
        log.info("europe loss test: tile %d of %d (%d regions with a zone so far)", i + 1, len(tiles), len(acc))
    out = {k: {"zone": v["zone"], "counts": v["counts"].tolist(), "sums": v["sums"].tolist(),
               "lookup": sorted([[float(x), int(n)] for x, n in v["lookup"].items()]), "off": v["off"]}
           for k, v in acc.items()}
    return {**{k: {"zone": 0} for k in g["Code"]}, **out}      # a region with a polygon but no zone cell holds 0


# ── modelled ────────────────────────────────────────────────────────────────────────────────────────────────
def edges_for(tested: list[dict]) -> list[float]:
    """Every depth at which a tested curve has a point; each curve is a straight line between consecutive ones."""
    for cv in tested:
        if cv["points"][0][0] != 0:
            raise ValueError(f"{cv['key']}: the interval sums need a curve that starts at depth 0")
    return sorted({float(p[0]) for cv in tested for p in cv["points"]})


def mean_fraction(counts: list[int], sums: list[float], zone: int, points: list, edges: list[float]) -> float:
    """The mean of the curve over the zone's cells (0 where dry): inside an interval the curve is a straight line,
    so its sum over the interval's cells is n·r(lo) + slope·(Σdepth − n·lo); beyond the last point it holds."""
    r = [curves.ratio(points, x) for x in edges]
    total = 0.0
    for i, (n, s) in enumerate(zip(counts, sums)):
        if not n:
            continue
        if i == len(edges) - 1:
            total += n * r[i]
        else:
            slope = (r[i + 1] - r[i]) / (edges[i + 1] - edges[i])
            total += n * r[i] + slope * (s - n * edges[i])
    return total / zone


def design_period(lookup: list[list[float]]) -> tuple[Optional[float], int]:
    """(the median design return period over the zone cells the protection map holds one for — the mean of the two
    middle values when their number is even; None when it holds none: undefended), the cells it was taken over.
    A value below 1 (the map's no-data, −1) holds no period, as the platform reads the layer everywhere."""
    vals = sorted((v, n) for v, n in lookup if v == v and v >= 1)
    total = sum(n for _v, n in vals)
    if not total:
        return None, 0

    def nth(k: int) -> float:
        seen = 0
        for v, n in vals:
            seen += n
            if seen > k:
                return v
        return vals[-1][0]
    return (nth(total // 2) if total % 2 else (nth(total // 2 - 1) + nth(total // 2)) / 2), total


def modelled(p: dict, points: list, edges: list[float], rps: list[int]) -> dict:
    fr = {rp: mean_fraction(p["counts"][i], p["sums"][i], p["zone"], points, edges) for i, rp in enumerate(rps)}
    design, held = design_period(p["lookup"])
    undefended = engine.eal(fr)
    return {"fraction_at_rp": {str(rp): round(v, 6) for rp, v in fr.items()}, "ead_undefended": undefended,
            "design_rp_years": design, "protection_cells": held,
            "ead": protection.defended_eal(fr, design) if design else undefended}


# ── the test ────────────────────────────────────────────────────────────────────────────────────────────────
def _pct_rank(x: list[float]) -> list[float]:
    """Percentile rank 0–100 (ties averaged): Spearman ρ is unchanged, and the ledger's fixed 0–100 bands read
    quartiles of the modelled figure."""
    from ml.validation.metrics import rank
    r = np.asarray(rank(np.asarray(x, float)), float)
    return list((r - r.min()) / (r.max() - r.min()) * 100) if r.max() > r.min() else [50.0] * len(x)


def evaluate(obs, prof: dict, curve: dict, edges: list[float], rps: list[int]) -> dict:
    """One curve against the observed rates: the per-region rows, ρ and the registered rule's verdict."""
    from core.validation_gates import MIN_N_REGION_CLAIM, RANK_GATE_SPEARMAN
    from ml.validation.metrics import spearman
    rows, no_zone, no_polygon = [], [], []
    for code, o in obs.iterrows():
        p = prof.get(code)
        if p is None or not p["zone"]:
            (no_polygon if p is None else no_zone).append(code)
            continue
        m = modelled(p, curve["points"], edges, rps)
        rows.append({"code": code, "country": o["country"], "observed_rate": float(o["observed_rate"]),
                     "reported_loss_eur": round(float(o["reported_loss_eur"])), "events": int(o["events"]),
                     "zone_cells": p["zone"], **m})
    rho = spearman(np.array([r["ead"] for r in rows]), np.array([r["observed_rate"] for r in rows]))
    rho_u = spearman(np.array([r["ead_undefended"] for r in rows]), np.array([r["observed_rate"] for r in rows]))
    passed = rho is not None and len(rows) >= MIN_N_REGION_CLAIM and rho >= RANK_GATE_SPEARMAN
    return {"rows": rows, "no_zone": no_zone, "no_polygon": no_polygon, "spearman": rho, "spearman_undefended": rho_u, "n": len(rows),
            "passed": bool(passed)}


def maps_pass(codes: list[str], edges: list[float], path: Path = OUT) -> dict:
    """The pass over the maps for these regions and edges: read from the saved pass when it was made on the same
    layer version, regions and edges, else made now and saved (git-ignored, beside the other loss data)."""
    stamp = {"layer": LAYER, "version": registry.layer(LAYER)["version"], "edges": edges, "codes": sorted(codes)}
    f = path / "profiles.json"
    if f.exists():
        held = json.loads(f.read_text(encoding="utf-8"))
        if held.get("stamp") == stamp:
            return held["profiles"]
    prof = profiles(codes, edges)
    path.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"stamp": stamp, "profiles": prof}), encoding="utf-8")
    return prof


def run(session, *, actor: str = "europe_loss_test", path: Path = OUT) -> dict:
    """The registered test, every curve, each result recorded (validation ledger and family file); the per-region
    rows saved beside the pass over the maps for the drill-down."""
    from core.validation_gates import MIN_N_REGION_CLAIM
    from services.loss import published_test
    from services.validation.engine import ValidationResult, record_result
    proto = protocol()
    fam = curves.families()[FAMILY]
    tested = [next(c for c in fam["curves"] if c["key"] == k) for k in proto["curves"]]
    edges = edges_for(tested)
    obs, selection = observed()
    check_region_sets(selection)
    prof = maps_pass(list(obs.index), edges, path)
    rps = _paths()["rps"]
    built = []                      # every curve's result built (and checked against the ledger) before any is written
    for cv in tested:
        r = evaluate(obs, prof, cv, edges, rps)
        built.append((cv, r, ValidationResult(
            hazard_type="flood_loss", kind="rank", method="out_of_sample", scope=f"europe/{cv['key']}",
            predicted=_pct_rank([x["ead"] for x in r["rows"]]), observed=[x["observed_rate"] for x in r["rows"]],
            target_source="HANZE v2.1.1 reported river-flood losses 1990–2020 per NUTS-3 region (zone-asset rate)",
            data_vintage=f"HANZE 2.1.1 + exposure 2.0.3; EU maps {registry.layer(LAYER)['version']}",
            labels=[x["code"] for x in r["rows"]],
            notes=("Pre-registered (loss_protocol.json europe_loss_test). Predicted = the curve's defended expected "
                   "annual damage fraction of each region's 1-in-100-year zone, passed as its percentile rank (ρ "
                   "unchanged; the bands read quartiles). Pass needs ρ ≥ 0.35 with at least "
                   f"{MIN_N_REGION_CLAIM} regions."),
            extra={"protocol": KEY, "curve": cv["key"], "min_regions": MIN_N_REGION_CLAIM,
                   "spearman_undefended": r["spearman_undefended"], "regions_without_zone": len(r["no_zone"])})))
    ledger = [record_result(session, res, actor=actor, persist_samples=True, commit=False) for _cv, _r, res in built]
    session.commit()                # the three results are in the ledger together, or none is
    out = {}
    for (cv, r, _res), led in zip(built, ledger):
        passed = bool(led["passed_gate"] and r["passed"])
        result = {"protocol": KEY, "registered": proto["registered"], "run": date.today().isoformat(),
                  "countries": sorted({x["country"] for x in r["rows"]}), "regions_tested": r["n"],
                  "regions_without_zone": r["no_zone"], "regions_without_polygon": r["no_polygon"],
                  "spearman": r["spearman"], "spearman_undefended": r["spearman_undefended"],
                  "band_mean_observed": led["metrics"].get("band_mean_observed"),
                  "monotonic": led["metrics"].get("monotonic"), "gate": led["gate"],
                  "min_regions": MIN_N_REGION_CLAIM, "ledger_run": led["run_id"], **selection, "passed": passed}
        published_test.record(FAMILY, cv["key"], result)
        out[cv["key"]] = {**result, "rows": r["rows"]}
    (path / f"result_{date.today().isoformat()}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out

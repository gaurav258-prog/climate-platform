"""The processing proof (the product owner's decision of 2026-10-23: the loss figures tested 'till a point we are confident
on the processing'): every loss figure the engine recorded for the lookalike customers' books is recomputed here, from the
stored inputs, by an implementation of its own — the hazard read at the asset (hazard_intensity_samples), the curve's
published points (data/reference/vulnerability), the value the book states — and must agree to the cent. Every asset and
peril must have a result, and every gap a catalogue reason. Written from the method as published (the engine's step 6:
value × flooded share × damage ratio at the flooded depth, or value × damage ratio at the wind; the expected annual loss
the area under the loss–exceedance curve in annual exceedance probability, the rarest loss held beyond), never by calling
the engine. What is recomputed: each return period's loss — low, central and high — and the expected annual loss of
each, with the value they are a share of; and, for a flood figure, the defended expected annual loss (low, central, high)
at the published protection standard where the asset stands, or none where the protection map has no level there.
Coastal flood is read like river flood (water depth on its own maps); its defended figure — a stated range of standards —
is not yet recomputed here.
Reads the shared database as it is; skips where the lookalikes are not loaded."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
ORGS = [f"{f['name']} (demo)" for f in json.loads((ROOT / "data/demo/lookalike/assumptions.json").read_text()).values()]
LAYERS = json.loads((ROOT / "data/reference/hazard_intensity_layers.json").read_text())
LAYERS = LAYERS.get("layers", LAYERS)
FAMILIES = {d["family"]: d for d in (json.loads(p.read_text()) for p in (ROOT / "data/reference/vulnerability").glob("*.json"))}
# where each book states the value a curve's share is taken of, by the curve's basis (the method as decided, E307)
VALUE = {("insurance", "building"): "x.building_value_eur",
         ("insurance", "asset_value"): "NULLIF(COALESCE(x.building_value_eur, 0) + COALESCE(x.contents_value_eur, 0), 0)",
         ("banking", "building"): "x.building_value_eur", ("banking", "asset_value"): "x.building_value_eur",
         ("realestate", "building"): "x.building_value_eur", ("realestate", "asset_value"): "x.building_value_eur"}
EXT = {"insurance": "ext_insurance", "banking": "ext_banking", "realestate": "ext_realestate"}
_P = json.loads((ROOT / "data/reference/hazard_intensity_layers.json").read_text())["protection_layers"]
PROTECTION = ("jrc_flood_protection_europe", _P["jrc_flood_protection_europe"]["version"])


def ratio_at(points: list, x: float) -> float:
    """A published curve read at x: straight lines between its points; nothing below its first point (unless exactly
    on it); its last ratio held beyond its last point."""
    if x < points[0][0]:
        return 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1] if x > points[-1][0] else points[0][1]


def band_at(curve: dict, x: float, central: float) -> tuple[float, float]:
    """The curve's published spread at x: a measured band holding x (its 10th–90th percentile; the last band held
    beyond it); else the published standard deviation (straight lines between its points, its first value below them,
    its last beyond) as central ± one deviation within 0–1; else, where the publisher states none, no spread."""
    bands = curve.get("bands") or []
    for b in bands:
        if b["from_m"] < x <= b["to_m"]:
            return b["p10"], b["p90"]
    if bands and x > bands[-1]["to_m"]:
        return bands[-1]["p10"], bands[-1]["p90"]
    if curve.get("sd"):
        sd = curve["sd"][0][1] if x <= curve["sd"][0][0] else ratio_at(curve["sd"], x)
        return max(0.0, central - sd), min(1.0, central + sd)
    assert curve.get("spread") == "none published", curve["key"]
    return central, central


def defended(losses: dict[int, float], design_rp: float) -> float:
    """The expected annual loss with nothing lost below the protection line p = 1 / design_rp: the area under the
    loss–exceedance curve (the rarest loss held from p = 0; straight lines between the periods held; nothing more
    frequent than the most frequent period) from p = 0 to the line."""
    rps = sorted(losses, reverse=True)                        # rarest first: probability ascending
    pts = [(0.0, losses[rps[0]])] + [(1 / rp, losses[rp]) for rp in rps]
    top = min(1 / design_rp, 1 / rps[-1])
    area = 0.0
    for (p0, l0), (p1, l1) in zip(pts, pts[1:]):
        if p0 >= top:
            break
        q1 = min(p1, top)
        at_q1 = l0 + (l1 - l0) * (q1 - p0) / (p1 - p0) if p1 > p0 else l1
        area += (q1 - p0) * (l0 + at_q1) / 2
    return area


def annual(losses: dict[int, float]) -> float:
    rps = sorted(losses)
    total = 0.0
    for a, b in zip(rps, rps[1:]):
        total += (1 / a - 1 / b) * (losses[a] + losses[b]) / 2
    return total + losses[rps[-1]] / rps[-1]


def _runs(s) -> list[dict]:
    return [dict(r) for r in s.execute(text("""
        SELECT DISTINCT ON (r.org_id, r.book) r.run_id::text, r.book, r.n_assets, o.name, r.inputs
        FROM loss_runs r JOIN organizations o ON o.org_id = r.org_id
        WHERE o.name = ANY(:n) AND r.scenario = 'baseline' AND r.time_horizon = 'current'
        ORDER BY r.org_id, r.book, r.seq DESC"""), {"n": ORGS}).mappings()]


def test_every_asset_and_peril_has_a_figure_or_a_named_reason(session_rolled_back):
    s = session_rolled_back
    runs = _runs(s)
    if not runs:
        pytest.skip("the lookalike customers are not loaded (python -m scripts.lookalike.build)")
    from core import messages
    known = set(messages.catalogue())
    for r in runs:
        rows = s.execute(text("SELECT gap, gap_code, eal_eur FROM loss_results WHERE run_id = CAST(:r AS uuid)"),
                         {"r": r["run_id"]}).all()
        assert len(rows) == r["n_assets"] * len(r["inputs"]["layers"]), r["name"]     # every peril the run read
        assert all((g is None) == (e is not None) for g, _c, e in rows), r          # a figure or a gap, never both
        assert {c for g, c, _e in rows if g is not None} <= known, r


def test_every_recorded_figure_is_recomputed_to_the_cent(session_rolled_back):
    s = session_rolled_back
    runs = [r for r in _runs(s) if r["book"] in EXT]
    if not runs:
        pytest.skip("the lookalike customers are not loaded (python -m scripts.lookalike.build)")
    checked, defended_checked = 0, []
    for r in runs:
        figures = s.execute(text("""
            SELECT x.asset_id::text, x.peril, x.curve_key, CAST(x.exposed_value_eur AS FLOAT) AS value,
                   CAST(x.eal_eur AS FLOAT) AS eal, CAST(x.eal_low_eur AS FLOAT) AS eal_low,
                   CAST(x.eal_high_eur AS FLOAT) AS eal_high, x.loss_at_rp, x.flood_layer, x.protection_rp_years,
                   CAST(x.eal_defended_eur AS FLOAT) AS d, CAST(x.eal_defended_low_eur AS FLOAT) AS d_low,
                   CAST(x.eal_defended_high_eur AS FLOAT) AS d_high, e.latitude, e.longitude
            FROM loss_results x JOIN portfolio_entities e ON e.entity_id = x.asset_id
            WHERE x.run_id = CAST(:r AS uuid) AND x.gap IS NULL"""), {"r": r["run_id"]}).mappings().all()
        for f in figures:
            family = FAMILIES[f["curve_key"].split(":", 1)[0]]
            curve = next(c for c in family["curves"] if c["key"] == f["curve_key"])
            stated = s.execute(text(f"""SELECT CAST({VALUE[(r['book'], family['damage_basis'])]} AS FLOAT)
                                        FROM {EXT[r['book']]} x WHERE x.entity_id = CAST(:a AS uuid)"""),
                               {"a": f["asset_id"]}).scalar()
            assert abs(f["value"] - stated) < 0.005, f                               # the value the book states
            depth_peril = f["peril"] in ("flood", "coastal_flood")         # read in water depth on the asset's maps
            layer = f["flood_layer"] if depth_peril else "storm_v4_wind"
            L = LAYERS[layer]
            divide = 1.0 if family["metric"] == L["metric"] else float(L["conversions"][family["metric"]]["divide_by"])
            samples = s.execute(text("""
                SELECT rp_years, value, cell_fraction, cell_mean FROM hazard_intensity_samples
                WHERE layer_key = :k AND layer_version = :v AND latitude = :la AND longitude = :lo
                  AND scenario = 'present' AND period = 'present' AND climate_model = ''"""),
                {"k": layer, "v": L["version"], "la": f["latitude"], "lo": f["longitude"]}).mappings().all()
            assert samples, f
            low, losses, high = {}, {}, {}
            for sm in samples:
                rp = sm["rp_years"]
                if depth_peril:
                    share, depth = sm["cell_fraction"] or 0.0, sm["cell_mean"] or 0.0
                    if share == 0 or depth <= 0:
                        low[rp] = losses[rp] = high[rp] = 0.0
                        continue
                    c = ratio_at(curve["points"], depth)
                    lo, hi = band_at(curve, depth, c)
                    low[rp], losses[rp], high[rp] = stated * share * min(lo, c), stated * share * c, stated * share * max(hi, c)
                else:
                    low[rp] = losses[rp] = high[rp] = stated * ratio_at(curve["points"], float(sm["value"] or 0) / divide)
            recorded = {int(k): v for k, v in f["loss_at_rp"].items()}
            assert set(recorded) == set(losses), f
            for rp in losses:
                for part, mine in (("low", low), ("central", losses), ("high", high)):
                    assert abs(recorded[rp][part] - round(mine[rp], 2)) <= 0.011, (f["asset_id"], f["peril"], rp, part)
            for key, mine in (("eal", losses), ("eal_low", low), ("eal_high", high)):
                assert abs(f[key] - round(annual(mine), 2)) <= 0.011, (f["asset_id"], f["peril"], key, f[key], annual(mine))
            if f["peril"] == "flood":
                P = PROTECTION
                level = s.execute(text("""
                    SELECT status, design_rp_years FROM flood_protection_samples
                    WHERE layer_key = :k AND layer_version = :v AND latitude = :la AND longitude = :lo"""),
                    {"k": P[0], "v": P[1], "la": f["latitude"], "lo": f["longitude"]}).mappings().first()
                if level is None or level["status"] != "sampled":
                    assert f["protection_rp_years"] is None and f["d"] is None, f
                else:
                    rp_design = float(level["design_rp_years"])
                    assert f["protection_rp_years"] == rp_design, f
                    for key, mine in (("d", losses), ("d_low", low), ("d_high", high)):
                        assert abs(f[key] - round(defended(mine, rp_design), 2)) <= 0.011, (f["asset_id"], key)
                    defended_checked.append(f["asset_id"])
            checked += 1
    assert checked > 0, "no figure to recompute — every lookalike result is a gap"
    assert defended_checked, "no defended figure to recompute — no lookalike asset stands where a protection level is read"

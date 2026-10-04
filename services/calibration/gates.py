"""The two gates a calibration run is judged by (data/reference/calibration_protocol.json, E162).

downside   the fit's out-of-sample r² against the ranged publish floor — one constant, shared with the engine
upside     the four rules agreed on 2026-10-04 for the favourable years, every figure out of sample: each year is
           predicted by the fit without it (its own line, rmse and band), so a rule never sees the year it judges
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from ml.features.crop_cycle import decompose
from services.intelligence.supply_cogs import RANGED_PUBLISH_FLOOR

PROTOCOL = Path(__file__).resolve().parents[2] / "data" / "reference" / "calibration_protocol.json"


@lru_cache(maxsize=1)
def protocol() -> dict:
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def downside_pass(r2_oos: float | None) -> bool:
    return r2_oos is not None and r2_oos >= RANGED_PUBLISH_FLOOR


def _fold(pts: list[tuple], i: int, cap: bool, q_min: int) -> tuple[float, float]:
    """The fit without point i: (its prediction at point i, its 68% band half-width there) — with the cap, the
    prediction is limited to the mean observed anomaly of the fold's own wettest quartile."""
    tr = pts[:i] + pts[i + 1:]
    n = len(tr)
    xs, ys = [p[0] for p in tr], [p[1] for p in tr]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    rmse = math.sqrt(sum((y - a - b * x) ** 2 for x, y in zip(xs, ys)) / (n - 2))
    x = pts[i][0]
    pred = a + b * x
    if cap:
        wet = sorted(tr, key=lambda p: p[0])[: max(q_min, n // 4)]
        pred = min(pred, sum(p[1] for p in wet) / len(wet))
    return pred, rmse * math.sqrt(1 + 1 / n + (x - mx) ** 2 / sxx)


def _evaluate(pts: list[tuple], mean_score: float, cap: bool, rules: dict) -> dict:
    q_min = int(rules["wet_quartile_min_years"])
    res = [(p, *_fold(pts, i, cap, q_min)) for i, p in enumerate(pts)]
    fav = [r for r in res if r[0][0] < mean_score]
    obs, pred = [r[0][1] for r in fav], [r[1] for r in fav]
    rmse = math.sqrt(sum((o - p) ** 2 for o, p in zip(obs, pred)) / len(fav))
    bias = sum(pred) / len(pred) - sum(obs) / len(obs)
    cover = sum(1 for r in fav if abs(r[0][1] - r[1]) <= r[2]) / len(fav)
    wet = sorted(res, key=lambda r: r[0][0])[: max(q_min, len(res) // 4)]
    over = sum(r[1] for r in wet) / len(wet) - sum(r[0][1] for r in wet) / len(wet)
    half = sum(r[2] for r in wet) / len(wet)
    return {"favourable_years": len(fav), "bias": round(bias, 3), "rmse": round(rmse, 3),
            "t1_bias": abs(bias) <= rules["bias_max_rmse_fraction"] * rmse,
            "cover": round(cover, 4), "t2_band": rules["band_cover_min"] <= cover <= rules["band_cover_max"],
            "wet_over_prediction": round(over, 3), "wet_band_half_width": round(half, 3), "t4_wet": over <= half,
            "wet_cap_pct": round(sum(p[1] for p in sorted(pts, key=lambda p: p[0])[: max(q_min, len(pts) // 4)])
                                 / max(q_min, len(pts) // 4), 3) if cap else None}


def _area_share(pts: list[tuple], area: dict[int, float], mean_score: float) -> float | None:
    """Mean share of a favourable gain year's production deviation carried by harvested area (both detrended the same
    way, no cycle removed for area) — None when the source reports no area for those years."""
    if not area:
        return None
    da = decompose(area, allow_cycle=False)["years"]
    shares = []
    for x, y, yr in pts:
        t = da.get(yr)
        if x < mean_score and y > 0 and t and t.get("trend_full_window"):
            pp = math.log1p(y / 100)
            if pp > 0:
                shares.append(max(0.0, min(1.0, math.log1p(t["climate_pct"] / 100) / pp)))
    return sum(shares) / len(shares) if shares else None


def upside(pts: list[tuple], area: dict[int, float]) -> dict:
    """The upside verdict for one fitted panel: pts = [(score, climate_pct, year)], area = {year: harvested ha} of the
    same series. Returns the evaluation (line, and the capped line when rule 4 needs it) and `pass`."""
    rules = protocol()["upside"]
    q_min = int(rules["wet_quartile_min_years"])
    if len(pts) < 2 * q_min + 2:
        return {"pass": False, "failed": ["too few years for the four rules"]}
    mean_score = sum(p[0] for p in pts) / len(pts)
    if sum(1 for p in pts if p[0] < mean_score) < q_min:
        return {"pass": False, "failed": ["too few favourable years"]}
    share = _area_share(pts, area, mean_score)
    t3 = share is not None and share <= rules["area_share_max"]
    line = _evaluate(pts, mean_score, False, rules)
    final, capped = line, False
    if not line["t4_wet"]:
        final, capped = _evaluate(pts, mean_score, True, rules), True
    checks = {"1 bias": final["t1_bias"], "2 band": final["t2_band"], "3 area": t3, "4 too wet": final["t4_wet"]}
    return {"pass": all(checks.values()), "failed": [k for k, ok in checks.items() if not ok],
            "capped": capped, "area_share": round(share, 4) if share is not None else None,
            "line": line, "capped_line": final if capped else None}

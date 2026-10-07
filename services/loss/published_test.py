"""The held-out test of a published damage curve on observed losses — data/reference/loss_protocol.json,
published_curve_test (stated before it was built or run). Nothing is fitted to the claims, so every event with enough
claims is held out; the pass tests are the protocol's own ('test': event totals and range coverage).

  test(family_key, curve_key)   per event: predicted total (Σ the curve's ratio at each claim's depth × the building's
                                value) against the recorded total, and the share of claims whose recorded ratio lies
                                inside the curve's published range — and whether both tests pass
  record(family_key, result)    the result on the curve in its family file (a rebuilt family keeps it)
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np

from services.loss import curves, measured, registry

INCH = 0.0254


def _ratio(points: list, x: np.ndarray) -> np.ndarray:
    xs, ys = np.array([p[0] for p in points]), np.array([p[1] for p in points])
    return np.interp(x, xs, ys, left=0.0, right=ys[-1])          # linear between points, the last held beyond


def test(family_key: str, curve_key: str) -> dict:
    proto = measured.protocol()
    rule, T = proto["published_curve_test"], proto["test"]
    fam = curves.families()[family_key]
    curve = next(c for c in fam["curves"] if c["key"] == curve_key)
    if not curve.get("sd"):
        raise ValueError(f"{curve_key} publishes no range to test")
    df, aside, n_in = measured._claims()
    depth = df[proto["measured_curves"]["depth_field"]].to_numpy() * INCH
    central = _ratio(curve["points"], depth)
    sd = _ratio(curve["sd"], depth)
    lo, hi = np.clip(central - sd, 0, 1), np.clip(central + sd, 0, 1)
    ratio = df["damage_ratio"].to_numpy()
    inside = (ratio >= lo) & (ratio <= hi)
    df = df.assign(_pred=central * df["buildingPropertyValue"].to_numpy(), _inside=inside)
    counts = df["floodEvent"].value_counts()
    rows = []
    for ev in [e for e, n in counts.items() if n >= T["min_event_claims"]]:
        g = df[df["floodEvent"] == ev]
        predicted, recorded = float(g["_pred"].sum()), float(g["buildingDamageAmount"].sum())
        rows.append({"event": ev, "claims": int(len(g)), "predicted_usd": round(predicted), "recorded_usd": round(recorded),
                     "error": round(predicted / recorded - 1, 4) if recorded else None,
                     "band_coverage": round(float(g["_inside"].mean()), 4)})
    within = [r for r in rows if r["error"] is not None and abs(r["error"]) <= T["event_total"]["tolerance"]]
    share = len(within) / len(rows) if rows else 0.0
    tested = df[df["floodEvent"].isin([r["event"] for r in rows])]
    coverage = float(tested["_inside"].mean()) if len(tested) else 0.0
    passed_total = share >= T["event_total"]["share_of_events_required"]
    passed_band = T["band"]["coverage_min"] <= coverage <= T["band"]["coverage_max"]
    return {"protocol": "published_curve_test", "registered": rule["registered"], "run": date.today().isoformat(),
            "claims_in": n_in, "claims_used": int(len(df)), "set_aside": aside, "countries": ["US"],
            "events": rows, "events_tested": len(rows), "events_within_tolerance": len(within),
            "share_within_tolerance": round(share, 4),
            "median_abs_error": round(float(np.median([abs(r["error"]) for r in rows])), 4) if rows else None,
            "band_coverage": round(coverage, 4), "passed_event_total": passed_total, "passed_band": passed_band,
            "passed": bool(passed_total and passed_band)}


def record(family_key: str, curve_key: str, result: dict) -> None:
    path = registry.REF / "vulnerability" / f"{family_key}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    for c in doc["curves"]:
        if c["key"] == curve_key:
            c["test"] = result
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    curves.reload()

"""The held-out test of a published damage curve on observed losses — data/reference/loss_protocol.json,
published_curve_test (North America residential, stated before it was built or run; corrected 2026-10-23, E325) and
published_curve_test_commercial (North America commercial, registered 2026-10-23). Nothing is fitted to the claims, so
every event with enough claims is held out; the pass tests are the protocol's own ('test': event totals and range
coverage — the range test only where the curve publishes a range, as each registration states).

  test(family_key, curve_key, key)   per event: predicted total (Σ the curve's ratio at each claim's depth × the
                                     building's value) against the recorded total, and, for a curve with a published
                                     range, the share of claims whose recorded ratio lies inside it — and whether the
                                     registered tests pass; the claims are the registration's occupancy codes in the
                                     curve's countries (E325)
  record(family_key, curve_key, result, supersedes_because)
                                     the result on the curve in its family file (a rebuilt family keeps it); a result it
                                     replaces for a stated reason is kept, summarised, under 'superseded'
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np

from services.loss import curves, measured, registry

INCH = 0.0254
# The registrations this test runs: each one's occupancy codes and whether its pass needs the range test (held here as
# values; tests/unit/test_curve_claims_tests.py checks the registered text still states each one).
RULES = {
    "published_curve_test": {"curve": "jrc_huizinga_2017:residential:021", "codes": None, "use": "residential",
                             "range": True},
    "published_curve_test_commercial": {"curve": "jrc_huizinga_2017:commercial:021", "codes": [4, 6, 18, 19],
                                        "use": "non-residential", "range": False},
}


def _ratio(points: list, x: np.ndarray) -> np.ndarray:
    xs, ys = np.array([p[0] for p in points]), np.array([p[1] for p in points])
    return np.interp(x, xs, ys, left=0.0, right=ys[-1])          # linear between points, the last held beyond


def test(family_key: str, curve_key: str, key: str = "published_curve_test") -> dict:
    proto = measured.protocol()
    rule, T, R = proto[key], proto["test"], RULES[key]
    if R["curve"] != curve_key:
        raise ValueError(f"{key} is registered for {R['curve']}, not {curve_key}")
    fam = curves.families()[family_key]
    curve = next(c for c in fam["curves"] if c["key"] == curve_key)
    if R["range"] != bool(curve.get("sd")):
        raise ValueError(f"{curve_key}: the registration's range test does not match the curve's published spread")
    df, aside, n_in = measured._claims(R["codes"], curve["countries"], R["use"])
    depth = df[proto["measured_curves"]["depth_field"]].to_numpy() * INCH
    central = _ratio(curve["points"], depth)
    df = df.assign(_pred=central * df["buildingPropertyValue"].to_numpy())
    if R["range"]:
        sd = _ratio(curve["sd"], depth)
        lo, hi = np.clip(central - sd, 0, 1), np.clip(central + sd, 0, 1)
        ratio = df["damage_ratio"].to_numpy()
        df = df.assign(_inside=(ratio >= lo) & (ratio <= hi))
    counts = df["floodEvent"].value_counts()
    rows = []
    for ev in [e for e, n in counts.items() if n >= T["min_event_claims"]]:
        g = df[df["floodEvent"] == ev]
        predicted, recorded = float(g["_pred"].sum()), float(g["buildingDamageAmount"].sum())
        rows.append({"event": ev, "claims": int(len(g)), "predicted_usd": round(predicted), "recorded_usd": round(recorded),
                     "error": round(predicted / recorded - 1, 4) if recorded else None,
                     **({"band_coverage": round(float(g["_inside"].mean()), 4)} if R["range"] else {})})
    within = [r for r in rows if r["error"] is not None and abs(r["error"]) <= T["event_total"]["tolerance"]]
    share = len(within) / len(rows) if rows else 0.0
    passed_total = measured.enough_events(len(within), len(rows))
    out = {"protocol": key, "registered": rule["registered"], "run": date.today().isoformat(),
           "claims_in": n_in, "claims_used": int(len(df)), "set_aside": aside,
           "countries": sorted(df["country"].unique().tolist()), "occupancy_codes": R["codes"] or
           proto["measured_curves"]["residential_codes"]["codes"],
           "events": rows, "events_tested": len(rows), "events_within_tolerance": len(within),
           "share_within_tolerance": round(share, 4),
           "median_abs_error": round(float(np.median([abs(r["error"]) for r in rows])), 4) if rows else None,
           "passed_event_total": passed_total}
    if R["range"]:
        tested = df[df["floodEvent"].isin([r["event"] for r in rows])]
        coverage = float(tested["_inside"].mean()) if len(tested) else 0.0
        passed_band = T["band"]["coverage_min"] <= coverage <= T["band"]["coverage_max"]
        return {**out, "band_coverage": round(coverage, 4), "passed_band": passed_band,
                "passed": bool(passed_total and passed_band)}
    return {**out, "band_coverage": None, "passed_band": None,
            "range_test": "not applicable: the curve publishes no range (product owner's decision, 2026-10-23)",
            "passed": bool(passed_total)}


_SUMMARY = ("protocol", "registered", "run", "claims_used", "countries", "events_tested", "events_within_tolerance",
            "median_abs_error", "band_coverage", "spearman", "passed")


def record(family_key: str, curve_key: str, result: dict, supersedes_because: str | None = None) -> None:
    path = registry.REF / "vulnerability" / f"{family_key}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    for c in doc["curves"]:
        if c["key"] == curve_key:
            old = c.get("test") or {}
            kept = list(old.get("superseded", []))
            if supersedes_because and old:
                kept.append({**{k: old[k] for k in _SUMMARY if k in old}, "because": supersedes_because})
            c["test"] = {**result, **({"superseded": kept} if kept else {})}
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    curves.reload()

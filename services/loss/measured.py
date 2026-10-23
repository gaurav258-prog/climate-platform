"""A damage curve measured from observed claims (E171): the spread of building damage by flood depth above ground,
from the prepared NFIP claims (services.loss.claims), under data/reference/loss_protocol.json — and its test on flood
events it was not built from.

  build()   per depth band: the claims, the share with no damage, the 10th/50th/90th percentile and the mean damage
            ratio; residential claims only (FEMA's occupancy codes, quoted in the protocol) in the curve's countries
            (E325); every claim set aside is counted with its reason
  test()    each flood event with ≥ 500 claims, predicted from all other events' claims: the event's total damage
            (Σ mean ratio of each claim's band × the building's value) against the recorded total, and the share of
            its claims whose damage ratio falls inside their band's 10th–90th percentile
  write()   the family file data/reference/vulnerability/nfip_measured.json (kind "measured"), with the test and
            whether it passed the protocol's two tests"""
from __future__ import annotations

import json
from datetime import date

import numpy as np

from services.loss import claims, registry

INCH = 0.0254
FAMILY_FILE = registry.REF / "vulnerability" / "nfip_measured.json"
COUNTRIES = ["US"]                  # the measured curve's countries: the claims it is built and tested from (E325)


def protocol() -> dict:
    return json.loads((registry.REF / "loss_protocol.json").read_text(encoding="utf-8"))


def _claims(codes: list[int] | None = None, countries=("US",), use: str = "residential"):
    """The prepared claims a curve is built or tested from: the curve's countries only (measured_curves 'countries',
    E325 — FEMA's state field read through services.reference.us_areas), the FEMA occupancy codes given (default the
    residential codes), and the depth rules; every claim set aside is counted with its reason."""
    import pandas as pd
    import pyarrow.parquet as pq

    from services.reference.us_areas import country
    P = protocol()["measured_curves"]
    codes = P["residential_codes"]["codes"] if codes is None else codes
    t = pq.read_table(claims.OUT, columns=["floodEvent", "state", "occupancyType", P["depth_field"], "damage_ratio",
                                            "buildingDamageAmount", "buildingPropertyValue"]).to_pandas()
    place = t["state"].map(country)
    d = t[P["depth_field"]]
    steps = [
        ("no state recorded (the claim cannot be placed in a country)", place.isna()),
        ("outside the curve's countries (a US outlying area: its own country)", ~place.isin(list(countries))),
        (f"not a {use} building (FEMA occupancy code)", ~t["occupancyType"].isin(codes)),
        ("no exterior water depth recorded", d.isna()),
        (f"exterior depth recorded as {P['set_aside']['placeholder_in']} (a placeholder)", d == P["set_aside"]["placeholder_in"]),
        ("no water above ground (exterior depth zero or negative)", d <= 0),
        (f"exterior depth above {P['set_aside']['above_in']} inches (beyond the last band)", d > P["set_aside"]["above_in"]),
    ]
    aside, drop = {}, pd.Series(False, index=t.index)
    for why, mask in steps:
        mask = mask.fillna(False) & ~drop
        aside[why] = int(mask.sum())
        drop |= mask
    kept = t[~drop].assign(country=place[~drop])
    kept["band"] = np.digitize(kept[P["depth_field"]].to_numpy(), P["bins_in"][1:-1], right=True)
    assert len(kept) + sum(aside.values()) == len(t)
    return kept, aside, len(t)


def enough_events(within: int, events: int) -> bool:
    """The event-total test's count (loss_protocol.json test.event_total): at least the registered share of the held-out
    events within the tolerance, the share held as a whole-number fraction and compared in whole numbers — 'at least two
    thirds' is within × 3 ≥ events × 2, never a rounded decimal (E326: 0.67 failed 6 of 9)."""
    f = protocol()["test"]["event_total"]["share_of_events_required"]
    return events > 0 and within * f["denominator"] >= events * f["numerator"]


def _bands(df) -> list[dict]:
    P = protocol()["measured_curves"]
    edges = P["bins_in"]
    out = []
    for i in range(len(edges) - 1):
        r = df.loc[df["band"] == i, "damage_ratio"].to_numpy()
        out.append({"from_m": round(edges[i] * INCH, 4), "to_m": round(edges[i + 1] * INCH, 4), "n": int(r.size),
                    "zero_share": round(float((r == 0).mean()), 4) if r.size else None,
                    "p10": round(float(np.quantile(r, .10)), 4) if r.size else None,
                    "p50": round(float(np.quantile(r, .50)), 4) if r.size else None,
                    "p90": round(float(np.quantile(r, .90)), 4) if r.size else None,
                    "mean": round(float(r.mean()), 4) if r.size else None})
    return out


def test(df) -> dict:
    T = protocol()["test"]
    counts = df["floodEvent"].value_counts()
    events = [e for e, n in counts.items() if n >= T["min_event_claims"]]
    rows, inside_all, n_all = [], 0, 0
    for ev in events:
        held = df[df["floodEvent"] == ev]
        bands = _bands(df[df["floodEvent"] != ev])
        mean = np.array([b["mean"] for b in bands])[held["band"].to_numpy()]
        lo = np.array([b["p10"] for b in bands])[held["band"].to_numpy()]
        hi = np.array([b["p90"] for b in bands])[held["band"].to_numpy()]
        predicted = float((mean * held["buildingPropertyValue"].to_numpy()).sum())
        recorded = float(held["buildingDamageAmount"].sum())
        ratio = held["damage_ratio"].to_numpy()
        inside = int(((ratio >= lo) & (ratio <= hi)).sum())
        inside_all += inside
        n_all += len(held)
        rows.append({"event": ev, "claims": int(len(held)), "predicted_usd": round(predicted), "recorded_usd": round(recorded),
                     "error": round(predicted / recorded - 1, 4) if recorded else None,
                     "band_coverage": round(inside / len(held), 4)})
    within = [r for r in rows if r["error"] is not None and abs(r["error"]) <= T["event_total"]["tolerance"]]
    share = len(within) / len(rows) if rows else 0.0
    coverage = inside_all / n_all if n_all else 0.0
    passed_total = enough_events(len(within), len(rows))
    passed_band = T["band"]["coverage_min"] <= coverage <= T["band"]["coverage_max"]
    return {"protocol": protocol()["protocol"], "events": rows, "events_tested": len(rows),
            "events_within_tolerance": len(within), "share_within_tolerance": round(share, 4),
            "median_abs_error": round(float(np.median([abs(r["error"]) for r in rows])), 4) if rows else None,
            "band_coverage": round(coverage, 4), "passed_event_total": passed_total, "passed_band": passed_band,
            "passed": bool(passed_total and passed_band)}


def _non_decreasing(means: list[float], weights: list[int]) -> tuple[list[float], list[list[int]]]:
    """Pool-adjacent-violators: the closest non-decreasing sequence (claim-weighted); returns the values and the
    groups of bands that were pooled."""
    blocks = [[m, w, [i]] for i, (m, w) in enumerate(zip(means, weights))]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0]:
            m0, w0, ix0 = blocks[i]
            m1, w1, ix1 = blocks.pop(i + 1)
            blocks[i] = [(m0 * w0 + m1 * w1) / (w0 + w1), w0 + w1, ix0 + ix1]
            i = max(i - 1, 0)
        else:
            i += 1
    out = [0.0] * len(means)
    for m, _w, ix in blocks:
        for j in ix:
            out[j] = round(m, 4)
    return out, [ix for _m, _w, ix in blocks if len(ix) > 1]


def build_family() -> dict:
    P = protocol()["measured_curves"]
    df, aside, n_in = _claims(countries=COUNTRIES)
    bands = _bands(df)
    thin = [b for b in bands if b["n"] < P["min_claims_per_bin"]]
    if thin:
        raise ValueError(f"bands with fewer than {P['min_claims_per_bin']} claims: {thin}")
    result = test(df)
    m = claims.manifest()
    central, pooled = _non_decreasing([b["mean"] for b in bands], [b["n"] for b in bands])
    points = [[0.0, 0.0]] + [[round((b["from_m"] + b["to_m"]) / 2, 4), c] for b, c in zip(bands, central)]
    return {
        "family": "nfip_measured", "kind": "measured", "peril": "flood", "metric": "water_depth", "unit": "m",
        "damage_basis": "building",
        "source": {"authors": "FEMA (OpenFEMA)", "year": 2026, "title": "NFIP Redacted Claims v3", "publisher": "FEMA",
                   "url": "https://www.fema.gov/openfema-data-page/nfip-redacted-claims-v3", "file": m.get("file"),
                   "sha256": m.get("sha256")},
        "licence": "US federal open data (OpenFEMA); 'This dataset is not intended to be an official federal report'",
        "beyond_last": "hold",
        "derivation": {"protocol": protocol()["protocol"], "built": date.today().isoformat(),
                       "depth_field": P["depth_field"], "residential_codes": P["residential_codes"]["codes"],
                       "claims_in": n_in, "claims_used": int(len(df)), "set_aside": aside, "countries": COUNTRIES,
                       "method": "mean damage ratio at each band's midpoint (central value); the band's 10th and 90th "
                                 "percentiles as the range; the ratio is building damage / building value, both "
                                 "actual cash value as the adjuster recorded them. Damage does not fall as water "
                                 "rises: where a band's mean is below the band before it, the two are pooled "
                                 "(claim-weighted mean, pool-adjacent-violators); the measured means are kept in "
                                 "the bands",
                       "pooled_bands": pooled},
        "curves": [{"key": "nfip_measured:residential:united_states", "occupancy": "residential",
                    "region": "united_states", "countries": COUNTRIES, "points": points, "bands": bands}],
        "test": result}


def _summary(fam: dict) -> dict:
    d, t = fam.get("derivation") or {}, fam.get("test") or {}
    return {"built": d.get("built"), "claims_used": d.get("claims_used"), "countries": d.get("countries"),
            "events_tested": t.get("events_tested"), "events_within_tolerance": t.get("events_within_tolerance"),
            "band_coverage": t.get("band_coverage"), "passed": t.get("passed")}


def write(supersedes_because: str | None = None) -> dict:
    """Build the family and write it; a build it replaces for a stated reason is kept, summarised, under 'superseded'."""
    fam = build_family()
    if FAMILY_FILE.exists():
        old = json.loads(FAMILY_FILE.read_text(encoding="utf-8"))
        fam["superseded"] = old.get("superseded", [])
        if supersedes_because:
            fam["superseded"].append({**_summary(old), "because": supersedes_because})
    FAMILY_FILE.parent.mkdir(parents=True, exist_ok=True)
    FAMILY_FILE.write_text(json.dumps(fam, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return fam

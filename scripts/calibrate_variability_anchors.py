"""Derive the baseline-relative percentile anchors for the temperature-variability screen (and check the
soil-water screen) from the golden-source climatology, so the published anchor tables are reproducible rather
than hand-tuned.

Method: a chronic-variability HAZARD should read "High" only where the driver is ELEVATED vs the land it could
sit on — not wherever seasons merely exist. We take the driver's empirical percentiles across the LAND cells of
the 1991–2020 baseline and place the bucket thresholds on the distribution: median land → mid-M, top quartile →
enter High, top decile → enter Very High. The printed (value, score) breakpoints are what
ml/scoring/climate_variability_point.py embeds as _TEMP_VAR_ANCHORS.

Run:  .venv/bin/python -m scripts.calibrate_variability_anchors
"""
from __future__ import annotations

from sqlalchemy import text

from core.db.session import get_session

# Percentile → target score: where each land percentile of the driver should land on the 0–100 scale, so the
# screen discriminates (top quartile = High, top decile = Very High). Disclosed design choice.
_PCT_TO_SCORE = [(0.10, 8.0), (0.25, 20.0), (0.50, 38.0), (0.75, 50.0), (0.90, 74.0), (0.97, 88.0), (0.99, 95.0)]


def _percentiles(sql_value_expr: str, table: str, where: str) -> dict:
    sel = ", ".join(f"percentile_cont({p}) WITHIN GROUP (ORDER BY v) p{int(p*100):02d}"
                    for p, _ in _PCT_TO_SCORE)
    q = f"WITH r AS (SELECT lat, lon, {sql_value_expr} AS v FROM {table} GROUP BY lat, lon {where}) SELECT {sel} FROM r"
    with get_session() as s:
        return dict(s.execute(text(q)).mappings().first())


def main() -> int:
    # temperature: seasonal amplitude (warmest- minus coldest-month mean), land proxy rng>2°C excludes ocean.
    rng = _percentiles("max(CAST(temp_mean_k AS FLOAT)) - min(CAST(temp_mean_k AS FLOAT))",
                       "climatology_baseline", "HAVING max(CAST(temp_mean_k AS FLOAT)) - min(CAST(temp_mean_k AS FLOAT)) > 2")
    print("temperature-variability land amplitude percentiles (°C):")
    anchors = [(0.0, 0.0)]
    for p, score in _PCT_TO_SCORE:
        v = round(float(rng[f"p{int(p*100):02d}"]), 1)
        anchors.append((v, score))
        print(f"  p{int(p*100):>2} = {v:>5}°C  → score {score}")
    anchors.append((60.0, 100.0))
    print("  _TEMP_VAR_ANCHORS =", anchors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Crop calibration coverage (E165) — every crop × origin the crop maps hold, and what the platform publishes for it:
a loss range and a gain range, a loss range only, tested and held (no number), or not calibrated (with the reason).

Read from the coverage snapshot (services.calibration.registry_specs) and the published runs; the area share is the
origin's share of the crop's harvested area in its map. Categories, not verdicts (no 'failed' wording)."""
from __future__ import annotations

import gzip
import json
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.calibration import crop_area_weights as W
from services.intelligence.supply_cogs import RANGED_PUBLISH_FLOOR

CATEGORY = {"both": "Loss and gain ranges", "loss": "Loss range", "held": "Tested — held", "none": "Not calibrated"}


@lru_cache(maxsize=1)
def _outlines() -> dict[str, dict]:
    """{ISO2: simplified GeoJSON geometry} of the GISCO 2020 countries — for the map, 0.05° tolerance."""
    from shapely.geometry import mapping, shape
    doc = json.load(gzip.open(W.ROOT / W.reference()["countries"]["file"]))
    out = {}
    for f in doc["features"]:
        code = {"EL": "GR", "UK": "GB"}.get(f["properties"]["CNTR_ID"], f["properties"]["CNTR_ID"])
        out[code] = mapping(shape(f["geometry"]).simplify(0.05, preserve_topology=True))
    return out


def _rows(session: Session, commodity: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT v.origin, CAST(v.area_share AS FLOAT) AS area_share, CAST(v.area_ha AS FLOAT) AS area_ha, v.status, v.reason,
               bool_or(r.downside_pass) AS loss, bool_or(r.upside_pass) AS gain, max(CAST(r.r2_oos AS FLOAT)) AS r2_oos,
               string_agg(DISTINCT s.driver, ', ') AS drivers, count(r.run_id) AS published, count(s.spec_id) AS recipes,
               bool_or(l.run_id IS NOT NULL) AS run
        FROM crop_calibration_coverage v
        LEFT JOIN crop_calibration_specs s ON s.commodity = v.commodity AND s.origin = v.origin AND s.retired_at IS NULL
                                           AND s.yield_region = ''
        LEFT JOIN crop_calibration_runs r ON r.spec_id = s.spec_id AND r.status = 'published'
        LEFT JOIN LATERAL (SELECT run_id FROM crop_calibration_runs x WHERE x.spec_id = s.spec_id LIMIT 1) l ON true
        WHERE v.commodity = :c
        GROUP BY v.origin, v.area_share, v.area_ha, v.status, v.reason
        ORDER BY v.area_share DESC"""), {"c": commodity}).mappings()
    out = []
    for r in rows:
        if r["status"] != "recipe":
            cat, why = "none", r["reason"]
        elif not r["published"]:
            cat, why = "none", "a recipe is recorded; its run awaits review" if r["run"] else "a recipe is recorded, not yet run"
        elif r["loss"] and r["gain"]:
            cat, why = "both", None
        elif r["loss"]:
            cat, why = "loss", "the gain side did not pass the four upside rules"
        else:
            cat, why = "held", f"tested: out-of-sample r² {r['r2_oos']:.2f} — below the {RANGED_PUBLISH_FLOOR:.2f} bar"
        out.append({"origin": r["origin"], "area_share": r["area_share"], "area_ha": r["area_ha"], "category": cat,
                    "label": CATEGORY[cat], "why": why, "drivers": r["drivers"], "r2_oos": r["r2_oos"]})
    return out


def coverage(session: Session, commodity: str | None) -> dict:
    crops = [dict(r) for r in session.execute(text("""
        SELECT commodity, count(*) AS origins, max(generated_at) AS generated_at FROM crop_calibration_coverage
        GROUP BY commodity ORDER BY commodity""")).mappings()]
    pick = commodity or (crops[0]["commodity"] if crops else None)
    rows = _rows(session, pick) if pick else []
    share = {k: round(sum(r["area_share"] for r in rows if r["category"] == k) * 100, 1) for k in CATEGORY}
    outlines = _outlines()
    return {"commodities": crops, "commodity": pick, "rows": rows, "area_share_pct": share, "categories": CATEGORY,
            "geometry": {r["origin"]: outlines.get(r["origin"]) for r in rows if outlines.get(r["origin"])}}

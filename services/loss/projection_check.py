"""How far the projection source's present day sits from what was observed and from the JRC maps — the check stated in
data/reference/loss_protocol.json (projection_present_day_check) before it was built or run. Reported, not a gate: a
projected figure cannot be tested against a future that has not happened.

  observed   the flood_jrc_ems validator's six EMS events and nodes, the flooded share of each node's mapped part
  predictor  as for the JRC maps: the share of the node box's pixels wet at the 1-in-100-year period × the depth–damage
             fraction at their mean depth — Aqueduct's present-day map (30″) and the JRC maps (90 m) on the same nodes
  agreement  at every asset location, whether the two sources agree it is wet or dry at the 1-in-100-year period
Raster reads go through the isolated sampler (services.geo.raster_sampler, E170)."""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.scoring.flood_jrc import flood_score
from services.loss import intensity, registry

LAYER = "aqueduct_river_flood"


def _present_path(rp: int = 100):
    L = registry.layer(LAYER)
    v = {"scenario": L["present"]["scenario"], "period": L["present"]["year"], "climate_model": L["present"]["model"]}
    return intensity.aqueduct_path(v, rp)


def aqueduct_box(b) -> Optional[tuple[float, float]]:
    """(wet share, mean wet depth) of the Aqueduct present-day 1-in-100-year map's pixels whose centres lie in the box."""
    from services.geo import raster_sampler
    L = registry.layer(LAYER)
    z = raster_sampler.zonal(str(_present_path()), list(b.exterior.coords), above=L["dry_below"])
    if z is None or not z["inside"]:
        return None
    return z["present"] / z["inside"], (z["sum"] / z["present"] if z["present"] else 0.0)


def _metrics(pred: list[float], obs: list[float]) -> dict:
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score
    y = np.asarray(obs) > 0.02
    return {"n": len(pred), "rho": round(float(spearmanr(pred, obs)[0]), 4),
            "auc_share_gt_2pct": round(float(roc_auc_score(y, pred)), 4) if 0 < y.sum() < len(y) else None}


def against_observed() -> dict:
    import pandas as pd

    from ml.scoring.flood_jrc import TileSet
    from scripts.backtest_flood_ems import EVENTS, ems_extent, ems_mapped
    from services.validation.validators.flood_jrc import PANEL, event_nodes, observed_share
    data = pd.read_parquet(PANEL)
    tiles = TileSet()
    aq, jrc, obs, per_event = [], [], [], {}
    for ev in EVENTS:
        ext, _fc = ems_extent(ev)
        mapped = ems_mapped(ev)
        m = data.event == ev["name"]
        if ext is None or ext.is_empty or mapped is None or not m.any():
            continue
        a_, j_, o_ = [], [], []
        for _c, b in event_nodes(data.loc[m, "h3_cell"], ev, mapped):
            st, ab = tiles.stats(b), aqueduct_box(b)
            if st is None or ab is None:
                continue
            a_.append(flood_score(*ab)); j_.append(flood_score(*st[100][:2])); o_.append(observed_share(ext, mapped, b))
        if len(a_) >= 10:
            per_event[ev["name"]] = {"aqueduct": _metrics(a_, o_), "jrc": _metrics(j_, o_)}
        aq += a_; jrc += j_; obs += o_
    tiles.close()
    return {"pooled": {"aqueduct": _metrics(aq, obs), "jrc": _metrics(jrc, obs)}, "per_event": per_event}


def agreement(session: Session) -> dict:
    """Counts over asset locations: wet or dry at the 1-in-100-year period in each source."""
    L = registry.layer(LAYER)
    J = registry.layer("jrc_river_flood")
    rows = session.execute(text("""
        SELECT CASE WHEN j.cell_fraction IS NULL THEN 'no_land' WHEN j.cell_fraction > 0 THEN 'wet' ELSE 'dry' END AS jrc,
               CASE WHEN a.cell_fraction > 0 THEN 'wet' ELSE 'dry' END AS aq, count(*) AS n
        FROM hazard_intensity_samples j
        JOIN hazard_intensity_samples a ON a.latitude = j.latitude AND a.longitude = j.longitude AND a.rp_years = j.rp_years
         AND a.layer_key = :ak AND a.layer_version = :av AND a.scenario = :s AND a.period = :p AND a.climate_model = :m
        WHERE j.layer_key = 'jrc_river_flood' AND j.layer_version = :jv AND j.rp_years = 100 AND j.status = 'sampled'
          AND j.scenario = 'present'
        GROUP BY 1, 2"""), {"ak": LAYER, "av": L["version"], "s": L["present"]["scenario"], "p": L["present"]["year"],
                            "m": L["present"]["model"], "jv": J["version"]}).all()
    c: dict[tuple[str, str], int] = {}
    for jrc, aq, n in rows:
        c[(jrc, aq)] = c.get((jrc, aq), 0) + int(n)
    judged = sum(n for (j, _a), n in c.items() if j != "no_land")
    agree = c.get(("wet", "wet"), 0) + c.get(("dry", "dry"), 0)
    return {"locations": sum(c.values()), "jrc_no_land_in_cell": sum(n for (j, _a), n in c.items() if j == "no_land"),
            "both_wet": c.get(("wet", "wet"), 0), "both_dry": c.get(("dry", "dry"), 0),
            "jrc_wet_only": c.get(("wet", "dry"), 0), "aqueduct_wet_only": c.get(("dry", "wet"), 0),
            "agree_share": round(agree / judged, 4) if judged else None,
            "basis": "JRC wet: the location's H3 res-8 cell has a flooded share; Aqueduct wet: its 30″ pixel is wet"}


def run(session: Session) -> dict:
    rule = json.loads((registry.REF / "loss_protocol.json").read_text(encoding="utf-8"))["projection_present_day_check"]
    return {"protocol": "projection_present_day_check", "registered": rule["registered"], "run": date.today().isoformat(),
            "against_observed": against_observed(), "agreement_at_assets": agreement(session)}


def record(result: dict) -> None:
    f = registry.REF / "hazard_intensity_layers.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    doc["layers"][LAYER]["present_day_check"] = result
    f.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

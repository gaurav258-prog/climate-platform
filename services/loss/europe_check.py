"""The JRC European river-flood maps' check before they replace the global maps (data/reference/loss_protocol.json
'europe_maps_check', registered 2026-10-16 before it was built or run).

Both maps are judged on the flood_jrc_ems validator's own nodes — the six Copernicus EMS observed floods, nodes inside
the event box with at least half the 0.1° box inside the area EMS mapped — against the observed flooded share of each
node's mapped part. Each map's predictor is the one the validator reads from the global maps: the share of the box's
land pixels flooded at the 1-in-100-year period (permanent water excluded, depths above 0.05 m) × the depth–damage
fraction at their mean depth. The European maps replace the global ones inside their coverage unless they rank the
observed floods worse: refused when the 95th percentile of the paired-bootstrap difference (European − global; 2,000
resamples, seed 7) is below zero for the rank correlation or for the AUC. The product owner decided (2026-10-16) that a
passed check adopts them; the result is written into the layer's registry entry. Raster reads go through the isolated
sampler (services.geo.raster_sampler, E170)."""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from services.loss import registry

KEY = "jrc_river_flood_europe"
LAYERS_FILE = registry.REF / "hazard_intensity_layers.json"


def europe_box(b) -> Optional[tuple[float, float]]:
    """(wet share, mean wet depth) of the European 1-in-100-year map over a lon/lat polygon; None off the map or when
    the box has no land."""
    from ml.scoring.flood_jrc import DEPTH_MIN_M
    from services.geo import raster_sampler
    L = registry.layer(KEY)
    d = registry.ROOT / L["files"]["dir"]
    z = raster_sampler.zonal(str(d / L["files"]["pattern"].format(rp=100)), list(b.exterior.coords), above=DEPTH_MIN_M,
                             exclude={"path": str(d / L["files"]["water"]), "value": 1})
    if z is None or not z["inside"]:
        return None
    return z["present"] / z["inside"], (z["sum"] / z["present"] if z["present"] else 0.0)


def verdict(spread: dict) -> bool:
    """True unless the European maps rank the floods worse beyond sampling noise (the registered rule)."""
    return not (spread["rho"][1] < 0 or spread["auc"][1] < 0)


def compare() -> dict:
    """Both maps on the validator's nodes, per event and pooled, and the registered rule's verdict."""
    import pandas as pd

    from ml.scoring.flood_jrc import TileSet, flood_score
    from scripts.backtest_flood_ems import EVENTS, ems_extent, ems_mapped
    from services.loss.refine30 import _metrics, _paired_bootstrap
    from services.validation.validators.flood_jrc import PANEL, event_nodes, observed_share
    rule = json.loads((registry.REF / "loss_protocol.json").read_text(encoding="utf-8"))["europe_maps_check"]
    data = pd.read_parquet(PANEL)
    tiles = TileSet()
    pg, pe, obs, per_event, skipped = [], [], [], {}, 0
    for ev in EVENTS:
        ext, _fc = ems_extent(ev)
        mapped = ems_mapped(ev)
        m = data.event == ev["name"]
        if ext is None or ext.is_empty or mapped is None or not m.any():
            continue
        g, e, o = [], [], []
        for _c, b in event_nodes(data.loc[m, "h3_cell"], ev, mapped):
            st, eu = tiles.stats(b), europe_box(b)
            if st is None or eu is None:
                skipped += 1
                continue
            g.append(flood_score(*st[100][:2])); e.append(flood_score(*eu)); o.append(observed_share(ext, mapped, b))
        if len(g) >= 10:
            per_event[ev["name"]] = {"global": _metrics(g, o), "europe": _metrics(e, o)}
        pg += g; pe += e; obs += o
    tiles.close()
    spread = _paired_bootstrap(pg, pe, obs)
    return {"protocol": "europe_maps_check", "registered": rule["registered"], "run": date.today().isoformat(),
            "rule": rule["rule"], "pooled": {"global": _metrics(pg, obs), "europe": _metrics(pe, obs)},
            "difference_europe_minus_global_90pct_interval": spread, "per_event": per_event,
            "nodes_without_both_maps": skipped, "passed": verdict(spread)}


def record(result: dict) -> None:
    """The check into the layer's registry entry: 'in_use' when it passed (the product owner's decision of 2026-10-16
    adopts a passed check), 'refused' otherwise — the global maps then stay everywhere."""
    doc = json.loads(LAYERS_FILE.read_text(encoding="utf-8"))
    L = doc["layers"][KEY]
    L["test"] = result
    L["status"] = "in_use" if result["passed"] else "refused"
    L["adoption"] = (f"in use inside coverage_countries since {result['run']}: the registered check did not refuse it "
                     "(product owner's decision, 2026-10-16)") if result["passed"] else \
        f"refused {result['run']}: it ranked the observed floods worse than the global maps beyond sampling noise"
    LAYERS_FILE.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

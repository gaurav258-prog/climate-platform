"""Where a projected loss run reads its hazard — the platform's one timeline (services.reference.warming_axis; the product
owner's decisions of 2026-10-22). A hazard source's maps are placed by the warming each represents, as its layer
declares (registry 'use' → 'timeline'):

  present     its present-day map — made from observations, measured on the observed record over its years
  each map    a pathway × period map — climate-model output, measured on the assessed series of the SSP with its forcing

A pathway-year (its horizon's assessed level) reads the two maps that bracket its warming, whatever pathway made them,
blended by how far its warming lies between theirs; warmer than every map it is a named gap, never extrapolated.

  datasets(layer_key)                  {key: {level, variant | pathway + period}} — 'present' and '<pathway>:<period>'
  place(layer_key, scenario, horizon)  {target, lower, upper, w, levels}; None when warmer than every map
"""
from __future__ import annotations

from typing import Optional

from services.loss import registry
from services.reference import warming_axis as axis


def datasets(layer_key: str) -> dict[str, dict]:
    L = registry.layer(layer_key)
    t = L["use"]["timeline"]
    P = L["present"]
    out = {"present": {"level": axis.window("observed", *t["present_years"])["central"],
                       "variant": {"scenario": P["scenario"], "period": P["year"], "climate_model": P["model"]}}}
    for pathway, ssp in t["maps"].items():
        for period, (first, last) in t["periods"].items():
            out[f"{pathway}:{period}"] = {"level": axis.window("assessed", first, last, ssp)["central"],
                                          "pathway": pathway, "period": period}
    return out


def place(layer_key: str, scenario: str, horizon: str) -> Optional[dict]:
    target = axis.anchor(scenario, horizon)
    ds = datasets(layer_key)
    levels = {k: v["level"] for k, v in ds.items()}
    b = axis.bracket(target["central"], levels)
    base = {"axis": axis.spec()["version"], "target": target, "levels": levels}
    if b is None:
        return None
    lower, upper, w = b
    return {**base, "lower": lower, "upper": upper, "w": w}


def warmest(layer_key: str) -> tuple[str, float]:
    """The warmest map of a layer: its key and level — what a pathway-year beyond it is named against."""
    k, v = max(((k, d["level"]) for k, d in datasets(layer_key).items()), key=lambda kv: kv[1])
    return k, v

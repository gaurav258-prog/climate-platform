"""Projected loss (the product owner's decisions of 2026-10-07, 2026-10-22 and 2026-10-23, recorded with each source's
layer under 'use'): one asset and peril in a pathway-year's climate, read from the peril's registered projection source
on the platform's one timeline (services.loss.timeline).

  SOURCES                      each peril's projection source: river flood — WRI Aqueduct riverine maps (five climate
                               models); coastal flood — WRI Aqueduct coastal maps (sea-level rise at three percentiles);
                               tropical cyclone — the STORM Climate Change winds (four climate models)
  members(layer)               the source's members: its climate models, or its sea-level-rise percentiles
  variants(layer)              every map of the source: its present day (unless another layer holds it) and each
                               pathway × period × member
  assess(session, asset, …)    the figure: for each member, the hazard blended between the two maps that bracket the
                               pathway-year's warming (the present day, made from observations, is the same for every
                               member) — water depth for a flood map, the wind at each return period for a wind map — and
                               the adopted curve applied. Central: the member the source names ('central_member'), else
                               the median of the members ranked by expected yearly loss (the mean of the two middle ones
                               when they are even); low and high: the lowest curve-low and highest curve-high of the
                               members, per return period and for the yearly figure. Beside it, the same source's present
                               figure — the only figure it is compared with.
  gap(peril, scenario, horizon)  why a projected run has no figure — or None
  inputs(peril, scenario, horizon) what a projected run read, recorded with it

A scenario or horizon warmer than every map of the source, and a peril without a projection source, is a named gap."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from services.loss import gaps, registry

SOURCES = {"flood": "aqueduct_river_flood", "coastal_flood": "aqueduct_coastal_flood", "storm": "storm_cc_wind"}


def members(L: dict) -> list[str]:
    return list(L.get("members") or L["models"])


def present_variant(L: dict) -> dict:
    P = L["present"]
    return {"scenario": P["scenario"], "period": P["year"], "climate_model": P["model"]}


def present_layer(key: str) -> str:
    """The layer holding a source's present day: another layer it names (the STORM future set's present climate is the
    present set's maps), else its own."""
    return registry.layer(key)["present"].get("layer") or key


def variants(key: str) -> list[dict]:
    L = registry.layer(key)
    own = [] if L["present"].get("layer") else [present_variant(L)]
    return own + [{"scenario": s, "period": p, "climate_model": m}
                  for s in L["pathways"] for m in members(L) for p in L["periods"]]


def gap(peril: str, scenario: str, horizon: str) -> Optional[dict]:
    return gaps.projection(peril, scenario, horizon, SOURCES.get(peril))


def _depth(L: dict) -> bool:
    return L["metric"] == "water_depth"


def blend(lower: dict[int, dict], upper: dict[int, dict], w: float, L: dict) -> dict[int, dict]:
    """The hazard between two maps, by warming (the product owner's decision of 2026-10-22), per return period held by
    both. A flood map: the water depth — a dry pixel's depth is none — blended linearly by w, the pixel wet where the
    blended depth is above the source's dry level. A wind map: the wind blended linearly by w."""
    out = {}
    for rp in sorted(set(lower) & set(upper)):
        a, b = lower[rp], upper[rp]
        if _depth(L):
            da = (a["cell_fraction"] or 0.0) * (a["cell_mean"] or 0.0)
            db = (b["cell_fraction"] or 0.0) * (b["cell_mean"] or 0.0)
            depth = da + (db - da) * w
            wet = depth > L["dry_below"]
            out[rp] = {"status": "sampled", "cell_fraction": 1.0 if wet else 0.0, "cell_mean": depth if wet else 0.0}
        else:
            va, vb = float(a["value"] or 0.0), float(b["value"] or 0.0)
            out[rp] = {"status": "sampled", "value": va + (vb - va) * w}
    return out


def central(per_member: dict[str, dict], L: dict) -> dict:
    """The central figure: the member the source names, else the median of the members by expected yearly loss — for
    an even count the mean of the two middle members' figures, per return period and for the yearly figure."""
    named = L["use"].get("central_member")
    if named:
        return per_member[named]
    ranked = sorted(per_member.values(), key=lambda x: x["eal_eur"])
    n = len(ranked)
    if n % 2:
        return ranked[n // 2]
    a, b = ranked[n // 2 - 1], ranked[n // 2]
    return {"eal_eur": (a["eal_eur"] + b["eal_eur"]) / 2,
            "loss_at_rp": {rp: {"central": (a["loss_at_rp"][rp]["central"] + b["loss_at_rp"][rp]["central"]) / 2}
                           for rp in a["loss_at_rp"]}}


def assess(session: Session, asset: dict, peril: str, family_key: Optional[str], scenario: str, horizon: str) -> dict:
    from services.loss import engine, timeline
    base = {"peril": peril, "exposed_value_eur": None, "occupancy": None, "curve_key": None}
    why = gap(peril, scenario, horizon)
    if why:
        return {**base, **why}
    if asset.get("position"):      # a holding is never a physical asset (E307): its first reason
        return {**base, **gaps.gap(asset["no_asset_value"])}
    if asset.get("latitude") is None or asset.get("longitude") is None:
        return {**base, **gaps.gap("loss.gap.no_location")}
    if not family_key:             # as today's run: no adopted curves, nothing read — the choice comes first (E324)
        return {**base, **gaps.gap("loss.gap.no_curves_chosen", peril=gaps.peril_name(peril))}
    key = SOURCES[peril]
    L = registry.layer(key)
    lat, lon = float(asset["latitude"]), float(asset["longitude"])
    pkey = present_layer(key)
    today = engine._samples(session, pkey, registry.layer(pkey)["version"], lat, lon, present_variant(L))
    why = gaps.intensity(today, pkey)
    if why:
        return {**base, **why}
    base, ctx = engine._resolve(session, asset, peril, family_key, base)
    if ctx is None:
        return base
    where = timeline.place(key, scenario, horizon)
    per = registry.divisor(key, ctx["family"]["metric"])
    if per is None or registry.divisor(pkey, ctx["family"]["metric"]) != per:
        return {**base, **gaps.gap("loss.gap.curves_not_usable", peril=gaps.peril_name(peril))}

    def read(dataset: str, m: str) -> dict[int, dict]:
        if dataset == "present":
            return today
        pathway, period = dataset.split(":")
        return engine._samples(session, key, L["version"], lat, lon,
                               {"scenario": pathway, "period": period, "climate_model": m})
    per_member = {}
    for m in members(L):
        lo, hi = read(where["lower"], m), read(where["upper"], m)
        why = gaps.intensity(lo, key if where["lower"] != "present" else pkey) or gaps.intensity(hi, key)
        if why:
            return {**base, **why}
        rows, why = engine._rp_figures(ctx["curve"], ctx["value"], blend(lo, hi, where["w"], L), key, per)
        if rows is None:
            return {**base, **why}
        per_member[m] = engine._summary(rows)
    today_rows, why = engine._rp_figures(ctx["curve"], ctx["value"], today, pkey, per)
    if today_rows is None:
        return {**base, **why}
    mid = central(per_member, L)
    rps = sorted(mid["loss_at_rp"], key=int)
    out = {**base, "gap": None, "standing": engine.standing(ctx["family"], ctx["country"], ctx["curve"], peril),
           "eal_eur": round(mid["eal_eur"], engine.CENTS),
           "eal_low_eur": min(x["eal_low_eur"] for x in per_member.values()),
           "eal_high_eur": max(x["eal_high_eur"] for x in per_member.values()),
           "loss_at_rp": {rp: {"low": min(x["loss_at_rp"][rp]["low"] for x in per_member.values()),
                               "central": round(mid["loss_at_rp"][rp]["central"], engine.CENTS),
                               "high": max(x["loss_at_rp"][rp]["high"] for x in per_member.values())} for rp in rps},
           "eal_same_source_today_eur": engine._summary(today_rows)["eal_eur"],
           "model_eal": {m: x["eal_eur"] for m, x in per_member.items()}}
    if _depth(L):
        out.update(flood_layer=key, **gaps.protection("loss.protection.not_projected"))
    return out


def inputs(peril: str, scenario: str, horizon: str) -> Optional[dict]:
    """What a projected run read for a peril, recorded with it: the source, and where the pathway-year sits on the
    timeline — its warming, the two maps that bracket it and the weight between them (or that it is warmer than every
    map). None for a peril without a projection source."""
    from services.loss import timeline
    key = SOURCES.get(peril)
    if key is None:
        return None
    L = registry.layer(key)
    use = L["use"]
    return {"key": key, "version": L["version"], "present_layer": present_layer(key), "members": members(L),
            "decided": use["decided"], "compared_with": use["compared_with"], "range": use["range"],
            "reads_as": L.get("reads_as") or L.get("wind_field"), "licence": L["licence"], "timeline": use["timeline"],
            "placement": timeline.place(key, scenario, horizon)}

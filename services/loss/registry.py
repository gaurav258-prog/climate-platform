"""The loss foundation's reference registries (E169), read and checked in one place:

  data/reference/hazard_intensity_layers.json   intensity layers: peril, metric, unit, version, return periods, source
  data/reference/event_sets.json                stochastic event sets: source, DOI, licence, simulated years, files
  data/reference/occupancy.json                 building-use classes and the declared crosswalk from asset types

A layer or event set is used only as registered: its key and version are written with every sample and loss run."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "data" / "reference"
UNITS = {"m", "m/s"}


class RegistryError(ValueError):
    pass


@lru_cache(maxsize=1)
def layers() -> dict[str, dict]:
    return json.loads((REF / "hazard_intensity_layers.json").read_text(encoding="utf-8"))["layers"]


@lru_cache(maxsize=1)
def event_sets() -> dict[str, dict]:
    return json.loads((REF / "event_sets.json").read_text(encoding="utf-8"))["event_sets"]


@lru_cache(maxsize=1)
def _occupancy() -> dict:
    return json.loads((REF / "occupancy.json").read_text(encoding="utf-8"))


def occupancy_classes() -> tuple[str, ...]:
    return tuple(_occupancy()["classes"])


def layer(key: str) -> dict:
    try:
        return layers()[key]
    except KeyError:
        raise RegistryError(f"intensity layer '{key}' is not registered (data/reference/hazard_intensity_layers.json)")


def occupancy_of(stated: Optional[str], table: str, asset_type: Optional[str]) -> tuple[Optional[str], str]:
    """(occupancy, basis): the institution's statement first; else the declared crosswalk for an unambiguous asset
    type; else (None, why) — never a guess."""
    if stated:
        if stated not in occupancy_classes():
            raise RegistryError(f"occupancy '{stated}' is not a class of data/reference/occupancy.json")
        return stated, "stated"
    walk = _occupancy()["crosswalk"].get(table, {})
    if asset_type and asset_type in walk:
        return walk[asset_type], f"crosswalk: {table} '{asset_type}'"
    return None, (f"no occupancy stated, and the asset type '{asset_type}' does not determine one" if asset_type
                  else "no occupancy stated and no asset type")


def check() -> list[str]:
    """Every problem in the registries; empty when they are sound."""
    from core.types import HazardType
    perils = {h.value for h in HazardType}
    out = []
    for k, L in layers().items():
        if L["peril"] not in perils:
            out.append(f"layer {k}: peril '{L['peril']}' is not a hazard type")
        if L["unit"] not in UNITS:
            out.append(f"layer {k}: unit '{L['unit']}' is not one of {sorted(UNITS)}")
        rps = L["return_periods"]
        if not rps or rps != sorted(set(rps)) or rps[0] <= 1:
            out.append(f"layer {k}: return periods must be distinct, ascending and above 1 year")
        if L.get("derived_from") and L["derived_from"] not in event_sets():
            out.append(f"layer {k}: derived from unregistered event set '{L['derived_from']}'")
        if not L.get("licence") and not L.get("licence_status"):
            out.append(f"layer {k}: neither a licence nor its verification status")
    for k, E in event_sets().items():
        if E["peril"] not in perils:
            out.append(f"event set {k}: peril '{E['peril']}' is not a hazard type")
        if not (E.get("licence") and E.get("doi") and E.get("years_simulated", 0) > 0):
            out.append(f"event set {k}: needs a licence, a DOI and the simulated years")
    occ = _occupancy()
    for table, walk in occ["crosswalk"].items():
        for t, c in walk.items():
            if c not in occ["classes"]:
                out.append(f"crosswalk {table} '{t}': '{c}' is not an occupancy class")
    return out

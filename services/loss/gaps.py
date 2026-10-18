"""The loss engine's messages (UI standard, product owner 2026-10-16): every reason a figure is missing, the defence
basis and the publisher's caution are codes of the message catalogue (core/messages.py, data/reference/messages.en.json)
with their values in customer words — a map's name, a hazard's name, a country's name — never an internal key. A result
keeps the code and its values (gap_code, gap_params; protection_code; caution_code), so a screen renders the label and
its detail, and groups results by code."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from core import messages
from services.loss import registry


def gap(code: str, **params: Any) -> dict:
    """The fields a result carries for a missing figure."""
    return {"gap": messages.label(code, **params), "gap_code": code, "gap_params": params}


def peril_name(peril: str) -> str:
    return messages.name("peril", peril)


def map_name(layer_key: str) -> str:
    return registry.layer(layer_key)["name"]


def country_name(iso2: str) -> str:
    from services.reference.countries import country_name as _name
    return _name(iso2) or iso2


def intensity(samples: dict, layer_key: str) -> Optional[dict]:
    """Why a layer gives no intensity at a location — not read yet, or off the map — or None."""
    if not samples:
        return gap("loss.gap.not_read", map=map_name(layer_key))
    if any(r["status"] != "sampled" for r in samples.values()):
        return gap("loss.gap.outside_map", map=map_name(layer_key))
    return None


def country(session: Session, asset: dict, stated: str) -> dict:
    """Why the asset has no country a curve can be chosen by — with the country its coordinates fall in as a hint,
    never as a substitute for what the book states."""
    from services.intake.observations import _country_from_location
    where = _country_from_location(session, asset)
    hint = f" Its coordinates are in {country_name(where)}." if where else ""
    if not stated:
        return gap("loss.gap.country_missing", hint=hint)
    return gap("loss.gap.country_group", stated=stated, hint=hint)


def occupancy(asset_type: Optional[str]) -> dict:
    return gap("loss.gap.use_unknown", type=asset_type) if asset_type else gap("loss.gap.use_and_type_unknown")


def projection(peril: str, scenario: str, horizon: str, use: dict) -> Optional[dict]:
    """Why a projected run has no figure for this peril, scenario and horizon — or None when the source serves it."""
    if peril != "flood":
        return gap("loss.gap.no_projection_peril", peril=peril_name(peril))
    if use["scenario_map"].get(scenario) is None:
        return gap("loss.gap.no_projection_scenario", scenario=messages.name("scenario", scenario))
    if use["horizon_map"].get(horizon) is None:
        return gap("loss.gap.no_projection_year", year=horizon)
    return None


def protection(code: str, years: Optional[float] = None) -> dict:
    """The defence basis a flood result carries: its code and its label."""
    params = {"years": f"{years:g}"} if years is not None else {}
    return {"protection_code": code, "protection_basis": messages.label(code, **params)}


CAUTION = "loss.caution.depth_may_be_overstated"


def caution(flagged: bool) -> dict:
    return {"caution_code": CAUTION, "caution": messages.label(CAUTION)} if flagged else {}

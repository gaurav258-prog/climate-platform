"""The value a loss figure is a share of, where the book states it only with the land in it (the product owner's decisions
of 2026-10-25) — kept beside the engine (services/loss/engine.py), which reads it for every run.
"""
from __future__ import annotations

BUILDING_SHARE_BOOKS = ("banking", "realestate")   # a stated value with the land in it: a loan's appraised value, a property's


def with_building_share(assets: list[dict], book: str, settings: dict) -> list[dict]:
    """For an organisation that adopts loss_building_share (the product owner's decisions of 2026-10-25): an asset whose
    book states no building value takes its stated value times the official building share for its place
    (services/reference/building_share.py), recorded on its figures (value_basis). A building value the book states
    always comes first; a place with no official share keeps its gap; an insurer's or a site's values are never split."""
    if settings.get("loss_building_share") != "official_statistics" or book not in BUILDING_SHARE_BOOKS:
        return assets
    from services.reference.building_share import share_at
    out = []
    for a in assets:
        stated = a.get("value")
        if a.get("building_value") or not stated or stated <= 0 or a.get("position"):
            out.append(a)
            continue
        s = share_at(a.get("country"), a.get("latitude"), a.get("longitude"))
        if s is None:
            out.append(a)
            continue
        derived = round(stated * s["share"], 2)
        basis = {"code": "official_building_share", "stated_value_eur": stated,
                 **{k: s[k] for k in ("share", "source", "area", "period", "lower_bound")}}
        out.append({**a, "building_value": derived, "asset_value": a.get("asset_value") or derived, "value_basis": basis})
    return out

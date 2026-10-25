"""The share of a stated property value that is the building, from official statistics (the product owner's decisions of
2026-10-25) — data/reference/building_share.json, built by scripts/build_building_share.py from the publishers' files.

  share_at(country, lat, lon)   {share, source, area, period, lower_bound, ...} for the place, or None where no official
                                figure exists: Spain by province (the Catastro's construction over total cadastral value,
                                all urban uses), Germany nationally (households' dwellings over dwellings and all their
                                land — a lower bound); anywhere else none

Read by the loss engine only for an organisation that adopts it (calc setting loss_building_share), for a book whose
stated value includes the land (a loan's appraised value, a property's value) and states no building value.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "building_share.json"


@lru_cache(maxsize=1)
def table() -> dict:
    return json.loads(FILE.read_text())


def _source(key: str) -> dict:
    return next(s for s in table()["sources"] if s["key"] == key)


def share_at(country: Optional[str], lat: Optional[float], lon: Optional[float]) -> Optional[dict]:
    c = (country or "").strip().upper()
    t = table()
    if c in t["by_country"]:
        row = t["by_country"][c]
        return {"share": row["share"], "source": row["source"], "area": c, "lower_bound": bool(row.get("lower_bound")),
                "period": str(row.get("year")), "dataset": _source(row["source"])["dataset"]}
    if lat is None or lon is None or not t["by_nuts3"]:
        return None
    from services.geo.regions import region_for
    r = region_for(float(lat), float(lon))
    row = t["by_nuts3"].get(r["key"]) if r.get("kind") == "nuts3" else None
    if row is None or r.get("country") != c:
        return None
    return {"share": row["share"], "source": row["source"], "area": row["area"], "region": r["key"], "lower_bound": False,
            "period": "2026 (values at 31 Dec 2025)", "dataset": _source(row["source"])["dataset"]}

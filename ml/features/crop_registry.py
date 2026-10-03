"""The crop–origin registry (data/reference/crop_registry.json, E151) — the one place a crop's biology and its FAOSTAT
item are stated. A crop not in the registry is refused (UnknownCrop), never guessed from its name."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "crop_registry.json"


class UnknownCrop(KeyError):
    pass


@lru_cache(maxsize=1)
def registry() -> dict:
    return json.loads(REF.read_text(encoding="utf-8"))


def crops() -> list[dict]:
    return registry()["crops"]


def crop(commodity: str) -> dict:
    for c in crops():
        if c["commodity"] == commodity:
            return c
    raise UnknownCrop(f"'{commodity}' is not in the crop registry (data/reference/crop_registry.json)")


def is_alternate_bearing(commodity: str) -> bool:
    return crop(commodity)["life_cycle"] == "perennial_alternate_bearing"


def fao_items() -> dict[str, str]:
    """{FAO item name: our commodity} for the crops FAOSTAT reports as one item."""
    return {c["fao_item"]: c["commodity"] for c in crops() if c.get("fao_item")}

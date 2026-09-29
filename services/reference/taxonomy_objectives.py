"""The six environmental objectives of the EU Taxonomy (Regulation (EU) 2020/852, Art. 9) — one reference list
(data/reference/taxonomy/environmental_objectives.json), read wherever an objective is accepted, validated or printed."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "taxonomy" / "environmental_objectives.json"


@lru_cache(maxsize=1)
def objectives() -> tuple[dict, ...]:
    return tuple(json.loads(_FILE.read_text())["objectives"])


def codes() -> tuple[str, ...]:
    """The objective codes in Article 9 order: ccm, cca, wtr, ce, ppc, bio."""
    return tuple(o["code"] for o in objectives())


def by_printed_heading(heading: str) -> str | None:
    """The code of the objective a template column block is printed under ('Water and marine resources (WTR)' → 'wtr')."""
    h = " ".join(heading.split()).lower()
    return next((o["code"] for o in objectives() if " ".join(o["printed"].split()).lower() == h), None)

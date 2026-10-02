"""The EUDR statement templates as printed (data/reference/regspec/eudr, captured by scripts/build_eudr_spec.py) — the
one place the statement and the simplified declaration read their wording from. Nothing printed is typed in code (E115).
"""
from __future__ import annotations

import re
from datetime import date

import services.regspec as R

FRAMEWORK = "eudr"


class SpecMissing(ValueError):
    pass


def governing(on: date | str) -> dict:
    """The version of Annexes II and III in force on a date (the reading recorded in the spec's interpretations)."""
    s = R.governing(FRAMEWORK, period_end=on)
    if s is None:
        raise SpecMissing(f"no EUDR template version is in force on {on}")
    return s


def has(spec: dict, template_id: str) -> bool:
    return any(t["id"] == template_id for t in spec["templates"])


def has_point(spec: dict, template_id: str, item_id: str) -> bool:
    return has(spec, template_id) and any(i["id"] == item_id for i in R.template(spec, template_id)["items"])


def items(spec: dict, template_id: str) -> list[dict]:
    """The printed points of a template, in printed order (heading and intro left out)."""
    return [i for i in R.template(spec, template_id)["items"] if i.get("number") is not None]


def point(spec: dict, template_id: str, item_id: str) -> dict:
    return next(i for i in R.template(spec, template_id)["items"] if i["id"] == item_id)


def quoted(label: str) -> str:
    """The words a point prescribes in quotation marks (point 5's confirmation, point 6's signature format)."""
    m = re.search(r"‘(.*)’", label)
    if not m:
        raise SpecMissing(f"no quoted wording in: {label[:60]}")
    return m.group(1)


def record(spec: dict) -> dict:
    """What a filing freezes about the version it was prepared under."""
    return {"framework": FRAMEWORK, "version": spec["version"], "act": spec["act"]["short"]}

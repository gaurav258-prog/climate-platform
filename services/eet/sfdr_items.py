"""EET fields a product's SFDR pre-contractual template already answers (data/reference/eet/sfdr_item_map.json): read
from the template answers (template_answers), so a commitment is stated once and the EET and the Annex II / III
document cannot disagree."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "eet" / "sfdr_item_map.json"


@lru_cache(maxsize=1)
def mapping() -> dict:
    return json.loads(_FILE.read_text())


def names() -> set[str]:
    """The EET fields filled from the template — never typed as an EET answer."""
    return set(mapping()["fields"])


def _value(rule: dict, answers: dict):
    a = answers.get(rule["item"])
    if a is None:
        return None
    if rule["take"] == "percent":
        return None if a.get("percent") is None else round(float(a["percent"]) / 100.0, 6)
    if rule["take"] == "ticked":
        return None if "ticked" not in a else ("Y" if a["ticked"] else "N")
    vals = [a.get("values", {}).get(lbl) for lbl in rule["labels"]]
    return None if all(v is None for v in vals) else round(sum(float(v) for v in vals if v is not None) / 100.0, 6)


def values(session: Session, fund_id: str, sfdr_classification: str | None) -> dict:
    """{eet field: value} for the product's article, from its pre-contractual answers (missing answers stay empty)."""
    from services.governance.template_answers import read
    org_id = session.execute(text("SELECT org_id::text FROM funds WHERE fund_id = CAST(:f AS uuid)"), {"f": fund_id}).scalar()
    answers = read(session, org_id, "sfdr_product", mapping()["document"], fund_id=fund_id)
    out = {}
    for name, arts in mapping()["fields"].items():
        rule = arts.get(sfdr_classification or "")
        if rule:
            v = _value(rule, answers)
            if v is not None:
                out[name] = v
    return out

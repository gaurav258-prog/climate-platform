"""Demo data: give the demo banks', insurers' and REITs' books the two building facts a flood loss needs — what each
building is used for (occupancy) and the building's own value, land excluded — as a customer's upload would state
them (product owner's decision, 2026-10-07). Without them every demo loss is a named gap.

Demo only — organisations whose name ends '(demo)'. Deterministic: every value is derived from the asset's own id and
attributes. Fills only facts that are empty — a stated value is never overwritten, and a use the asset type already
settles (data/reference/occupancy.json crosswalk) is left to the crosswalk. Declared demo assumptions:
  * building use, where the type does not settle it: hospitality and accommodation → commercial; energy, utilities,
    logistics, transportation premises, mining → industrial; 'Real estate' loans → commercial; an insurer's
    'property' policy → residential (55 %), commercial (35 %) or industrial (10 %) by the asset's id; agriculture is
    left to the crosswalk (its curve is not carried, so its loss stays a named gap)
  * building value (property and loan books; insurers state theirs already): 55–80 % of the stated property or
    appraised value — that value includes the land — by the asset's id

    venv/bin/python -m scripts.seed_demo_building_facts
"""
from __future__ import annotations

import hashlib

from sqlalchemy import text

from core.db.session import get_session
from services.loss import registry

USE_BY_TYPE = {"hospitality": "commercial", "Accommodation & food": "commercial", "energy": "industrial",
               "Electricity/utilities": "industrial", "logistics": "industrial", "Transportation": "industrial",
               "Mining & quarrying": "industrial", "Real estate": "commercial"}
INSURED_SPLIT = ((0.55, "residential"), (0.90, "commercial"), (1.00, "industrial"))
BUILDING_SHARE = (0.55, 0.80)
EXT = {"banking": "ext_banking", "realestate": "ext_realestate"}


def _u(entity_id: str, salt: str) -> float:
    return int(hashlib.sha256(f"{entity_id}:{salt}".encode()).hexdigest()[:8], 16) / 0x100000000


def use_for(r: dict) -> str | None:
    """The demo statement of building use, or None when the crosswalk settles it (or nothing should be stated)."""
    walk = registry._occupancy()["crosswalk"]["portfolio_entities.entity_type"]
    t = r["entity_type"] or ""
    if t in walk:
        return None
    if r["vertical"] == "insurance":
        u = _u(r["entity_id"], "use")
        return next(c for cut, c in INSURED_SPLIT if u < cut)
    return USE_BY_TYPE.get(t)


def building_value_for(r: dict) -> float | None:
    if r["vertical"] not in EXT or not r["value"]:
        return None
    lo, hi = BUILDING_SHARE
    return round(float(r["value"]) * (lo + (hi - lo) * _u(r["entity_id"], "building")), 2)


def main() -> None:
    with get_session() as s:
        rows = s.execute(text("""
            SELECT e.entity_id::text AS entity_id, e.vertical, e.entity_type, e.occupancy,
                   CAST(e.primary_value_eur AS FLOAT) AS value
            FROM portfolio_entities e JOIN organizations o ON o.org_id = e.org_id
            WHERE o.name LIKE '%(demo)' AND e.source = 'own' AND e.vertical IN ('banking', 'insurance', 'realestate')""")).mappings().all()
        uses = values = 0
        for r in rows:
            r = dict(r)
            use = use_for(r)
            if use and r["occupancy"] is None:
                s.execute(text("""UPDATE portfolio_entities SET occupancy = COALESCE(occupancy, :u)
                                  WHERE entity_id = CAST(:e AS uuid)"""), {"u": use, "e": r["entity_id"]})
                uses += 1
            bv = building_value_for(r)
            if bv:
                got = s.execute(text(f"""UPDATE {EXT[r['vertical']]} SET building_value_eur = COALESCE(building_value_eur, :b)
                                         WHERE entity_id = CAST(:e AS uuid) AND building_value_eur IS NULL"""),
                                {"b": bv, "e": r["entity_id"]})
                values += got.rowcount
    print(f"demo building facts: building use stated for {uses}, building value for {values} of {len(rows)} assets")


if __name__ == "__main__":
    main()

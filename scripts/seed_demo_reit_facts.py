"""Demo data: give every demo REIT's buildings the facts EU Taxonomy activity 7.7 needs to decide alignment
(data/reference/taxonomy/criteria/ccm_7_7.json) and a gross rental revenue, so the demo shows the Annex II templates
with aligned (A.1), not-aligned (A.2) and undetermined buildings.

Demo only — organisations of type 'reit' whose name ends '(demo)'. Deterministic: every value is derived from the
building's own id and attributes. Fills only facts that are empty — a stated value is never overwritten. Declared
demo assumptions:
  * gross rental revenue = NOI ÷ (1 − 0.30): a 30 % operating-cost ratio (the book states NOI only)
  * heating / air-conditioning rated output by building type and value (logistics and light industrial smaller)
  * an adaptation plan for about 60 % of buildings; energy-performance monitoring for about 75 % of large ones;
    top-15 %-of-stock evidence for about 1 in 8 buildings below EPC A (stated false for the rest); a building built
    after 2020 meets the Section 7.1 criteria in about half the cases
  * minimum safeguards: the demo undertaking states it is compliant

    venv/bin/python -m scripts.seed_demo_reit_facts
"""
from __future__ import annotations

import hashlib

from sqlalchemy import text

from core.db.session import get_session

_OPEX_RATIO = 0.30
_KW_BY_TYPE = {"office": 420, "retail": 360, "logistics": 180, "light_industrial": 220, "multifamily": 250}


def _u(entity_id: str, salt: str) -> float:
    return int(hashlib.sha256(f"{entity_id}:{salt}".encode()).hexdigest()[:8], 16) / 0x100000000


def facts_for(r: dict) -> dict:
    eid = r["entity_id"]
    out: dict = {"adaptation_plan_in_place": _u(eid, "plan") < 0.60}
    if r["annual_noi_eur"] is not None:
        out["annual_gross_rental_revenue_eur"] = round(float(r["annual_noi_eur"]) / (1 - _OPEX_RATIO), 2)
    base = _KW_BY_TYPE.get((r["entity_type"] or "").lower(), 200)
    out["heating_rated_output_kw"] = round(base * (0.5 + _u(eid, "kw")), 1)
    if out["heating_rated_output_kw"] > 290:
        out["energy_performance_monitoring"] = _u(eid, "mon") < 0.75
    if (r["epc_rating"] or "").upper() != "A":
        out["ped_top15_evidence"] = _u(eid, "ped") < 0.125
    if r["year_built"] and int(r["year_built"]) > 2020:
        out["meets_new_building_criteria"] = _u(eid, "new") < 0.5
    return out


def main() -> None:
    with get_session() as s:
        rows = s.execute(text("""
            SELECT e.entity_id::text AS entity_id, e.entity_type, e.year_built, CAST(x.annual_noi_eur AS FLOAT) AS annual_noi_eur,
                   x.epc_rating
            FROM portfolio_entities e
            JOIN organizations o ON o.org_id = e.org_id
            JOIN ext_realestate x ON x.entity_id = e.entity_id
            WHERE e.vertical = 'realestate' AND o.type = 'reit' AND o.name LIKE '%(demo)'""")).mappings().all()
        for r in rows:
            f = facts_for(dict(r))
            sets = ", ".join(f"{k} = COALESCE({k}, :{k})" for k in f)          # never overwrite a stated fact
            s.execute(text(f"UPDATE ext_realestate SET {sets} WHERE entity_id = CAST(:e AS uuid)"), {**f, "e": r["entity_id"]})
            s.execute(text("""UPDATE portfolio_entities SET minimum_safeguards_status = COALESCE(minimum_safeguards_status, 'compliant')
                              WHERE entity_id = CAST(:e AS uuid)"""), {"e": r["entity_id"]})
    print(f"demo EU Taxonomy 7.7 facts: {len(rows)} buildings across the demo REITs")


if __name__ == "__main__":
    main()

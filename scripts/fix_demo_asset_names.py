"""Rename the demo population's assets that were named with a map-grid code ('hex 848f28… property 125') or a type code
('Brindisi residential_real_estate 122'), and the demo bank counterparties named after them. The seed
(scripts/seed_demo_population.py) now names an asset by where it is — its NUTS-3 region, or its country outside the
EU — its type in customer words and its number; this applies the same rule to the rows already in the database, and
gives the grid-named rows their region's customer name ('Malaysia · 2.9°N 101.6°E').

Only rows still in the seed's own form are touched (name = region, type, number), and only when the region the platform
derives from the row's cell is the one the row holds. Idempotent: a second run finds nothing to change. Local demo only.

    venv/bin/python -m scripts.fix_demo_asset_names
"""
from __future__ import annotations

import re

import h3
from sqlalchemy import text

from core.db.session import SessionLocal
from scripts.seed_demo_population import asset_name
from services.geo.regions import region_for

NUMBER = re.compile(r" (\d+)$")


def renames(s) -> list[dict]:
    """The rows to rename: {id, org, old, new, old_region, new_region}."""
    rows = s.execute(text("""
        SELECT e.entity_id::text AS id, e.org_id::text AS org, e.entity_name AS name, e.entity_type AS et,
               e.region, e.h3_cell AS cell
        FROM portfolio_entities e JOIN organizations o ON o.org_id = e.org_id
        WHERE o.name LIKE '%(demo)' AND e.source = 'own' AND e.h3_cell IS NOT NULL AND e.region IS NOT NULL
          AND left(e.entity_name, length(e.region) + 1) = e.region || ' '""")).mappings().all()
    out = []
    for r in rows:
        m = NUMBER.search(r["name"])
        if not m or r["name"] != f"{r['region']} {r['et'] or 'asset'} {m.group(1)}":
            continue                                                    # not in the seed's own form: not ours to rename
        reg = region_for(*h3.cell_to_latlng(r["cell"]))
        held = reg["name"] if reg["kind"] == "nuts3" else f"hex {reg['key'][:6]}…"
        if r["region"] not in (held, reg["name"]):
            continue                                                    # the row's region is not the one its cell gives
        new = asset_name(reg["place"], r["et"], int(m.group(1)))
        if new != r["name"] or reg["name"] != r["region"]:
            out.append({"id": r["id"], "org": r["org"], "old": r["name"], "new": new,
                        "old_region": r["region"], "new_region": reg["name"]})
    return out


def run() -> None:
    s = SessionLocal()
    try:
        todo = renames(s)
        n_cp = 0
        for x in todo:
            s.execute(text("""UPDATE portfolio_entities SET entity_name = :new, region = :reg, updated_at = now()
                              WHERE entity_id = CAST(:id AS uuid)"""), {"new": x["new"], "reg": x["new_region"], "id": x["id"]})
            n_cp += s.execute(text("""UPDATE bank_counterparties SET counterparty_name = :new, updated_at = now()
                                      WHERE org_id = CAST(:o AS uuid) AND counterparty_name = :old"""),
                              {"new": f"{x['new']} (demo)", "old": f"{x['old']} (demo)", "o": x["org"]}).rowcount
        s.commit()
        for x in todo[:8]:
            print(f"  {x['old']}  →  {x['new']}")
        print(f"done · {len(todo)} asset(s) and {n_cp} counterparty name(s) corrected" if todo
              else "nothing to fix (already correct)")
    finally:
        s.close()


if __name__ == "__main__":
    run()

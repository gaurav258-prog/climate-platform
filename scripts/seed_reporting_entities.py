"""Seed real reporting entities per demo org and assign each org's located assets across them.

Makes the Horizon entity selector real: an analyst switches entities and the globe/KPIs/tasks re-scope to
that entity's assets. `kind` is generic (legal_entity / fund / …) per the model. Idempotent: skips an org
that already has entities. Assignment is round-robin across the org's real assets so each entity holds a
distinct, non-empty subset.

    python -m scripts.seed_reporting_entities
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from core.db.session import get_session

# org_id -> (type, [(entity_name, kind), ...])
PLAN = {
    "11111111-1111-4111-8111-111111111111": ("bank", [
        ("Meridian Bank AG", "legal_entity"), ("Meridian Leasing GmbH", "legal_entity"),
        ("Meridian Corporate Finance", "legal_entity")]),
    "22222222-2222-4222-8222-222222222222": ("insurer", [
        ("Iberia Mutual Seguros", "legal_entity"), ("Iberia Re", "legal_entity")]),
    "44444444-4444-4444-8444-444444444444": ("asset_manager", [
        ("Nordkap Global Equity Fund", "fund"), ("Nordkap EU Sustainable Fund", "fund"),
        ("Nordkap Real Assets Fund", "fund")]),
    "33333333-3333-4333-8333-333333333333": ("reit", [
        ("Stellar Logistics Fund I", "fund"), ("Stellar Logistics Fund II", "fund")]),
    "55555555-5555-4555-8555-555555555555": ("manufacturer", [
        ("Terra Foods SA", "legal_entity"), ("Terra Ingredients BV", "legal_entity")]),
}
ASSET_TABLES = {
    "bank": [("bank_assets", "asset_id")],
    "insurer": [("insurance_policies", "policy_id")],
    "asset_manager": [("assetmgmt_holdings", "holding_id")],
    "reit": [("realestate_properties", "property_id")],
    "manufacturer": [("sc_company_sites", "site_id"), ("sc_sourcing_plots", "plot_id")],
}


def main():
    with get_session() as s:
        for org, (typ, ents) in PLAN.items():
            if s.execute(text("SELECT count(*) FROM reporting_entities WHERE org_id=:o"), {"o": org}).scalar():
                print(f"{org}: entities already present; skip")
                continue
            eids = []
            for name, kind in ents:
                eid = str(uuid.uuid4())
                s.execute(text("INSERT INTO reporting_entities (entity_id, org_id, name, kind) VALUES (:e,:o,:n,:k)"),
                          {"e": eid, "o": org, "n": name, "k": kind})
                eids.append(eid)
            for tbl, idc in ASSET_TABLES[typ]:
                rows = [r[0] for r in s.execute(
                    text(f"SELECT {idc} FROM {tbl} WHERE org_id=:o ORDER BY {idc}"), {"o": org}).all()]
                for i, rid in enumerate(rows):
                    s.execute(text(f"UPDATE {tbl} SET entity_id=:e WHERE {idc}=:r"),
                              {"e": eids[i % len(eids)], "r": rid})
                print(f"  {tbl}: assigned {len(rows)} across {len(eids)} entities")
        s.commit()
    print("done")


if __name__ == "__main__":
    main()

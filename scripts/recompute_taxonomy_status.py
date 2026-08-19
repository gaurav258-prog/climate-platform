"""
Recompute ext_banking.taxonomy_status/taxonomy_activity/dnsh_assessment (see
the b9c0d1e2f3a4 migration -- this used to target bank_assets, now retired)
for every asset using the real classifier
(ml/regulatory/eu_taxonomy_classifier.py), replacing the random demo
assignment from before this existed.

Run after the loan book has been scored (seed_demo_loanbook.py already places
assets in scored cells) so the DNSH-climate-adaptation diagnostic can use each
asset's real headline_bucket, not a guess. Idempotent -- safe to re-run any
time canonical_scores changes.

Also picks up portfolio_entities.minimum_safeguards_status (see the
e6f7a8b9c0d1 migration) when an asset has one on file, so
reasoning.minimum_safeguards_verified reflects real supplied evidence
instead of always reading "not currently supplied".

Run:  .venv/bin/python scripts/recompute_taxonomy_status.py
"""
import json

from sqlalchemy import text

from core.db.session import get_session
from ml.regulatory.eu_taxonomy_classifier import classify_taxonomy

BASELINE_SCENARIO, CURRENT_HORIZON = "baseline", "current"


def main():
    with get_session() as s:
        assets = s.execute(text("""
            SELECT e.entity_id AS asset_id, e.nace_code, e.minimum_safeguards_status, x.resilience_rating
            FROM portfolio_entities e
            JOIN ext_banking x ON x.entity_id = e.entity_id
            WHERE e.vertical = 'banking'
        """)).mappings().all()

        headline_by_asset = {}
        risks = s.execute(text("""
            SELECT entity_id AS asset_id, physical_risk_score AS score, risk_bucket
            FROM v_portfolio_entity_physical_risk
            WHERE vertical = 'banking' AND scenario = :s AND time_horizon = :h
              AND hazard_type != 'heat_acute'
        """), {"s": BASELINE_SCENARIO, "h": CURRENT_HORIZON}).mappings().all()
        for r in risks:
            cur = headline_by_asset.get(r["asset_id"])
            if cur is None or r["score"] > cur["score"]:
                headline_by_asset[r["asset_id"]] = r

        updates = []
        counts = {"eligible": 0, "not_eligible": 0, "not_assessed": 0}
        for a in assets:
            headline = headline_by_asset.get(a["asset_id"])
            tax = classify_taxonomy(
                a["nace_code"],
                headline_bucket=headline["risk_bucket"] if headline else None,
                resilience_rating=a["resilience_rating"],
                minimum_safeguards_status=a["minimum_safeguards_status"],
            )
            counts[tax["status"]] = counts.get(tax["status"], 0) + 1
            updates.append({
                "asset_id": a["asset_id"],
                "status": tax["status"],
                "activity": tax["activity_ref"],
                "reasoning": json.dumps(tax["reasoning"]),
            })

        s.execute(text("""
            UPDATE ext_banking
            SET taxonomy_status = :status,
                taxonomy_activity = COALESCE(:activity,
                    (SELECT sector FROM portfolio_entities WHERE entity_id = :asset_id)),
                dnsh_assessment = CAST(:reasoning AS jsonb)
            WHERE entity_id = :asset_id
        """), updates)

        print(f"recomputed taxonomy status for {len(updates)} assets: {counts}")


if __name__ == "__main__":
    main()

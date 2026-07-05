"""
Recompute bank_assets.taxonomy_status/taxonomy_activity/dnsh_assessment for
every asset using the real classifier (ml/regulatory/eu_taxonomy_classifier.py),
replacing the random demo assignment from before this existed.

Run after the loan book has been scored (seed_demo_loanbook.py already places
assets in scored cells) so the DNSH-climate-adaptation diagnostic can use each
asset's real headline_bucket, not a guess. Idempotent -- safe to re-run any
time canonical_scores changes.

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
            SELECT asset_id, nace_code, resilience_rating
            FROM bank_assets
        """)).mappings().all()

        headline_by_asset = {}
        risks = s.execute(text("""
            SELECT asset_id, CAST(physical_risk_score AS FLOAT) AS score, risk_bucket
            FROM v_bank_asset_physical_risk
            WHERE scenario = :s AND time_horizon = :h
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
            )
            counts[tax["status"]] = counts.get(tax["status"], 0) + 1
            updates.append({
                "asset_id": a["asset_id"],
                "status": tax["status"],
                "activity": tax["activity_ref"],
                "reasoning": json.dumps(tax["reasoning"]),
            })

        s.execute(text("""
            UPDATE bank_assets
            SET taxonomy_status = :status,
                taxonomy_activity = COALESCE(:activity, sector),
                dnsh_assessment = CAST(:reasoning AS jsonb)
            WHERE asset_id = :asset_id
        """), updates)

        print(f"recomputed taxonomy status for {len(updates)} assets: {counts}")


if __name__ == "__main__":
    main()

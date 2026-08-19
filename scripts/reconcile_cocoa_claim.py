"""Reconcile the recorded cocoa validation claim to the LIVE engine output.

The anti-circularity guard (tests/integration/test_validation_claim_is_not_circular.py) enforces that
`sc_model_validation.model_prod_shock_pct` for 'Cocoa 2023/24' equals what the engine actually computes
today — so the Trust page can never advertise a world-shock figure the product no longer produces. When a
later score re-fit moves the engine (e.g. 8.82 → 8.76), the recorded claim must follow it.

This is the reproducible form of that reconciliation: it reads the live engine, writes the (signed)
magnitude into the record, and appends a dated note. Idempotent — a no-op once the record already matches.
It NEVER touches the observed figure, so the claim stays non-circular (model ≠ observed) and must still
beat the independent measurement (FAOSTAT −8.88) on its own.

    python -m scripts.reconcile_cocoa_claim
"""
from sqlalchemy import text

from core.db.session import get_session
from services.intelligence.supply_cogs import project_org_supply


def main() -> None:
    with get_session() as s:
        org = s.execute(text("SELECT org_id FROM organizations WHERE name ILIKE '%Terra%' LIMIT 1")).scalar()
        if org is None:
            print("No agriculture demo org — nothing to reconcile.")
            return
        live = project_org_supply(s, org)
        cocoa = next((c for c in live.commodities if c.commodity == "Cocoa"), None)
        if cocoa is None or cocoa.global_shock_pct is None:
            print("Cocoa not scored in this DB — nothing to reconcile.")
            return

        rec = s.execute(text("""
            SELECT model_prod_shock_pct, observed_prod_shock_pct
            FROM sc_model_validation WHERE event = 'Cocoa 2023/24' AND passed LIMIT 1
        """)).mappings().first()
        if rec is None:
            print("No passing 'Cocoa 2023/24' validation row — nothing to reconcile.")
            return

        engine = round(float(cocoa.global_shock_pct), 3)
        observed = float(rec["observed_prod_shock_pct"])            # signed, e.g. -8.88
        recorded = float(rec["model_prod_shock_pct"])
        signed_engine = -abs(engine) if observed < 0 else abs(engine)  # match the column's sign convention

        if abs(abs(recorded) - engine) <= 0.005:
            print(f"Already in sync: recorded {recorded} ≈ engine {engine}. No change.")
            return
        if signed_engine == observed:
            # would make the claim circular — refuse rather than silently create a copy
            raise SystemExit(f"Refusing: engine {signed_engine} equals the observed {observed} — "
                             "that would be a circular claim, not a backtest.")

        note = (f" (Reconciled: engine re-fit moved the modelled world shock to {engine}% on the current "
                f"scores; record synced to the live engine — vs FAOSTAT {abs(observed)}%, "
                f"{abs(abs(signed_engine) - abs(observed)) / abs(observed) * 100:.1f}% error, no shared input.)")
        s.execute(text("""
            UPDATE sc_model_validation
            SET model_prod_shock_pct = :m,
                skill_note = COALESCE(skill_note, '') || :note
            WHERE event = 'Cocoa 2023/24' AND passed
        """), {"m": signed_engine, "note": note})
        s.commit()
        print(f"Reconciled cocoa claim: {recorded} → {signed_engine} (engine {engine}%, observed {observed}%).")


if __name__ == "__main__":
    main()

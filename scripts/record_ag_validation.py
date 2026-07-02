"""
Record the agriculture backtest findings into sc_model_validation, so the validation that
makes the € credible is surfaced in the product (Trust → Models & validation), not just in
script stdout. Single source of truth = the scripts/backtest_*.py results already produced.
Idempotent. Run: .venv/bin/python scripts/record_ag_validation.py
"""
from sqlalchemy import text
from core.db.session import get_session

# From backtest_cocoa_drought.py / backtest_coffee_climate.py / backtest_supply_impact.py.
ROWS = [
    {
        "event": "Cocoa 2023/24", "commodity": "Cocoa", "hazard": "heat_acute",
        "obs_prod": -12.9, "model_price": 173.0, "obs_price": 177.0,
        "note": ("Driven by EXTREME HEAT (2024 = hottest year in 34, +1.16°C), NOT drought "
                 "(2023 was the WETTEST year, SPEI +2.15 — excess rain → black-pod disease). "
                 "Calibrated chain reproduces the −12.9% world supply shock and +173% price "
                 "(≈ observed +177% 2024 avg; P90 ≈ the ~4× peak)."),
        "source": "ICCO Nov-2025 + ICE + backtest_cocoa_drought.py",
    },
    {
        "event": "Coffee 2021", "commodity": "Coffee", "hazard": "drought",
        "obs_prod": -12.7, "model_price": 27.0, "obs_price": 55.0,
        "note": ("Driven by DROUGHT (2021 = driest year in 34, SPEI −0.86), NOT heat. Chain "
                 "reproduces the −12.7% supply shock → +27% (the drought-attributable share). "
                 "The Jul-2021 FROST added the rest (to ~+55%) and is NOT modelled — invisible "
                 "in monthly means; pending the CDS daily-min fix. Coffee € is a conservative floor."),
        "source": "ICO/USDA + backtest_coffee_climate.py",
    },
]


def main():
    with get_session() as s:
        for r in ROWS:
            s.execute(text("""
                INSERT INTO sc_model_validation
                    (event, commodity, hazard, observed_prod_shock_pct, model_price_move_pct,
                     observed_price_move_pct, skill_note, source)
                VALUES (:e,:c,:h,:op,:mp,:op2,:n,:src)
                ON CONFLICT (event) DO UPDATE SET
                    observed_prod_shock_pct=EXCLUDED.observed_prod_shock_pct,
                    model_price_move_pct=EXCLUDED.model_price_move_pct,
                    observed_price_move_pct=EXCLUDED.observed_price_move_pct,
                    skill_note=EXCLUDED.skill_note, source=EXCLUDED.source, run_at=now()
            """), {"e": r["event"], "c": r["commodity"], "h": r["hazard"], "op": r["obs_prod"],
                   "mp": r["model_price"], "op2": r["obs_price"], "n": r["note"], "src": r["source"]})
        n = s.execute(text("SELECT count(*) FROM sc_model_validation")).scalar()
    print(f"recorded {len(ROWS)} validation events ({n} total in sc_model_validation)")


if __name__ == "__main__":
    main()

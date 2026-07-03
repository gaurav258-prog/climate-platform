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
    {
        "event": "Fuego 2018 (Guatemala coffee, volcanic)", "commodity": "Coffee", "hazard": "volcanic",
        "obs_prod": -0.9, "model_price": 1.8, "obs_price": None,
        "note": ("Guatemala's Alotenango/Antigua plot volcanic score (81, proximal+ashfall physics) "
                 "against Anacafe's ~0.9% NATIONAL coffee production loss from the June 2018 Fuego "
                 "eruption. KNOWN LIMITATION: Coffee is one shared commodity (Brazil drought-calibrated "
                 "sensitivity=0.45, global_share=0.35); the live product borrows Brazil's 15x-larger "
                 "world share when pricing Guatemala's hazard (no per-origin override in the schema). "
                 "This row reports the ORIGIN-SPECIFIC figure (Guatemala's real ~2.3% world coffee "
                 "share) instead: yield-shock 36.4% -> price-move 1.8% -- order-of-magnitude only, since "
                 "Anacafe's 0.9% is a national average diluted across origins far from Fuego, not a "
                 "local Antigua-region figure. Disclosed, not resolved -- Guatemala stays 'indicative', "
                 "not added to BACKTESTED. See docs/VOLCANIC_HAZARD_METHODOLOGY.md."),
        "source": "Anacafe + MAGA + backtest_volcanic.py",
    },
    {
        "event": "Hurricane Maria 2017 (Puerto Rico coffee, storm)", "commodity": "Coffee", "hazard": "storm",
        "obs_prod": None, "model_price": 0.0, "obs_price": None,
        "note": ("Puerto Rico's Adjuntas plot storm score (73, Modified Rankine Vortex wind-decay "
                 "physics vs IBTrACS's real Hurricane Maria track) against Puerto Rico Dept. of "
                 "Agriculture's ~$780M / ~80% of total island crop value destroyed (economy-wide, "
                 "NOT coffee-specific -- 18 million coffee trees destroyed is the only coffee-specific "
                 "figure found, a quantity not a %). KNOWN LIMITATION (same as Guatemala's volcanic "
                 "row): Coffee is one shared commodity (Brazil drought-calibrated sensitivity=0.45, "
                 "global_share=0.35); the live product borrows Brazil's much larger world share when "
                 "pricing Puerto Rico's hazard. This row reports the ORIGIN-SPECIFIC figure (Puerto "
                 "Rico's real world coffee share, order-of-magnitude ~0.05%) instead: yield-shock "
                 "32.8% -> price-move ~0.0% -- this anchor is WEAKER than both Guatemala's and the "
                 "cocoa/coffee climate backtests since no clean coffee-specific national-loss % exists "
                 "for this event. Disclosed, not smoothed over -- Puerto Rico stays 'indicative', not "
                 "added to BACKTESTED. See docs/STORM_HAZARD_METHODOLOGY.md."),
        "source": "Puerto Rico Dept. of Agriculture + NOAA/NCEI + backtest_storm.py",
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

"""Per-ORIGIN commodity calibration (commodity x origin), not per-commodity

Revision ID: sc_calibration_20260715
Revises: sfdr_batch_20260712
Create Date: 2026-07-15

WHY. The impact function carried ONE calibration per commodity, keyed by name
(sc_commodities.name is UNIQUE). That is physically wrong for two reasons:

  1. The same crop fails differently in different places, and each origin is a
     different share of WORLD production. Coffee was calibrated to Brazil
     (sensitivity 0.45, world share 35%); when Guatemala and Puerto Rico coffee
     plots were added they silently BORROWED Brazil's 35% world share -- i.e. the
     model believed a Guatemalan drought moved the world coffee price as much as
     a Brazilian one. Guatemala is ~2.3% of world coffee; Puerto Rico ~0.02%.
  2. The world supply shock was weighted by how much the CUSTOMER happens to buy
     in each origin, when it must be weighted by each origin's share of world
     PRODUCTION. A buyer sourcing 90% from Ghana does not make Ghana 90% of the
     world cocoa price signal.

MODEL. World supply shock for a commodity is now the sum over its origins:
    global_shock = SUM_over_origins( origin_yield_shock x origin_world_share )
then price_move = A(stock_to_use) x global_shock / |elasticity| as before. The
sourcing channel still uses the buyer's own spend-weighted yield shock.

BACKTEST PRESERVED. Cocoa's calibrated global_share of 0.60 was the West-African
belt: Cote d'Ivoire (~45%) + Ghana (~15%). Splitting it into the real per-origin
shares sums back to 0.60, so the 2023/24 event reproduction is unchanged while
the model becomes correct.

stock_to_use and demand_elasticity stay COMMODITY-level (stocks and demand are
global properties of a traded commodity, not properties of an origin).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sc_calibration_20260715"
down_revision: Union[str, None] = "sfdr_batch_20260712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (commodity, origin, sensitivity, world_share, hazard_driver, tier, event_ref, note)
# Sources: ICCO (cocoa), ICO/USDA PSD (coffee), IOC (olive oil), USDA WASDE (wheat
# stocks), FAOSTAT production shares. Sensitivity is NULL where not calibrated ->
# the engine falls back to CROP_SENSITIVITY.
_SEED = [
    ("Cocoa", "CI", 0.294, 0.45, "heat_acute", "backtested",
     "Cote d'Ivoire/Ghana 2023/24 extreme heat -> ICCO world crop -12.9%, ICE +177%",
     "Cote d'Ivoire ~45% of world cocoa (ICCO). Sensitivity 0.294 fitted on the seasonal "
     "(Jan-Mar harmattan) heat score to reproduce the 2023/24 world shock; CI+GH shares sum "
     "to the 0.60 belt figure the original single-commodity calibration used, so the event "
     "reproduction is preserved."),
    ("Cocoa", "GH", 0.294, 0.15, "heat_acute", "backtested",
     "Cote d'Ivoire/Ghana 2023/24 extreme heat (Ghana crop ~-40%)",
     "Ghana ~15% of world cocoa (ICCO). Same belt-wide heat event and same fitted sensitivity "
     "as CI -- one weather system drives both origins."),
    ("Coffee", "BR", 0.45, 0.35, "drought", "backtested",
     "Brazil 2021 drought -> world crop -12.7%, price +27% (drought-attributable share)",
     "Brazil ~35% of world coffee (ICO/USDA). Drought-attributable only: the Jul-2021 frost "
     "added the rest of the move and is not modelled, so coffee's euro is a conservative floor."),
    ("Coffee", "GT", 0.45, 0.023, "volcanic", "indicative",
     None,
     "Guatemala ~2.3% of world coffee (ICO). Sensitivity BORROWED from Brazil -- not fitted to "
     "a Guatemalan event, so this origin stays indicative. Previously this origin silently used "
     "Brazil's 35% world share (15x too large); the Fuego 2018 check was order-of-magnitude only."),
    ("Coffee", "PR", 0.45, 0.0002, "storm", "indicative",
     None,
     "Puerto Rico ~0.02% of world coffee -- negligible for the world price (market channel ~0), "
     "but a real hit to a buyer sourcing there (sourcing channel still applies). Sensitivity "
     "borrowed from Brazil; Hurricane Maria 2017 had no clean coffee-specific % anchor."),
    ("Olive oil", "ES", None, 0.45, None, "indicative",
     None, "Spain ~45% of world olive oil (IOC). Not event-backtested."),
    ("Durum wheat", "ES", None, 0.02, None, "indicative",
     None, "Spain is a minor global durum origin (Canada/Italy/Turkey dominate). Not backtested."),
    ("Citrus", "ES", None, 0.03, None, "indicative",
     None, "Valencia is a major EU citrus region but small next to Brazil/China/US. Not backtested."),
    ("Wine grapes", "ES", None, 0.01, None, "indicative",
     None, "Extremadura is a small fraction of world wine-grape production. Not backtested."),
    ("Almonds", "PT", None, 0.01, None, "indicative",
     None, "Alentejo is a minor almond origin next to California's ~80% world share. Not backtested."),
    ("Cane sugar", "ES", None, 1.0, None, "indicative",
     None, "HONEST FLAG: Spain does not grow cane sugar at commercial scale (its real sugar crop "
     "is beet; cane is Brazil/India/Thailand). Left at the crude world_share=1.0 placeholder "
     "rather than inventing a share for a geography that does not reflect real production. The "
     "demo seed's placement itself is the thing to fix."),
]

# commodity -> global stocks-to-use % (USDA/ICCO/ICO). NULL -> flat transmission fallback.
_STOCKS = {
    "Cocoa": 26.4, "Coffee": 40.0, "Olive oil": 25.0, "Durum wheat": 32.0,
    "Citrus": 12.0, "Wine grapes": 45.0, "Almonds": 15.0,
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE sc_commodities ADD COLUMN stock_to_use NUMERIC(6,2);

        CREATE TABLE sc_commodity_calibration (
            commodity_id     UUID NOT NULL REFERENCES sc_commodities(commodity_id) ON DELETE CASCADE,
            origin           VARCHAR(40) NOT NULL,        -- ISO-2 country (matches sc_sourcing_plots.country)
            sensitivity      NUMERIC(6,4),                -- fraction of yield lost at full hazard; NULL -> crop default
            world_share      NUMERIC(7,5) NOT NULL,       -- this origin's share of WORLD production (0-1)
            hazard_driver    VARCHAR(30),                 -- the validated dominant hazard for this origin
            calibration_tier VARCHAR(12) NOT NULL DEFAULT 'indicative'
                             CHECK (calibration_tier IN ('backtested','indicative')),
            event_ref        TEXT,                        -- the real event this reproduces (backtested only)
            source_note      TEXT,
            impact_version   VARCHAR(20),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (commodity_id, origin)
        );
        CREATE INDEX ix_sc_calibration_origin ON sc_commodity_calibration(origin);
    """)

    for name, stock in _STOCKS.items():
        op.execute(
            f"UPDATE sc_commodities SET stock_to_use = {stock} WHERE name = '{name}';"
        )

    for (name, origin, sens, share, driver, tier, event, note) in _SEED:
        sens_sql = "NULL" if sens is None else str(sens)
        driver_sql = "NULL" if driver is None else f"'{driver}'"
        event_sql = "NULL" if event is None else "'" + event.replace("'", "''") + "'"
        note_sql = "'" + note.replace("'", "''") + "'"
        op.execute(f"""
            INSERT INTO sc_commodity_calibration
                (commodity_id, origin, sensitivity, world_share, hazard_driver,
                 calibration_tier, event_ref, source_note, impact_version)
            SELECT commodity_id, '{origin}', {sens_sql}, {share}, {driver_sql},
                   '{tier}', {event_sql}, {note_sql}, 'sc-impact-v0.3'
            FROM sc_commodities WHERE name = '{name.replace("'", "''")}'
            ON CONFLICT (commodity_id, origin) DO NOTHING;
        """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS sc_commodity_calibration;
        ALTER TABLE sc_commodities DROP COLUMN IF EXISTS stock_to_use;
    """)

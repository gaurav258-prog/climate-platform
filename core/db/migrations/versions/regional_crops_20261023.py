"""Regional crop calibrations (data/reference/calibration_protocol.json 'regional', crop-calib-reg-v1).

  crop_calibration_coverage  + region: '' for a crop × origin (as before), a region code for a crop × region
                             (services.calibration.regional_specs); status + 'small_area' — a region holding under
                             the protocol's share of the crop's mapped area in its country
  v_sc_commodity_calibration the ranged tier also needs a damage response — the fit's slope negative (E327: a fit where
                             more drought meant more yield cleared the floor and would have derived 'ranged')

The coverage is a snapshot replaced whole on each generation, so a downgrade drops the regional rows with the column
(the next generation writes them again).

Revision ID: regional_crops_20261023
Revises: fund_pos_money_20261023
"""
from typing import Sequence, Union

from alembic import op

_FLOOR = "0.40"   # as ranged_gate_oos_20260731 wrote it (a numeric literal keeps its written scale); services.intelligence.supply_cogs.RANGED_PUBLISH_FLOOR


def _view(ranged_condition: str) -> str:
    return f"""
        CREATE OR REPLACE VIEW v_sc_commodity_calibration AS
        SELECT c.commodity_id, c.origin, c.sensitivity, c.world_share, c.hazard_driver,
               c.event_ref, c.source_note, c.impact_version, c.region_key, c.season_months,
               c.scoring_model, c.baseline_from, c.baseline_to,
               CASE
                 WHEN EXISTS (SELECT 1 FROM sc_model_validation v
                              WHERE v.commodity_id = c.commodity_id
                                AND v.origin::text = c.origin::text
                                AND v.passed
                                AND v.hazard::text = c.hazard_driver::text)
                   THEN 'backtested'
                 WHEN EXISTS (SELECT 1 FROM sc_commodity_fit f
                              WHERE f.commodity_id = c.commodity_id
                                AND f.origin::text = c.origin::text
                                AND f.hazard_driver::text = c.hazard_driver::text
                                AND {ranged_condition})
                   THEN 'ranged'
                 ELSE 'indicative'
               END AS calibration_tier
        FROM sc_commodity_calibration c
    """

revision: str = "regional_crops_20261023"
down_revision: Union[str, None] = "fund_pos_money_20261023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE crop_calibration_coverage
            ADD COLUMN region varchar(8) NOT NULL DEFAULT '',
            DROP CONSTRAINT crop_calibration_coverage_pkey,
            ADD PRIMARY KEY (commodity, origin, region),
            DROP CONSTRAINT crop_calibration_coverage_status_check,
            ADD CONSTRAINT crop_calibration_coverage_status_check
                CHECK (status IN ('recipe', 'no_yield_series', 'too_few_years', 'no_season', 'small_area'));
    """)
    op.execute(_view(f"f.r2_oos >= {_FLOOR} AND f.slope < 0"))


def downgrade() -> None:
    op.execute(_view(f"f.r2_oos >= {_FLOOR}"))
    op.execute("""
        DELETE FROM crop_calibration_coverage WHERE region <> '' OR status = 'small_area';
        ALTER TABLE crop_calibration_coverage
            DROP CONSTRAINT crop_calibration_coverage_status_check,
            ADD CONSTRAINT crop_calibration_coverage_status_check
                CHECK (status IN ('recipe', 'no_yield_series', 'too_few_years', 'no_season')),
            DROP CONSTRAINT crop_calibration_coverage_pkey,
            DROP COLUMN region,
            ADD PRIMARY KEY (commodity, origin);
    """)

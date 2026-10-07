"""Projected hazard intensity and the losses read from it (product owner's decisions, 2026-10-07).

A projected flood depth is published per pathway, period and climate model (WRI Aqueduct Floods: RCP4.5/RCP8.5 ×
2030/2050/2080 × five models, and its own present-day map), so a sample names all three; today's layers keep
'present' / 'present' / ''. A projected loss is compared only with the same source's present day, so a result keeps
that figure beside it, and each model's figure behind the range.

  hazard_intensity_samples  + scenario, period, climate_model (part of the unique key)
  loss_runs                 time_horizon may be '2080' (the source's last period, 2060–2099)
  loss_results              + eal_same_source_today_eur, model_eal (jsonb: model → expected annual loss)

Downgrade refuses while a projected sample, a 2080 run or a projected result is recorded.

Revision ID: loss_proj_20261007
Revises: loss_value_20261006
"""
from typing import Sequence, Union

from alembic import op

revision: str = "loss_proj_20261007"
down_revision: Union[str, None] = "loss_value_20261006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO hazard_intensity_samples (layer_key, layer_version, latitude, longitude, h3_cell, rp_years, status,
                    value, cell_fraction, cell_mean, scenario, period, climate_model)
                VALUES ('probe', 'probe', 0, 0, 'probe', 10, 'sampled', 0, 0, 0, 'rcp8p5', '2050', 'probe');""",
    "cleanup": """ALTER TABLE hazard_intensity_samples DISABLE TRIGGER trg_hazard_intensity_samples_guard;
                  DELETE FROM hazard_intensity_samples WHERE layer_key = 'probe';
                  ALTER TABLE hazard_intensity_samples ENABLE TRIGGER trg_hazard_intensity_samples_guard;""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE hazard_intensity_samples
            ADD COLUMN scenario      varchar(20) NOT NULL DEFAULT 'present',
            ADD COLUMN period        varchar(12) NOT NULL DEFAULT 'present',
            ADD COLUMN climate_model varchar(40) NOT NULL DEFAULT '';
        DROP INDEX ux_hazard_intensity_sample;
        CREATE UNIQUE INDEX ux_hazard_intensity_sample ON hazard_intensity_samples
            (layer_key, layer_version, latitude, longitude, rp_years, scenario, period, climate_model);
        ALTER TABLE loss_runs DROP CONSTRAINT loss_runs_time_horizon_check,
            ADD CONSTRAINT loss_runs_time_horizon_check CHECK (time_horizon IN ('current', '2030', '2050', '2080', '2100'));
        ALTER TABLE loss_results
            ADD COLUMN eal_same_source_today_eur numeric(18,2) CHECK (eal_same_source_today_eur >= 0),
            ADD COLUMN model_eal jsonb;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM hazard_intensity_samples WHERE scenario <> 'present' OR period <> 'present' OR climate_model <> '')
               OR EXISTS (SELECT 1 FROM loss_runs WHERE time_horizon = '2080')
               OR EXISTS (SELECT 1 FROM loss_results WHERE eal_same_source_today_eur IS NOT NULL OR model_eal IS NOT NULL) THEN
                RAISE EXCEPTION 'projected samples or losses are recorded — they cannot be removed';
            END IF;
        END $$;
        ALTER TABLE loss_results DROP COLUMN model_eal, DROP COLUMN eal_same_source_today_eur;
        ALTER TABLE loss_runs DROP CONSTRAINT loss_runs_time_horizon_check,
            ADD CONSTRAINT loss_runs_time_horizon_check CHECK (time_horizon IN ('current', '2030', '2050', '2100'));
        DROP INDEX ux_hazard_intensity_sample;
        CREATE UNIQUE INDEX ux_hazard_intensity_sample ON hazard_intensity_samples
            (layer_key, layer_version, latitude, longitude, rp_years);
        ALTER TABLE hazard_intensity_samples DROP COLUMN climate_model, DROP COLUMN period, DROP COLUMN scenario;
    """)

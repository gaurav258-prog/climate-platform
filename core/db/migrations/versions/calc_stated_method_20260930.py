"""org_calc_settings loses severity_model and insurance_return_period_model: they chose between the platform's own
damage schedules ('universal' / 'peril_specific') and return-period tables ('fixed' / 'peril_specific'), which are gone
(E69) — the institution states its damage ratios and event probabilities as method parameters. Reversible: the
downgrade restores the columns with the values they held (kept in a side table by the upgrade).

Revision ID: calc_stated_method_20260930
Revises: reit_sum_insured_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "calc_stated_method_20260930"
down_revision: Union[str, None] = "reit_sum_insured_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE org_calc_settings_retired_20260930 AS
            SELECT org_id, severity_model, insurance_return_period_model FROM org_calc_settings;
        ALTER TABLE org_calc_settings DROP COLUMN severity_model, DROP COLUMN insurance_return_period_model;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE org_calc_settings
            ADD COLUMN severity_model VARCHAR(20) NOT NULL DEFAULT 'universal'
                CONSTRAINT org_calc_settings_severity_model_check
                CHECK (severity_model IN ('universal', 'peril_specific')),
            ADD COLUMN insurance_return_period_model VARCHAR(20) NOT NULL DEFAULT 'fixed'
                CONSTRAINT org_calc_settings_insurance_return_period_model_check
                CHECK (insurance_return_period_model IN ('fixed', 'peril_specific'));
        UPDATE org_calc_settings s SET severity_model = r.severity_model,
               insurance_return_period_model = r.insurance_return_period_model
        FROM org_calc_settings_retired_20260930 r WHERE r.org_id = s.org_id;
        DROP TABLE org_calc_settings_retired_20260930;
    """)

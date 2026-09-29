"""The facts EU Taxonomy activity 7.7 'Acquisition and ownership of buildings' needs to decide alignment.

Delegated Regulation (EU) 2021/2139, Annex I, Section 7.7 (data/reference/taxonomy/criteria/ccm_7_7.json): substantial
contribution by EPC class A — or the top 15 % of the national / regional stock by operational primary energy demand —
for a building built before 2021, by the Section 7.1 criteria for one built after, and energy-performance monitoring
for a large non-residential building (heating / air-conditioning over 290 kW); do-no-significant-harm to climate
adaptation by Appendix A (a climate risk and vulnerability assessment, and an adaptation plan for existing buildings);
the other four objectives are 'N/A'. EPC, year built and minimum safeguards are already stated; these are the rest.

Revision ID: reit_7_7_facts_20260929
Revises: taxonomy_csrd_20260929
"""
from typing import Sequence, Union

from alembic import op

revision: str = "reit_7_7_facts_20260929"
down_revision: Union[str, None] = "taxonomy_csrd_20260929"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLS = (
    ("ped_top15_evidence", "BOOLEAN"),                 # within the top 15 % of the stock by operational PED, evidenced
    ("meets_new_building_criteria", "BOOLEAN"),        # built after 2020: meets the Section 7.1 criteria
    ("heating_rated_output_kw", "NUMERIC(10,1) CONSTRAINT ck_ext_realestate_heating_kw CHECK (heating_rated_output_kw >= 0)"),
    ("energy_performance_monitoring", "BOOLEAN"),      # efficiently operated through energy performance monitoring
    ("adaptation_plan_in_place", "BOOLEAN"),           # Appendix A: adaptation solutions under an adaptation plan
)


def upgrade() -> None:
    for name, kind in _COLS:
        op.execute(f"ALTER TABLE ext_realestate ADD COLUMN IF NOT EXISTS {name} {kind}")


def downgrade() -> None:
    for name, _ in _COLS:
        op.execute(f"ALTER TABLE ext_realestate DROP COLUMN IF EXISTS {name}")

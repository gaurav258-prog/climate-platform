"""Add 'soil_water' to the hazard vocabulary.

Root-zone water stress (from the soil-moisture anomaly) is a distinct hazard channel from
meteorological drought (SPEI): it captures antecedent/deep soil water a rainfall index misses,
and is the validated driver for dryland cereals (Spanish durum wheat: soil-moisture r²=0.42 vs
SPEI 0.36). Kept as its own hazard_type so a cell can carry BOTH (olive→drought, wheat→soil_water)
without one retiring the other. Same drop-and-re-add pattern as the
pollution/volcanic additions.
"""
from alembic import op

# Frozen vocabulary (self-contained migration — never import app code): core.types.HAZARD_VALUES as of commit 3fedbcc.
_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic', 'volcanic',
    'pollution', 'frost', 'soil_water',
)

# The vocabulary in force at down_revision (ranged_floor_20260718 = d5e6f7a8b9c0's list) — what downgrade() restores.
_PRIOR_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic', 'volcanic',
    'pollution', 'frost',
)

revision = "soil_water_hazard_vocab_20260718"
down_revision = "ranged_floor_20260718"
branch_labels = None
depends_on = None


def _in_list(column: str, values) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    for table, name, column in [
        ("canonical_scores", "ck_canonical_hazard_vocab", "hazard_type"),
        ("satellite_observations", "ck_obs_hazard_vocab", "hazard_type"),
    ]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {name} CHECK ({_in_list(column, _HAZARD_VALUES)}) NOT VALID"
        )


def downgrade() -> None:
    # Restore the pre-soil_water CHECK constraints exactly as d5e6f7a8b9c0 (frost) left them.
    for table, name, column in [
        ("canonical_scores", "ck_canonical_hazard_vocab", "hazard_type"),
        ("satellite_observations", "ck_obs_hazard_vocab", "hazard_type"),
    ]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {name} CHECK ({_in_list(column, _PRIOR_HAZARD_VALUES)}) NOT VALID"
        )

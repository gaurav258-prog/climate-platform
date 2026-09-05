"""windstorm_vocab — add the extratropical-windstorm hazard to the vocabulary CHECK constraints.

EU-Taxonomy Appendix A separates 'Storm (blizzard, dust, sand)' from 'Cyclone/hurricane/typhoon'. The new
HazardType.WINDSTORM (ERA5 gust-climatology channel, distinct from the tropical-cyclone STORM channel) adds
'windstorm' to core.types.HAZARD_VALUES; this rebuilds the hazard_type CHECK constraints from that list, same
drop-and-re-add-from-HAZARD_VALUES pattern as the prior vocab migrations. NOT VALID (new rows enforced;
existing rows untouched).
"""
from typing import Sequence, Union

from alembic import op

from core.types import HAZARD_VALUES

revision: str = "windstorm_vocab_20260905"
down_revision: Union[str, None] = "hazard_layers_2_20260904"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
            f"ADD CONSTRAINT {name} CHECK ({_in_list(column, HAZARD_VALUES)}) NOT VALID"
        )


def downgrade() -> None:
    # Does not restore the pre-windstorm CHECK (would need the prior HAZARD_VALUES snapshot).
    pass

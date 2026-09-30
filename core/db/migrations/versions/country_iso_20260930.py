"""Countries stored as ISO 3166-1 alpha-2, one code per country.

Demo seeding stored the EU's own codes for two countries ('UK' for the United Kingdom, 'EL' for Greece —
Interinstitutional Style Guide 7.1.1) beside the ISO ones ('GB', 'GR'), so the same country had two codes and a
lookup keyed by ISO missed one of them: the Solvency II earthquake region table (keyed GR) left every Greek risk
without an earthquake charge. Intake now converts them (services.reference.iso_country.to_iso2); this migration
converts the stored rows and adds a check so neither code is stored as a country again.

Revision ID: country_iso_20260930
Revises: narratives_answers_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "country_iso_20260930"
down_revision: Union[str, None] = "narratives_answers_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("portfolio_entities", "organizations")
_EU_TO_ISO = {"UK": "GB", "EL": "GR"}        # frozen here (services.reference.iso_country.EU_TO_ISO)


def upgrade() -> None:
    for t in _TABLES:
        for eu, iso in _EU_TO_ISO.items():
            op.execute(f"UPDATE {t} SET country = '{iso}' WHERE upper(country) = '{eu}'")
        op.execute(f"""ALTER TABLE {t} ADD CONSTRAINT ck_{t}_country_iso
                       CHECK (country IS NULL OR (country ~ '^[A-Z]{{2}}$' AND country NOT IN ('UK', 'EL')))""")


def downgrade() -> None:
    # the check goes; the rows stay ISO (which of them were written 'UK' / 'EL' is not recorded, and ISO is correct)
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} DROP CONSTRAINT IF EXISTS ck_{t}_country_iso")

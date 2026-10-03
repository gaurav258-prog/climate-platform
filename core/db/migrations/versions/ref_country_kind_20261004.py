"""The country reference says which of its entries are countries (E154).

ref_countries carries ISO 3166 alpha-2 codes from CLDR plus the exceptional reservation 'EU' (accepted on uploads,
which may state a value for the Union as a whole). Read as 'the countries', it let a reader take the EU total for a
country (found 2026-10-04: Eurostat's 'EU' row would have landed as a country next to its own members). Each entry now
states it: is_country false for a grouping of countries — 'EU' (ISO 3166-1 exceptional reservation). Kosovo (XK, a
user-assigned code with its own statistics) is a country entry.

Revision ID: ref_country_kind_20261004
Revises: crop_release_checks_20261004
"""
from typing import Sequence, Union

from alembic import op

revision: str = "ref_country_kind_20261004"
down_revision: Union[str, None] = "crop_release_checks_20261004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ref_countries ADD COLUMN is_country boolean NOT NULL DEFAULT true;
        UPDATE ref_countries SET is_country = false WHERE iso2 = 'EU';
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE ref_countries DROP COLUMN is_country;")

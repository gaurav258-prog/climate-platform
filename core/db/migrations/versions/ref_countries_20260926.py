"""Country reference data (Unicode CLDR): codes, names in the EU's languages, and each country's currency.

  * ref_countries — ISO 3166 alpha-2 (key), alpha-3, numeric, English name, the current legal-tender currency
    and since when, and the CLDR version it came from.
  * ref_country_names — every accepted way of writing a country (normalised, case/spacing-insensitive) → alpha-2:
    the codes themselves, CLDR names in each loaded language, CLDR short/variant forms, and a small labelled list of
    common business forms ('curated'). A normalised name that could mean two countries is never stored.
Loaded by services/reference/countries.py (feed `reference_countries`).

Revision ID: ref_countries_20260926
Revises: fx_ecb_feed_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "ref_countries_20260926"
down_revision: Union[str, None] = "fx_ecb_feed_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ref_countries (
            iso2            CHAR(2) PRIMARY KEY,
            iso3            CHAR(3),
            numeric_code    CHAR(3),
            name_en         TEXT NOT NULL,
            currency        CHAR(3),
            currency_from   DATE,
            source_version  TEXT NOT NULL,
            loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS ref_country_names (
            name_norm  TEXT PRIMARY KEY,
            iso2       CHAR(2) NOT NULL REFERENCES ref_countries(iso2) ON DELETE CASCADE,
            name       TEXT NOT NULL,
            locale     TEXT,
            kind       TEXT NOT NULL,
            CONSTRAINT ck_country_name_kind CHECK (kind IN ('code', 'name', 'variant', 'curated'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_country_names_iso2 ON ref_country_names (iso2)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ref_country_names")
    op.execute("DROP TABLE IF EXISTS ref_countries")

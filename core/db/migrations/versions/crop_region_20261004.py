"""A crop-yield series can be national or for one region of a country (E156).

The store's key was (commodity, country, season_year, source) — no place for a sub-national unit. The Brazilian
series (IBGE PAM) therefore carried their state in the SOURCE label ('IBGE PAM Soybean MT (sub-national)'), and
sub-national sources (USDA NASS states and counties, Eurostat NUTS-2) could not be added at all.

  crop_yield_observations.region_code    '' for a national figure, else the region's code — ISO 3166-2 for a state or
                                         province ('BR-MT', 'US-IA'), NUTS for EU regions ('ES61'), the publisher's code
                                         prefixed for a smaller unit ('US-IA-19001' county FIPS); part of the key
  crop_yield_release_rows.region_code    the same, part of the release row's key
  IBGE rows                              their region stated (BR-MT, BR-RS, BR-MG); the source labels stay as they are
                                         (two Rio Grande do Sul soybean series — 34 and 51 years — must stay apart, and
                                         calibration audits read the labels)

Every product reader states which it reads: a national series is region_code = ''. Downgrade refuses while a regional
row exists outside the IBGE rows this revision labelled (the old key cannot hold two regions of one country).

Revision ID: crop_region_20261004
Revises: ref_country_kind_20261004
"""
from typing import Sequence, Union

from alembic import op

revision: str = "crop_region_20261004"
down_revision: Union[str, None] = "ref_country_kind_20261004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_IBGE = {"IBGE PAM Soybean MT (sub-national)": "BR-MT", "IBGE PAM Cotton MT (sub-national)": "BR-MT",
         "IBGE PAM Maize MT (sub-national)": "BR-MT", "IBGE PAM Soybean RS (sub-national)": "BR-RS",
         "IBGE PAM Soybean RS full (sub-national)": "BR-RS",
         "IBGE PAM Minas Gerais (sub-national arabica proxy)": "BR-MG"}

REFUSAL_PROBE = {
    "setup": """INSERT INTO crop_yield_observations (commodity, country, region_code, season_year, production_tonnes, source)
                VALUES ('Probe', 'US', 'US-IA', 2020, 1, 'probe'), ('Probe', 'US', 'US-IL', 2020, 1, 'probe');""",
    "cleanup": """DELETE FROM crop_yield_observations WHERE source = 'probe';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE crop_yield_observations ADD COLUMN region_code varchar(24) NOT NULL DEFAULT '';
        ALTER TABLE crop_yield_observations DROP CONSTRAINT crop_yield_observations_commodity_country_season_year_sourc_key;
        ALTER TABLE crop_yield_observations ADD CONSTRAINT ux_crop_yield_series
            UNIQUE (commodity, country, region_code, season_year, source);
        ALTER TABLE crop_yield_release_rows ADD COLUMN region_code varchar(24) NOT NULL DEFAULT '';
        ALTER TABLE crop_yield_release_rows DROP CONSTRAINT crop_yield_release_rows_pkey;
        ALTER TABLE crop_yield_release_rows ADD PRIMARY KEY (release_id, commodity, country, region_code, season_year);
    """)
    for label, code in _IBGE.items():
        op.execute(f"UPDATE crop_yield_observations SET region_code = '{code}' WHERE source = '{label}'")


def downgrade() -> None:
    labels = ", ".join(f"'{k}'" for k in _IBGE)
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM crop_yield_observations WHERE region_code <> '' AND source NOT IN ({labels})) THEN
            RAISE EXCEPTION 'crop_region_20261004 downgrade: regional rows are held — the key before this revision '
                            'cannot hold two regions of one country';
          END IF;
        END $$;
        ALTER TABLE crop_yield_release_rows DROP CONSTRAINT crop_yield_release_rows_pkey;
        ALTER TABLE crop_yield_release_rows ADD PRIMARY KEY (release_id, commodity, country, season_year);
        ALTER TABLE crop_yield_release_rows DROP COLUMN region_code;
        ALTER TABLE crop_yield_observations DROP CONSTRAINT ux_crop_yield_series;
        ALTER TABLE crop_yield_observations ADD CONSTRAINT crop_yield_observations_commodity_country_season_year_sourc_key
            UNIQUE (commodity, country, season_year, source);
        ALTER TABLE crop_yield_observations DROP COLUMN region_code;
    """)

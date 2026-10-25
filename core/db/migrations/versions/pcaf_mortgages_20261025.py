"""PCAF mortgages (Part A, 3rd ed., §5.5; data/reference/pcaf/part_a_2025.json): what a bank states so a mortgage's
financed emissions are computed instead of named as a gap.

  ext_banking  + pcaf_asset_class                   the loan's PCAF asset class (chapter 5's ten) — it sets the attribution
               + property_value_at_origination_eur  the denominator: the property's value when the loan was made
               + property_value_fixed_eur           where that value cannot be obtained, the latest value, kept fixed for
                                                    the following years (the intake refuses a changed one)
               + floor_area_m2                      what an energy use per m² is multiplied by
  bank_building_energy                              the mortgaged building's energy use, one row per energy source: where
                                                    the figure comes from (it sets the data quality score, Table 5.5-1),
                                                    the figure (kWh a year, or kWh/m² a year), the number of buildings
                                                    for statistics per building, and the source's emission factor with
                                                    its type (the supplier's own, or the average for the area)

Biomass is not an energy source here: §6.1 reports its biogenic CO2 apart, which the platform does not carry yet.
Downgrade refuses while any of it is stated (the earlier shape cannot keep it).

Revision ID: pcaf_mortgages_20261025
Revises: loss_value_basis_20261025
"""
from typing import Sequence, Union

from alembic import op

revision: str = "pcaf_mortgages_20261025"
down_revision: Union[str, None] = "loss_value_basis_20261025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORG, _LOAN = "0bbe0bbe-0000-4000-8000-000000000337", "aaaaaaaa-0000-4000-8000-000000000337"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_ORG}', 'refusal probe', 'bank', 'DE');
                 INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, primary_value_eur, source)
                 VALUES ('{_LOAN}', '{_ORG}', 'banking', 'probe', 1, 'own');
                 INSERT INTO ext_banking (entity_id, pcaf_asset_class) VALUES ('{_LOAN}', 'mortgages');
                 INSERT INTO bank_building_energy (org_id, entity_id, energy_source, energy_basis, annual_kwh)
                 VALUES ('{_ORG}', '{_LOAN}', 'electricity', 'metered', 1);""",
    "cleanup": f"""DELETE FROM bank_building_energy WHERE entity_id = '{_LOAN}';
                   DELETE FROM ext_banking WHERE entity_id = '{_LOAN}';
                   DELETE FROM portfolio_entities WHERE entity_id = '{_LOAN}';
                   DELETE FROM organizations WHERE org_id = '{_ORG}';""",
}

_CLASSES = ("listed_equity_corporate_bonds", "business_loans_unlisted_equity", "project_finance", "commercial_real_estate",
            "mortgages", "motor_vehicle_loans", "use_of_proceeds", "securitization_structured_products", "sovereign_debt",
            "sub_sovereign_debt")
_SOURCES = ("natural_gas", "heating_oil", "lpg", "coal", "electricity", "district_heating", "district_cooling")
_BASES = ("metered", "energy_label", "statistics_per_m2", "statistics_per_building")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.execute(f"""
        ALTER TABLE ext_banking
            ADD COLUMN pcaf_asset_class TEXT CONSTRAINT ck_ext_banking_pcaf_asset_class CHECK (pcaf_asset_class IN ({_in(_CLASSES)})),
            ADD COLUMN property_value_at_origination_eur NUMERIC(18,2)
                CONSTRAINT ck_ext_banking_value_at_origination CHECK (property_value_at_origination_eur > 0),
            ADD COLUMN property_value_fixed_eur NUMERIC(18,2)
                CONSTRAINT ck_ext_banking_value_fixed CHECK (property_value_fixed_eur > 0),
            ADD COLUMN floor_area_m2 NUMERIC(12,2) CONSTRAINT ck_ext_banking_floor_area CHECK (floor_area_m2 > 0);
        COMMENT ON COLUMN ext_banking.pcaf_asset_class IS 'The loan''s PCAF asset class (Part A, 3rd ed., chapter 5): sets its attribution';
        COMMENT ON COLUMN ext_banking.property_value_at_origination_eur IS 'PCAF mortgages: the property value at loan origination (the attribution denominator)';
        COMMENT ON COLUMN ext_banking.property_value_fixed_eur IS 'PCAF mortgages: the latest property value, fixed, where the value at origination cannot be obtained';

        CREATE TABLE bank_building_energy (
            energy_id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id                      UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            entity_id                   UUID NOT NULL REFERENCES portfolio_entities(entity_id) ON DELETE CASCADE,
            energy_source               TEXT NOT NULL CHECK (energy_source IN ({_in(_SOURCES)})),
            energy_basis                TEXT NOT NULL CHECK (energy_basis IN ({_in(_BASES)})),
            annual_kwh                  NUMERIC(18,3) CHECK (annual_kwh >= 0),
            kwh_per_m2                  NUMERIC(12,3) CHECK (kwh_per_m2 >= 0),
            buildings                   INTEGER CHECK (buildings >= 1),
            emission_factor_kg_per_kwh  NUMERIC(12,6) CHECK (emission_factor_kg_per_kwh >= 0),
            emission_factor_type        TEXT CHECK (emission_factor_type IN ('supplier_specific', 'average')),
            emission_factor_source      TEXT,
            energy_year                 INTEGER CHECK (energy_year BETWEEN 1990 AND 2100),
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ux_bank_building_energy UNIQUE (entity_id, energy_source),
            -- each basis carries its own figure (data/reference/pcaf/part_a_2025.json mortgages.energy_bases)
            CONSTRAINT ck_bank_building_energy_figure CHECK (
                (energy_basis = 'metered' AND annual_kwh IS NOT NULL AND kwh_per_m2 IS NULL AND buildings IS NULL)
                OR (energy_basis IN ('energy_label', 'statistics_per_m2') AND kwh_per_m2 IS NOT NULL AND annual_kwh IS NULL
                    AND buildings IS NULL)
                OR (energy_basis = 'statistics_per_building' AND annual_kwh IS NOT NULL AND buildings IS NOT NULL
                    AND kwh_per_m2 IS NULL)),
            CONSTRAINT ck_bank_building_energy_factor CHECK (
                emission_factor_kg_per_kwh IS NULL OR emission_factor_type IS NOT NULL)
        );
        CREATE INDEX ix_bank_building_energy_org ON bank_building_energy (org_id);
        COMMENT ON TABLE bank_building_energy IS 'PCAF mortgages: a mortgaged building''s energy use per energy source (Part A §5.5)';
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        DECLARE n integer;
        BEGIN
            SELECT (SELECT count(*) FROM bank_building_energy)
                 + (SELECT count(*) FROM ext_banking
                     WHERE pcaf_asset_class IS NOT NULL OR property_value_at_origination_eur IS NOT NULL
                        OR property_value_fixed_eur IS NOT NULL OR floor_area_m2 IS NOT NULL) INTO n;
            IF n > 0 THEN
                RAISE EXCEPTION 'cannot downgrade pcaf_mortgages_20261025: % loans or building energy rows state what the '
                                'PCAF mortgage method reads — the earlier shape cannot keep it', n;
            END IF;
        END $$;
        DROP TABLE bank_building_energy;
        ALTER TABLE ext_banking DROP COLUMN floor_area_m2, DROP COLUMN property_value_fixed_eur,
            DROP COLUMN property_value_at_origination_eur, DROP COLUMN pcaf_asset_class;
    """)

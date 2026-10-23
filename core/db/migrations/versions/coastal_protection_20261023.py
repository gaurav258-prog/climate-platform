"""Coastal flood defences (the product owner's decisions of 2026-10-23): a published coastal protection standard — the
COASTPROS-EU dataset, one entry per coastal NUTS2 region — is applied to coastal flood losses with the registered rule
(loss_protocol flood_protection). The dataset states its levels as text, read by the decided rule: a single number is the
level; a plain range ('1000-3000') is a range of levels, and the defended loss a range with no central figure; anything
else (a list, a condition, a note) is no level — protection unknown.

  flood_protection_samples  + design_rp_high_years: the upper level of a stated range (NULL for a single level); status
                              + 'not_a_level' (the region states something that is not a level)
  loss_results              + protection_rp_high_years: the upper level of the range applied (NULL for a single level);
                              a range's defended figure has no central value: low (the curve-low loss at the upper level)
                              and high (the curve-high loss at the lower level) with eal_defended_eur NULL — the same for
                              the share columns of an issuer's site

Downgrade refuses while a range is recorded.

Revision ID: coastal_protection_20261023
Revises: register_sites_20261023
"""
from typing import Sequence, Union

from alembic import op

revision: str = "coastal_protection_20261023"
down_revision: Union[str, None] = "register_sites_20261023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO flood_protection_samples (layer_key, layer_version, latitude, longitude, status, design_rp_years,
                                                      design_rp_high_years)
                VALUES ('probe', 'probe', 0, 0, 'sampled', 1000, 3000);""",
    "cleanup": """ALTER TABLE flood_protection_samples DISABLE TRIGGER trg_flood_protection_samples_guard;
                  DELETE FROM flood_protection_samples WHERE layer_key = 'probe';
                  ALTER TABLE flood_protection_samples ENABLE TRIGGER trg_flood_protection_samples_guard;""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE flood_protection_samples
            ADD COLUMN design_rp_high_years double precision,
            DROP CONSTRAINT flood_protection_samples_status_check,
            ADD CONSTRAINT flood_protection_samples_status_check
                CHECK (status IN ('sampled', 'no_value', 'outside_coverage', 'not_a_level')),
            ADD CONSTRAINT flood_protection_samples_range
                CHECK (design_rp_high_years IS NULL OR (status = 'sampled' AND design_rp_high_years > design_rp_years));

        ALTER TABLE loss_results
            ADD COLUMN protection_rp_high_years double precision,
            ADD CONSTRAINT loss_results_protection_range
                CHECK (protection_rp_high_years IS NULL OR protection_rp_high_years > protection_rp_years),
            DROP CONSTRAINT loss_results_defended_range,
            -- a single level: central, low and high together; a range of levels: low and high, no central figure
            ADD CONSTRAINT loss_results_defended_range CHECK (
                ((eal_defended_eur IS NULL) = (eal_defended_low_eur IS NULL AND eal_defended_high_eur IS NULL))
                OR (protection_rp_high_years IS NOT NULL AND eal_defended_eur IS NULL AND eal_defended_low_eur IS NOT NULL
                    AND eal_defended_high_eur IS NOT NULL AND eal_defended_low_eur <= eal_defended_high_eur
                    AND eal_eur IS NOT NULL AND eal_defended_high_eur <= eal_high_eur)),
            DROP CONSTRAINT loss_results_defended_ratio_range,
            ADD CONSTRAINT loss_results_defended_ratio_range CHECK (
                ((eal_defended_ratio IS NULL) = (eal_defended_ratio_low IS NULL AND eal_defended_ratio_high IS NULL))
                OR (protection_rp_high_years IS NOT NULL AND eal_defended_ratio IS NULL
                    AND eal_defended_ratio_low IS NOT NULL AND eal_defended_ratio_high IS NOT NULL
                    AND eal_defended_ratio_low <= eal_defended_ratio_high
                    AND eal_ratio IS NOT NULL AND eal_defended_ratio_high <= eal_ratio_high));
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM flood_protection_samples WHERE design_rp_high_years IS NOT NULL OR status = 'not_a_level')
               OR EXISTS (SELECT 1 FROM loss_results WHERE protection_rp_high_years IS NOT NULL) THEN
                RAISE EXCEPTION 'ranges of protection levels are recorded — they cannot be removed';
            END IF;
        END $$;
        ALTER TABLE loss_results
            DROP CONSTRAINT loss_results_defended_ratio_range,
            ADD CONSTRAINT loss_results_defended_ratio_range CHECK ((eal_defended_ratio IS NULL) =
                (eal_defended_ratio_low IS NULL AND eal_defended_ratio_high IS NULL)),
            DROP CONSTRAINT loss_results_defended_range,
            ADD CONSTRAINT loss_results_defended_range CHECK ((eal_defended_eur IS NULL) =
                (eal_defended_low_eur IS NULL AND eal_defended_high_eur IS NULL)),
            DROP CONSTRAINT loss_results_protection_range,
            DROP COLUMN protection_rp_high_years;
        ALTER TABLE flood_protection_samples
            DROP CONSTRAINT flood_protection_samples_range,
            DROP CONSTRAINT flood_protection_samples_status_check,
            ADD CONSTRAINT flood_protection_samples_status_check
                CHECK (status IN ('sampled', 'no_value', 'outside_coverage')),
            DROP COLUMN design_rp_high_years;
    """)

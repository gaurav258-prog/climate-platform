"""Flood defences in the loss engine (product owner's decisions, 2026-10-16; data/reference/loss_protocol.json
'flood_protection').

A published protection standard — the design return period, in years, of the local defences against river floods — is
sampled once per location and layer version; a loss result keeps the undefended figure and, beside it, the defended
one, the protection level it was read against and why a figure has none. Which intensity layer served a flood figure is
recorded with it (the JRC European maps replace the global ones inside their coverage once checked), and so is the
publisher's caution where its spurious-depth mask touches the location.

  flood_protection_samples  new, append-only: layer, version, location, status, design_rp_years
  hazard_intensity_samples  + caution (the publisher's own caution at the location, or null)
  loss_results              + flood_layer, protection_rp_years, protection_basis, eal_defended_eur,
                              eal_defended_low_eur, eal_defended_high_eur, caution

Downgrade refuses while a protection sample, a caution or a defended figure is recorded.

Revision ID: loss_prot_20261016
Revises: loss_proj_20261007
"""
from typing import Sequence, Union

from alembic import op

revision: str = "loss_prot_20261016"
down_revision: Union[str, None] = "loss_proj_20261007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO flood_protection_samples (layer_key, layer_version, latitude, longitude, status, design_rp_years)
                VALUES ('probe', 'probe', 0, 0, 'sampled', 100);""",
    "cleanup": """ALTER TABLE flood_protection_samples DISABLE TRIGGER trg_flood_protection_samples_guard;
                  DELETE FROM flood_protection_samples WHERE layer_key = 'probe';
                  ALTER TABLE flood_protection_samples ENABLE TRIGGER trg_flood_protection_samples_guard;""",
}


def upgrade() -> None:
    op.execute("""
        CREATE TABLE flood_protection_samples (
            sample_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            layer_key        varchar(64) NOT NULL,
            layer_version    varchar(40) NOT NULL,
            latitude         double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
            longitude        double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
            status           varchar(16) NOT NULL CHECK (status IN ('sampled', 'no_value', 'outside_coverage')),
            design_rp_years  double precision CHECK (design_rp_years >= 1),
            sampled_at       timestamptz NOT NULL DEFAULT now(),
            CHECK ((status = 'sampled') = (design_rp_years IS NOT NULL))
        );
        CREATE UNIQUE INDEX ux_flood_protection_sample ON flood_protection_samples
            (layer_key, layer_version, latitude, longitude);
        CREATE FUNCTION guard_flood_protection_samples() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'flood_protection_samples is append-only: a new layer version adds new rows';
        END $$;
        CREATE TRIGGER trg_flood_protection_samples_guard BEFORE UPDATE OR DELETE ON flood_protection_samples
            FOR EACH ROW EXECUTE FUNCTION guard_flood_protection_samples();

        ALTER TABLE hazard_intensity_samples ADD COLUMN caution text;

        ALTER TABLE loss_results
            ADD COLUMN flood_layer           varchar(64),
            ADD COLUMN protection_rp_years   double precision CHECK (protection_rp_years >= 1),
            ADD COLUMN protection_basis      text,
            ADD COLUMN eal_defended_eur      numeric(18,2) CHECK (eal_defended_eur >= 0),
            ADD COLUMN eal_defended_low_eur  numeric(18,2) CHECK (eal_defended_low_eur >= 0),
            ADD COLUMN eal_defended_high_eur numeric(18,2) CHECK (eal_defended_high_eur >= 0),
            ADD COLUMN caution               text,
            ADD CONSTRAINT loss_results_defended_needs_figure CHECK (eal_defended_eur IS NULL OR
                (eal_eur IS NOT NULL AND protection_rp_years IS NOT NULL AND eal_defended_eur <= eal_eur)),
            ADD CONSTRAINT loss_results_defended_range CHECK ((eal_defended_eur IS NULL) =
                (eal_defended_low_eur IS NULL AND eal_defended_high_eur IS NULL));
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM flood_protection_samples)
               OR EXISTS (SELECT 1 FROM hazard_intensity_samples WHERE caution IS NOT NULL)
               OR EXISTS (SELECT 1 FROM loss_results WHERE flood_layer IS NOT NULL OR protection_basis IS NOT NULL
                          OR eal_defended_eur IS NOT NULL OR caution IS NOT NULL) THEN
                RAISE EXCEPTION 'protection samples, cautions or defended losses are recorded — they cannot be removed';
            END IF;
        END $$;
        ALTER TABLE loss_results DROP CONSTRAINT loss_results_defended_range,
            DROP CONSTRAINT loss_results_defended_needs_figure,
            DROP COLUMN caution, DROP COLUMN eal_defended_high_eur, DROP COLUMN eal_defended_low_eur,
            DROP COLUMN eal_defended_eur, DROP COLUMN protection_basis, DROP COLUMN protection_rp_years,
            DROP COLUMN flood_layer;
        ALTER TABLE hazard_intensity_samples DROP COLUMN caution;
        DROP TRIGGER trg_flood_protection_samples_guard ON flood_protection_samples;
        DROP FUNCTION guard_flood_protection_samples();
        DROP TABLE flood_protection_samples;
    """)

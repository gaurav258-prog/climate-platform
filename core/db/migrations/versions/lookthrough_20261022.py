"""The holdings look-through of the loss engine (the product owner's decisions of 2026-10-22).

A fund holding is a share in a company, never a building (E307); its loss is looked through to the issuer's located
sites. A site's figure is the share of its value lost per year — no site states a value of its own: the issuer's sites
carry only a weight, each site's share of the issuer. The holding's euros are that share × the issuer's physical asset
value × the holding's share of the issuer, both provided data.

  loss_runs          book + 'issuer_sites': the sites of the issuers an organisation's funds hold
  loss_results       asset_kind + 'issuer_site'; a figure is in euros (a stated value) or, for an issuer site and only
                     there, a share of the value its curve applies to:
                       + eal_ratio, eal_ratio_low, eal_ratio_high                       0..1, low ≤ central ≤ high
                       + eal_defended_ratio, eal_defended_ratio_low, eal_defended_ratio_high   ≤ the undefended share
                       + ratio_at_rp (jsonb): the share lost at each return period
  issuer_emissions   + physical_asset_value_eur: the issuer's physical asset value — buildings, plant, machinery and
                     contents, land excluded (the value an asset-value curve's share is taken of), as the manager states
                     it; a balance, converted at its date's closing rate like the enterprise value beside it

Downgrade refuses while an issuer-sites run, a share figure or a physical asset value is recorded.

Revision ID: lookthrough_20261022
Revises: latest_seq_tables_20261022
"""
from typing import Sequence, Union

from alembic import op

revision: str = "lookthrough_20261022"
down_revision: Union[str, None] = "latest_seq_tables_20261022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORG = "0bbe0bbe-0000-4000-8000-000000316a01"
RUN = "0bbe0bbe-0000-4000-8000-000000316a02"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{ORG}', 'refusal probe', 'asset_manager', 'DE');
                INSERT INTO loss_runs (run_id, org_id, book, scenario, time_horizon, as_of, engine_version, inputs, n_assets, n_gaps)
                VALUES ('{RUN}', '{ORG}', 'issuer_sites', 'baseline', 'current', '2026-10-22', 'probe', '{{}}', 0, 0);""",
    "cleanup": f"""ALTER TABLE loss_runs DISABLE TRIGGER trg_loss_runs_guard;
                  DELETE FROM loss_runs WHERE run_id = '{RUN}';
                  ALTER TABLE loss_runs ENABLE TRIGGER trg_loss_runs_guard;
                  DELETE FROM organizations WHERE org_id = '{ORG}';""",
}

_BOOKS = "'banking', 'insurance', 'insurer_investments', 'realestate', 'assetmgmt', 'company_sites'"
_KINDS = "'portfolio_entity', 'company_site'"


def upgrade() -> None:
    op.execute(f"""
        ALTER TABLE loss_runs DROP CONSTRAINT loss_runs_book_check,
            ADD CONSTRAINT loss_runs_book_check CHECK (book IN ({_BOOKS}, 'issuer_sites'));

        ALTER TABLE loss_results DROP CONSTRAINT loss_results_asset_kind_check,
            ADD CONSTRAINT loss_results_asset_kind_check CHECK (asset_kind IN ({_KINDS}, 'issuer_site')),
            ADD COLUMN eal_ratio               double precision CHECK (eal_ratio BETWEEN 0 AND 1),
            ADD COLUMN eal_ratio_low           double precision CHECK (eal_ratio_low BETWEEN 0 AND 1),
            ADD COLUMN eal_ratio_high          double precision CHECK (eal_ratio_high BETWEEN 0 AND 1),
            ADD COLUMN eal_defended_ratio      double precision CHECK (eal_defended_ratio BETWEEN 0 AND 1),
            ADD COLUMN eal_defended_ratio_low  double precision CHECK (eal_defended_ratio_low BETWEEN 0 AND 1),
            ADD COLUMN eal_defended_ratio_high double precision CHECK (eal_defended_ratio_high BETWEEN 0 AND 1),
            ADD COLUMN ratio_at_rp             jsonb,
            DROP CONSTRAINT loss_results_check,
            DROP CONSTRAINT loss_results_check1,
            DROP CONSTRAINT ck_loss_results_range,
            -- a figure is in euros or, for an issuer site and only there, a share — never both, never neither
            ADD CONSTRAINT loss_results_figure CHECK ((gap IS NULL) = (eal_eur IS NOT NULL OR eal_ratio IS NOT NULL)),
            ADD CONSTRAINT loss_results_figure_unit CHECK (
                (eal_ratio IS NOT NULL) = (gap IS NULL AND asset_kind = 'issuer_site')
                AND (eal_ratio IS NULL OR (eal_eur IS NULL AND exposed_value_eur IS NULL AND loss_at_rp IS NULL))),
            ADD CONSTRAINT loss_results_figure_inputs CHECK (gap IS NOT NULL OR (curve_key IS NOT NULL AND
                ((exposed_value_eur IS NOT NULL AND loss_at_rp IS NOT NULL) OR ratio_at_rp IS NOT NULL))),
            ADD CONSTRAINT ck_loss_results_range CHECK (gap IS NOT NULL
                OR (eal_eur IS NOT NULL AND eal_low_eur IS NOT NULL AND eal_high_eur IS NOT NULL
                    AND eal_low_eur <= eal_eur AND eal_eur <= eal_high_eur)
                OR (eal_ratio IS NOT NULL AND eal_ratio_low IS NOT NULL AND eal_ratio_high IS NOT NULL
                    AND eal_ratio_low <= eal_ratio AND eal_ratio <= eal_ratio_high)),
            ADD CONSTRAINT loss_results_defended_ratio CHECK (eal_defended_ratio IS NULL OR
                (eal_ratio IS NOT NULL AND protection_rp_years IS NOT NULL AND eal_defended_ratio <= eal_ratio)),
            ADD CONSTRAINT loss_results_defended_ratio_range CHECK ((eal_defended_ratio IS NULL) =
                (eal_defended_ratio_low IS NULL AND eal_defended_ratio_high IS NULL));

        ALTER TABLE issuer_emissions
            ADD COLUMN physical_asset_value_eur numeric(20,2) CHECK (physical_asset_value_eur > 0);
    """)


def downgrade() -> None:
    op.execute(f"""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM loss_runs WHERE book = 'issuer_sites')
               OR EXISTS (SELECT 1 FROM loss_results WHERE asset_kind = 'issuer_site' OR eal_ratio IS NOT NULL)
               OR EXISTS (SELECT 1 FROM issuer_emissions WHERE physical_asset_value_eur IS NOT NULL) THEN
                RAISE EXCEPTION 'issuer-site losses or physical asset values are recorded — they cannot be removed';
            END IF;
        END $$;
        ALTER TABLE issuer_emissions DROP COLUMN physical_asset_value_eur;

        ALTER TABLE loss_results DROP CONSTRAINT loss_results_defended_ratio_range,
            DROP CONSTRAINT loss_results_defended_ratio,
            DROP CONSTRAINT ck_loss_results_range,
            DROP CONSTRAINT loss_results_figure_inputs,
            DROP CONSTRAINT loss_results_figure_unit,
            DROP CONSTRAINT loss_results_figure,
            ADD CONSTRAINT loss_results_check CHECK ((gap IS NULL) = (eal_eur IS NOT NULL)),
            ADD CONSTRAINT loss_results_check1 CHECK (gap IS NOT NULL OR (curve_key IS NOT NULL AND
                exposed_value_eur IS NOT NULL AND loss_at_rp IS NOT NULL)),
            ADD CONSTRAINT ck_loss_results_range CHECK (gap IS NOT NULL OR (eal_low_eur IS NOT NULL AND
                eal_high_eur IS NOT NULL AND eal_low_eur <= eal_eur AND eal_eur <= eal_high_eur)),
            DROP COLUMN ratio_at_rp,
            DROP COLUMN eal_defended_ratio_high, DROP COLUMN eal_defended_ratio_low, DROP COLUMN eal_defended_ratio,
            DROP COLUMN eal_ratio_high, DROP COLUMN eal_ratio_low, DROP COLUMN eal_ratio,
            DROP CONSTRAINT loss_results_asset_kind_check,
            ADD CONSTRAINT loss_results_asset_kind_check CHECK (asset_kind IN ({_KINDS}));

        ALTER TABLE loss_runs DROP CONSTRAINT loss_runs_book_check,
            ADD CONSTRAINT loss_runs_book_check CHECK (book IN ({_BOOKS}));
    """)

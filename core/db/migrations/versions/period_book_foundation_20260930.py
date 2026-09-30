"""The reporting year in the database: dated assets, year-end values, the year-end close, snapshots per period and
undertaking, and dated protected-area layers.

A sustainability statement covers the same reporting period and the same undertaking (or group) as the financial
statements (Delegated Regulation (EU) 2023/2772, ESRS 1 §73, ESRS 2 BP-1 §5(b)(i)); it prints the previous period
beside the current one (ESRS 1 §83) and corrects a material prior-period error by restating it (§96; §98 as amended
by Delegated Regulation (EU) 2026/1563). Its figures are of two kinds: positions at the reporting date (the carrying
amount of assets at material physical risk, as a share of total assets in the balance sheet — ESRS E1 AR 69(a) / §39
as amended; own sites in or near biodiversity-sensitive areas and their area — ESRS E4 §35) and totals over the year.

  sc_company_sites / sc_sourcing_plots   held_from / held_until: when the undertaking held the site or sourced from the
                                         plot (NULL = before / after records); area_ha on sites (ESRS E4 §35);
                                         entity links enforced (SET NULL on delete, as delete_entity already unassigns)
  site_period_values                     a site's year-end carrying amount and the year's net revenue it carries, as
                                         finance states them — append-only; the live value is the latest statement (a
                                         site or undertaking with year-end values is not deleted: it stops being held)
  reporting_period_close                 the year-end close of one undertaking (NULL entity = the organisation itself)
                                         and period, approved by a second person — append-only; after it, a
                                         period-keyed value (provided_datapoint, site_period_values) is refused
                                         unless it carries a restatement reason
  report_snapshots                       period_end and reporting_entity_id read from the frozen record; a version is
                                         counted per report type, period and undertaking
  protected_dataset_loads                every load of a protected-area layer kept, the current one per dataset open;
                                         protected_h3_cell rows belong to a load (a filing names the loads it read)

Revision ID: period_book_foundation_20260930
Revises: answers_entity_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "period_book_foundation_20260930"
down_revision: Union[str, None] = "answers_entity_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROBE_ORG = "0bbe0bbe-0000-4000-8000-00000000fee7"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_PROBE_ORG}', 'refusal probe', 'agriculture', 'ES');
                 INSERT INTO sc_company_sites (org_id, name, area_ha) VALUES ('{_PROBE_ORG}', 'probe site', 12.5);""",
    "cleanup": f"""DELETE FROM sc_company_sites WHERE org_id = '{_PROBE_ORG}';
                   DELETE FROM organizations WHERE org_id = '{_PROBE_ORG}';""",
}


def upgrade() -> None:
    # ── parsing helpers a generated column may call (a text→date / text→uuid cast is not immutable) ──
    op.execute("""
        CREATE FUNCTION iso_date_or_null(t text) RETURNS date LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
            SELECT CASE WHEN t ~ '^\\d{4}-\\d{2}-\\d{2}'
                        THEN make_date(substr(t, 1, 4)::int, substr(t, 6, 2)::int, substr(t, 9, 2)::int) END $$;
        CREATE FUNCTION uuid_or_null(t text) RETURNS uuid LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
            SELECT CASE WHEN t ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN t::uuid END $$;
    """)

    # ── dated assets, site area, enforced links ──
    op.execute("""
        ALTER TABLE sc_company_sites
            ADD COLUMN held_from DATE, ADD COLUMN held_until DATE,
            ADD COLUMN area_ha NUMERIC CONSTRAINT ck_site_area_ha CHECK (area_ha IS NULL OR area_ha >= 0),
            ADD CONSTRAINT ck_site_held CHECK (held_from IS NULL OR held_until IS NULL OR held_until > held_from),
            ADD CONSTRAINT fk_site_org FOREIGN KEY (org_id) REFERENCES organizations(org_id) ON DELETE CASCADE,
            ADD CONSTRAINT fk_site_entity FOREIGN KEY (entity_id) REFERENCES reporting_entities(entity_id) ON DELETE SET NULL;
        ALTER TABLE sc_sourcing_plots
            ADD COLUMN held_from DATE, ADD COLUMN held_until DATE,
            ADD CONSTRAINT ck_plot_held CHECK (held_from IS NULL OR held_until IS NULL OR held_until > held_from),
            ADD CONSTRAINT fk_plot_entity FOREIGN KEY (entity_id) REFERENCES reporting_entities(entity_id) ON DELETE SET NULL;
        COMMENT ON COLUMN sc_company_sites.held_from IS 'first day the undertaking held the site (NULL: before records)';
        COMMENT ON COLUMN sc_company_sites.held_until IS 'first day it no longer held it (NULL: still held)';
        COMMENT ON COLUMN sc_sourcing_plots.held_from IS 'first day the undertaking sourced from the plot (NULL: before records)';
        COMMENT ON COLUMN sc_sourcing_plots.held_until IS 'first day it no longer sourced from it (NULL: still sourcing)';
    """)

    # ── the year-end close ──
    op.execute("""
        CREATE TABLE reporting_period_close (
            close_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id              UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            reporting_entity_id UUID REFERENCES reporting_entities(entity_id) ON DELETE RESTRICT,
            period_end          DATE NOT NULL,
            requested_by        UUID NOT NULL,
            approved_by         UUID NOT NULL,
            approval_request_id UUID,
            note                TEXT,
            closed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_period_close_four_eyes CHECK (requested_by <> approved_by)
        );
        CREATE UNIQUE INDEX ux_period_close ON reporting_period_close (org_id, reporting_entity_id, period_end) NULLS NOT DISTINCT;
        CREATE FUNCTION prevent_period_close_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'reporting_period_close is append-only: a closed period is changed only by restatement';
        END $$;
        CREATE TRIGGER trg_period_close_worm BEFORE UPDATE OR DELETE ON reporting_period_close
            FOR EACH ROW EXECUTE FUNCTION prevent_period_close_mutation();
        CREATE FUNCTION period_closed(o uuid, e uuid, pe date) RETURNS boolean LANGUAGE sql STABLE AS $$
            SELECT pe IS NOT NULL AND EXISTS (SELECT 1 FROM reporting_period_close c
                          WHERE c.org_id = o AND c.reporting_entity_id IS NOT DISTINCT FROM e AND c.period_end = pe) $$;
    """)

    # ── year-end values of a site, as finance states them ──
    op.execute("""
        CREATE TABLE site_period_values (
            value_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq                 BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            org_id              UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            site_id             UUID NOT NULL REFERENCES sc_company_sites(site_id) ON DELETE RESTRICT,
            reporting_entity_id UUID REFERENCES reporting_entities(entity_id) ON DELETE RESTRICT,
            period_end          DATE NOT NULL,
            measure             TEXT NOT NULL CONSTRAINT ck_site_period_measure CHECK (measure IN ('carrying_amount', 'net_revenue')),
            amount              NUMERIC NOT NULL CONSTRAINT ck_site_period_amount CHECK (amount >= 0),
            currency            CHAR(3) NOT NULL,
            amount_eur          NUMERIC NOT NULL CONSTRAINT ck_site_period_amount_eur CHECK (amount_eur >= 0),
            money_source        JSONB,
            source              TEXT NOT NULL,
            batch_id            UUID,
            restatement_reason  TEXT,
            recorded_by         UUID,
            recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        COMMENT ON TABLE site_period_values IS
            'carrying_amount: at period_end (balance sheet); net_revenue: over the year ending period_end. Append-only: the live value is the latest statement (highest seq).';
        CREATE INDEX ix_site_period_values ON site_period_values (org_id, period_end, measure, site_id, seq DESC);
        CREATE VIEW v_site_period_values_live AS
            SELECT DISTINCT ON (site_id, period_end, measure) *
            FROM site_period_values ORDER BY site_id, period_end, measure, seq DESC;
        CREATE FUNCTION prevent_site_period_value_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'site_period_values is append-only: state a new value instead';
        END $$;
        CREATE TRIGGER trg_site_period_values_worm BEFORE UPDATE OR DELETE ON site_period_values
            FOR EACH ROW EXECUTE FUNCTION prevent_site_period_value_mutation();
    """)

    # ── after the close, a period-keyed value is a restatement ──
    op.execute("""
        ALTER TABLE provided_datapoint ADD COLUMN restatement_reason TEXT;
        CREATE FUNCTION refuse_closed_period_value() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE pe date; ent uuid;
        BEGIN
            IF TG_TABLE_NAME = 'provided_datapoint' THEN pe := NEW.reporting_period_end; ELSE pe := NEW.period_end; END IF;
            ent := NEW.reporting_entity_id;
            IF period_closed(NEW.org_id, ent, pe) AND COALESCE(btrim(NEW.restatement_reason), '') = '' THEN
                RAISE EXCEPTION 'the period ending % is closed for this undertaking: a new value is a restatement and needs its reason', pe;
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER trg_provided_closed_period BEFORE INSERT ON provided_datapoint
            FOR EACH ROW EXECUTE FUNCTION refuse_closed_period_value();
        CREATE TRIGGER trg_site_period_values_closed BEFORE INSERT ON site_period_values
            FOR EACH ROW EXECUTE FUNCTION refuse_closed_period_value();
    """)

    # ── snapshots per period and undertaking ──
    op.execute("""
        ALTER TABLE report_snapshots
            ADD COLUMN period_end DATE GENERATED ALWAYS AS (iso_date_or_null(reporting_basis->>'reporting_period_end')) STORED,
            ADD COLUMN reporting_entity_id UUID GENERATED ALWAYS AS (uuid_or_null(payload->'_scope'->>'reporting_entity_id')) STORED;
        ALTER TABLE report_snapshots DROP CONSTRAINT report_snapshots_org_id_report_type_version_key;
        CREATE UNIQUE INDEX ux_report_snapshots_scope_version
            ON report_snapshots (org_id, report_type, period_end, reporting_entity_id, version) NULLS NOT DISTINCT;
    """)

    # ── dated protected-area layers ──
    op.execute("""
        CREATE TABLE protected_dataset_loads (
            load_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            dataset      TEXT NOT NULL,
            data_vintage DATE,
            source       TEXT,
            n_cells      INTEGER,
            loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            retired_at   TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX ux_protected_load_current ON protected_dataset_loads (dataset) WHERE retired_at IS NULL;
        INSERT INTO protected_dataset_loads (dataset, data_vintage, source, n_cells)
            SELECT dataset, MAX(data_vintage), 'loaded before load history was kept', COUNT(*) FROM protected_h3_cell GROUP BY dataset;
        ALTER TABLE protected_h3_cell ADD COLUMN load_id UUID REFERENCES protected_dataset_loads(load_id) ON DELETE CASCADE;
        UPDATE protected_h3_cell c SET load_id = l.load_id FROM protected_dataset_loads l WHERE l.dataset = c.dataset;
        ALTER TABLE protected_h3_cell ALTER COLUMN load_id SET NOT NULL;
        ALTER TABLE protected_h3_cell DROP CONSTRAINT protected_h3_cell_pkey;
        ALTER TABLE protected_h3_cell ADD CONSTRAINT protected_h3_cell_pkey PRIMARY KEY (load_id, h3_cell);
        CREATE INDEX ix_protected_h3_cell ON protected_h3_cell (h3_cell);
        CREATE VIEW v_protected_h3_current AS
            SELECT c.* FROM protected_h3_cell c JOIN protected_dataset_loads l ON l.load_id = c.load_id WHERE l.retired_at IS NULL;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM sc_company_sites WHERE held_from IS NOT NULL OR held_until IS NOT NULL OR area_ha IS NOT NULL)
               OR EXISTS (SELECT 1 FROM sc_sourcing_plots WHERE held_from IS NOT NULL OR held_until IS NOT NULL)
               OR EXISTS (SELECT 1 FROM site_period_values) OR EXISTS (SELECT 1 FROM reporting_period_close)
               OR EXISTS (SELECT 1 FROM provided_datapoint WHERE restatement_reason IS NOT NULL)
               OR EXISTS (SELECT 1 FROM protected_dataset_loads GROUP BY dataset HAVING COUNT(*) > 1)
               OR EXISTS (SELECT 1 FROM report_snapshots GROUP BY org_id, report_type, version HAVING COUNT(*) > 1) THEN
                RAISE EXCEPTION 'cannot downgrade period_book_foundation_20260930: assets carry held dates or areas, year-end '
                                'values or closes exist, a value was restated, a protected layer has history, or snapshot '
                                'versions are counted per period and undertaking';
            END IF;
        END $$;
    """)
    op.execute("""
        DROP VIEW v_protected_h3_current;
        DROP INDEX ix_protected_h3_cell;
        ALTER TABLE protected_h3_cell DROP CONSTRAINT protected_h3_cell_pkey;
        ALTER TABLE protected_h3_cell ADD CONSTRAINT protected_h3_cell_pkey PRIMARY KEY (h3_cell, dataset);
        ALTER TABLE protected_h3_cell DROP COLUMN load_id;
        DROP TABLE protected_dataset_loads;

        DROP INDEX ux_report_snapshots_scope_version;
        ALTER TABLE report_snapshots ADD CONSTRAINT report_snapshots_org_id_report_type_version_key UNIQUE (org_id, report_type, version);
        ALTER TABLE report_snapshots DROP COLUMN reporting_entity_id, DROP COLUMN period_end;

        DROP TRIGGER trg_site_period_values_closed ON site_period_values;
        DROP TRIGGER trg_provided_closed_period ON provided_datapoint;
        DROP FUNCTION refuse_closed_period_value();
        ALTER TABLE provided_datapoint DROP COLUMN restatement_reason;

        DROP VIEW v_site_period_values_live;
        DROP TABLE site_period_values;
        DROP FUNCTION prevent_site_period_value_mutation();

        DROP FUNCTION period_closed(uuid, uuid, date);
        DROP TABLE reporting_period_close;
        DROP FUNCTION prevent_period_close_mutation();

        ALTER TABLE sc_sourcing_plots DROP CONSTRAINT fk_plot_entity, DROP CONSTRAINT ck_plot_held,
            DROP COLUMN held_until, DROP COLUMN held_from;
        ALTER TABLE sc_company_sites DROP CONSTRAINT fk_site_entity, DROP CONSTRAINT fk_site_org, DROP CONSTRAINT ck_site_held,
            DROP COLUMN area_ha, DROP COLUMN held_until, DROP COLUMN held_from;

        DROP FUNCTION uuid_or_null(text);
        DROP FUNCTION iso_date_or_null(text);
    """)

"""EUDR foundation, layer 1: the records Regulation (EU) 2023/1115 (as amended by 2024/3234, 2025/2650, 2026/2102) asks
for, before any statement is built on them (E90).

  eudr_undertaking_statement  who the undertaking is for EUDR on a date — size class within the meaning of Directive
                              2013/34/EU Art. 3 (Art. 2(30) 'SME'; Art. 2(15a) micro / small), the date it was
                              established as such (Art. 38(3): 'established as such by 31 December 2024'), country,
                              EORI (Annex II point 1). Stated by one person, approved by another; append-only.
  eudr_movement               one placing on the market, making available or export of a relevant product (Art. 4(2):
                              'prior submission of a due diligence statement'; Art. 5) with the actor's role in it,
                              HS code, description, trade name, scientific names, quantity (Annex II point 2 / Art.
                              9(1)(b): net mass in kg, a percentage estimate or deviation, a supplementary unit, volume
                              or items), supplier and customer (Art. 9(1)(e)-(f)), and the DDS reference numbers or
                              declaration identifiers received from an operator supplier (Art. 5(3)(a)).
  eudr_movement_plot          the plots a movement's commodities were produced on and 'the date or time range of
                              production' (Art. 9(1)(d)).
  eudr_plot_assessment        each satellite reading of a plot, kept (append-only): the dataset and version, the
                              geometry read, what was found — never a verdict (E91, the user's decision: tree-cover
                              loss is a risk the operator assesses, Art. 10; deforestation is conversion to
                              agricultural use, Art. 2(3)).
  eudr_dds_reference          the reference and verification numbers the information system returns for a statement
                              (Art. 4(2), 33; IR 2024/3084), append-only, a reference number once.
  parties                     suppliers and customers gain the trade name and web address Art. 5(3)(a)-(b) list.
  regulatory_filing           a statement's subject is its movement (eudr_movement_id); the one-live-filing rule now
                              counts the fund and the movement too — it ignored fund_id, so a second fund's periodic
                              document for the same period was refused (E90).

Revision ID: eudr_foundation_20261001
Revises: kri_reanchor_20261001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "eudr_foundation_20261001"
down_revision: Union[str, None] = "kri_reanchor_20261001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORG = "0bbe0bbe-0000-4000-8000-00000000feef"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_ORG}', 'refusal probe', 'manufacturer', 'NL');
                 INSERT INTO eudr_movement (org_id, kind, actor_role, planned_on, hs_code, description, customs_flow, net_mass_kg)
                 VALUES ('{_ORG}', 'placing', 'operator', '2027-01-15', '180100', 'probe cocoa beans', true, 1000);""",
    "cleanup": f"""DELETE FROM eudr_movement WHERE org_id = '{_ORG}';
                   DELETE FROM organizations WHERE org_id = '{_ORG}';""",
}

_WORM = """
    CREATE FUNCTION prevent_{t}_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION '{t} is append-only: record it again'; END $$;
    CREATE TRIGGER trg_{t}_worm BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION prevent_{t}_mutation();
"""


def upgrade() -> None:
    op.execute("""
        CREATE TABLE eudr_undertaking_statement (
            statement_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq                  BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            org_id               UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            reporting_entity_id  UUID REFERENCES reporting_entities(entity_id) ON DELETE RESTRICT,
            effective_from       DATE NOT NULL,
            size_class           TEXT NOT NULL CONSTRAINT ck_eudr_size CHECK (size_class IN ('micro', 'small', 'medium', 'large')),
            established_on       DATE,
            country              CHAR(2) NOT NULL CONSTRAINT ck_eudr_country CHECK (country ~ '^[A-Z]{2}$'),
            eori                 TEXT CONSTRAINT ck_eudr_eori CHECK (eori IS NULL OR eori ~ '^[A-Z]{2}[A-Z0-9]{1,15}$'),
            basis                TEXT,
            requested_by         UUID NOT NULL,
            approved_by          UUID NOT NULL,
            approval_request_id  UUID,
            recorded_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_eudr_statement_four_eyes CHECK (requested_by <> approved_by)
        );
        CREATE INDEX ix_eudr_statement ON eudr_undertaking_statement (org_id, reporting_entity_id, effective_from, seq DESC);
    """ + _WORM.format(t="eudr_undertaking_statement") + """
        ALTER TABLE sc_suppliers ADD COLUMN trade_name TEXT, ADD COLUMN web_address TEXT;
        ALTER TABLE sc_customers ADD COLUMN trade_name TEXT, ADD COLUMN web_address TEXT;

        CREATE TABLE eudr_movement (
            movement_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq                  BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            org_id               UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            reporting_entity_id  UUID REFERENCES reporting_entities(entity_id) ON DELETE RESTRICT,
            external_ref         TEXT,
            kind                 TEXT NOT NULL CONSTRAINT ck_eudr_kind CHECK (kind IN ('placing', 'making_available', 'export')),
            actor_role           TEXT NOT NULL CONSTRAINT ck_eudr_role
                                 CHECK (actor_role IN ('operator', 'micro_small_primary_operator', 'downstream_operator', 'trader')),
            planned_on           DATE NOT NULL,
            hs_code              TEXT NOT NULL CONSTRAINT ck_eudr_hs CHECK (hs_code ~ '^[0-9]{4}([0-9]{2}){0,3}$'),
            description          TEXT NOT NULL,
            trade_name           TEXT,
            scientific_names     TEXT[],
            customs_flow         BOOLEAN NOT NULL,
            net_mass_kg          NUMERIC CONSTRAINT ck_eudr_mass CHECK (net_mass_kg IS NULL OR net_mass_kg > 0),
            mass_deviation_pct   NUMERIC CONSTRAINT ck_eudr_dev CHECK (mass_deviation_pct IS NULL OR mass_deviation_pct BETWEEN 0 AND 100),
            supplementary_unit   TEXT,
            supplementary_qty    NUMERIC CONSTRAINT ck_eudr_supp CHECK (supplementary_qty IS NULL OR supplementary_qty > 0),
            volume_m3            NUMERIC CONSTRAINT ck_eudr_vol CHECK (volume_m3 IS NULL OR volume_m3 > 0),
            items_count          INTEGER CONSTRAINT ck_eudr_items CHECK (items_count IS NULL OR items_count > 0),
            supplier_id          UUID REFERENCES sc_suppliers(supplier_id) ON DELETE RESTRICT,
            customer_id          UUID REFERENCES sc_customers(customer_id) ON DELETE RESTRICT,
            upstream_refs        TEXT[],
            created_by           UUID,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            -- Annex II point 2 / Art. 9(1)(b): goods passing customs in kilograms of net mass
            CONSTRAINT ck_eudr_customs_mass CHECK (NOT customs_flow OR net_mass_kg IS NOT NULL),
            CONSTRAINT ck_eudr_supp_pair CHECK ((supplementary_unit IS NULL) = (supplementary_qty IS NULL)),
            CONSTRAINT ck_eudr_quantity CHECK (net_mass_kg IS NOT NULL OR volume_m3 IS NOT NULL OR items_count IS NOT NULL),
            CONSTRAINT ux_eudr_movement_ref UNIQUE (org_id, external_ref)
        );
        CREATE INDEX ix_eudr_movement ON eudr_movement (org_id, planned_on);

        CREATE TABLE eudr_movement_plot (
            movement_id          UUID NOT NULL REFERENCES eudr_movement(movement_id) ON DELETE CASCADE,
            plot_id              UUID NOT NULL REFERENCES sc_sourcing_plots(plot_id) ON DELETE RESTRICT,
            production_from      DATE NOT NULL,
            production_to        DATE NOT NULL,
            PRIMARY KEY (movement_id, plot_id),
            CONSTRAINT ck_eudr_production CHECK (production_from <= production_to)
        );

        CREATE TABLE eudr_plot_assessment (
            assessment_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq                  BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            plot_id              UUID NOT NULL REFERENCES sc_sourcing_plots(plot_id) ON DELETE RESTRICT,
            dataset              TEXT NOT NULL,
            dataset_version      TEXT NOT NULL,
            geometry_sha256      TEXT NOT NULL,
            cutoff               DATE NOT NULL,
            outcome              TEXT NOT NULL CONSTRAINT ck_eudr_outcome
                                 CHECK (outcome IN ('no_loss_detected', 'loss_after_cutoff', 'not_assessable')),
            loss_ha              NUMERIC CONSTRAINT ck_eudr_loss CHECK (loss_ha IS NULL OR loss_ha >= 0),
            first_loss_year      INTEGER,
            reason               TEXT,
            method               JSONB NOT NULL DEFAULT '{}'::jsonb,
            assessed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            assessed_by          UUID,
            CONSTRAINT ck_eudr_unassessable CHECK (outcome <> 'not_assessable' OR reason IS NOT NULL)
        );
        CREATE INDEX ix_eudr_plot_assessment ON eudr_plot_assessment (plot_id, seq DESC);
    """ + _WORM.format(t="eudr_plot_assessment") + """
        CREATE TABLE eudr_dds_reference (
            reference_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq                  BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            filing_id            UUID NOT NULL REFERENCES regulatory_filing(filing_id) ON DELETE RESTRICT,
            reference_number     TEXT NOT NULL CONSTRAINT ux_eudr_reference UNIQUE,
            verification_number  TEXT,
            source               TEXT NOT NULL CONSTRAINT ck_eudr_ref_source
                                 CHECK (source IN ('information_system', 'manual_entry', 'contingency')),
            received_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            recorded_by          UUID
        );
        CREATE INDEX ix_eudr_dds_reference ON eudr_dds_reference (filing_id, seq DESC);
    """ + _WORM.format(t="eudr_dds_reference") + """
        ALTER TABLE regulatory_filing ADD COLUMN eudr_movement_id UUID REFERENCES eudr_movement(movement_id) ON DELETE RESTRICT;
        ALTER TABLE regulatory_filing ADD CONSTRAINT ck_regulatory_filing_one_subject
            CHECK (fund_id IS NULL OR eudr_movement_id IS NULL);
        DROP INDEX ux_reg_filing_live;
        CREATE UNIQUE INDEX ux_reg_filing_live ON regulatory_filing (org_id, framework, period_end,
            COALESCE(entity_id, '00000000-0000-0000-0000-000000000000'::uuid),
            COALESCE(fund_id, '00000000-0000-0000-0000-000000000000'::uuid),
            COALESCE(eudr_movement_id, '00000000-0000-0000-0000-000000000000'::uuid))
            WHERE status <> ALL (ARRAY['superseded', 'withdrawn']);

        -- a movement in a statement that is not a withdrawn or superseded draft is what the statement says: frozen
        CREATE FUNCTION prevent_filed_movement_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM regulatory_filing f WHERE f.eudr_movement_id = OLD.movement_id
                       AND f.status NOT IN ('draft', 'returned', 'withdrawn', 'superseded')) THEN
                RAISE EXCEPTION 'movement % is in a statement under review or filed: it cannot change', OLD.movement_id;
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END $$;
        CREATE TRIGGER trg_eudr_movement_frozen BEFORE UPDATE OR DELETE ON eudr_movement
            FOR EACH ROW EXECUTE FUNCTION prevent_filed_movement_change();
        CREATE FUNCTION prevent_filed_movement_plot_change() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE m UUID := CASE WHEN TG_OP = 'INSERT' THEN NEW.movement_id ELSE OLD.movement_id END;
        BEGIN
            IF EXISTS (SELECT 1 FROM regulatory_filing f WHERE f.eudr_movement_id = m
                       AND f.status NOT IN ('draft', 'returned', 'withdrawn', 'superseded')) THEN
                RAISE EXCEPTION 'movement % is in a statement under review or filed: its plots cannot change', m;
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END $$;
        CREATE TRIGGER trg_eudr_movement_plot_frozen BEFORE INSERT OR UPDATE OR DELETE ON eudr_movement_plot
            FOR EACH ROW EXECUTE FUNCTION prevent_filed_movement_plot_change();
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM eudr_movement) OR EXISTS (SELECT 1 FROM eudr_plot_assessment)
               OR EXISTS (SELECT 1 FROM eudr_undertaking_statement) OR EXISTS (SELECT 1 FROM eudr_dds_reference)
               OR EXISTS (SELECT 1 FROM regulatory_filing WHERE status NOT IN ('superseded', 'withdrawn')
                          GROUP BY org_id, framework, period_end, entity_id HAVING count(*) > 1) THEN
                RAISE EXCEPTION 'cannot downgrade eudr_foundation_20261001: EUDR records are held, or two live filings '
                                'share a period that the older one-filing rule would refuse';
            END IF;
        END $$;
    """)
    op.execute("""
        DROP INDEX ux_reg_filing_live;
        CREATE UNIQUE INDEX ux_reg_filing_live ON regulatory_filing (org_id, framework, period_end,
            COALESCE(entity_id, '00000000-0000-0000-0000-000000000000'::uuid))
            WHERE status <> ALL (ARRAY['superseded', 'withdrawn']);
        ALTER TABLE regulatory_filing DROP CONSTRAINT ck_regulatory_filing_one_subject;
        ALTER TABLE regulatory_filing DROP COLUMN eudr_movement_id;
        DROP TABLE eudr_dds_reference; DROP FUNCTION prevent_eudr_dds_reference_mutation();
        DROP TABLE eudr_plot_assessment; DROP FUNCTION prevent_eudr_plot_assessment_mutation();
        DROP TABLE eudr_movement_plot; DROP FUNCTION prevent_filed_movement_plot_change();
        DROP TABLE eudr_movement; DROP FUNCTION prevent_filed_movement_change();
        ALTER TABLE sc_customers DROP COLUMN trade_name, DROP COLUMN web_address;
        ALTER TABLE sc_suppliers DROP COLUMN trade_name, DROP COLUMN web_address;
        DROP TABLE eudr_undertaking_statement; DROP FUNCTION prevent_eudr_undertaking_statement_mutation();
    """)

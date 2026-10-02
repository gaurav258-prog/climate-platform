"""EUDR simplified declaration — the foundation (E115). Regulation (EU) 2023/1115 as amended by 2025/2650, Article 4a and
Annex III; Implementing Regulation (EU) 2024/3084 as amended by 2026/1565, Articles 4a, 7 and 8.

  eudr_undertaking_statement  + primary_own_produce: the undertaking states it places products it itself grew, harvested,
                                obtained from or raised on plots in its country (Art. 2(15a)) — NULL: not stated
                              + other_system: the Union or Member State system holding all Annex III information, where
                                the undertaking states one (Art. 4a(4)) — NULL: none
  sc_sourcing_plots           + postal_address: 'the geolocation … may be replaced by the postal address' (Art. 4a(5))
  eudr_declaration_line       each relevant product the declaration names, with its one-off estimated annual quantity
                              (Annex III point 2), and — where Annex I leaves its scope open — the operator's statement of
                              whether it is in scope and why; a line is removed by dating it, never deleted
  eudr_declaration_identifier the declaration identifier and verification number the information system assigns (IR Art. 7),
                              append-only, one per filing — an update keeps the identifier (IR Art. 4a(3))
  regulatory_filing           framework 'eudr_simplified': labelled by its date; accepted only with its identifier; rejected
                              (Art. 8) or withdrawn (Art. 4a(6)) once submitted — not withdrawn once grouped (Art. 4a(7))

Revision ID: eudr_declaration_20261002
Revises: p3_t1_liabilities_20261001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "eudr_declaration_20261002"
down_revision: Union[str, None] = "p3_t1_liabilities_20261001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORG = "0bbe0bbe-0000-4000-8000-00000000fef8"
_F = "0bbe0bbe-0000-4000-8000-00000000fea8"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_ORG}', 'refusal probe', 'manufacturer', 'GH');
                 INSERT INTO regulatory_filing (filing_id, org_id, framework, period_end, period_label, status)
                 VALUES ('{_F}', '{_ORG}', 'eudr_simplified', '2027-01-15', 'declaration · 2027-01-15', 'draft');""",
    "cleanup": f"""ALTER TABLE regulatory_filing DISABLE TRIGGER USER;
                   DELETE FROM regulatory_filing WHERE filing_id = '{_F}';
                   ALTER TABLE regulatory_filing ENABLE TRIGGER USER;
                   DELETE FROM organizations WHERE org_id = '{_ORG}';""",
}

# self-contained (E25): the guard as eudr_filing_20261001 defined it, restored on downgrade
PRIOR_GUARD = "\nCREATE OR REPLACE FUNCTION guard_filing_transition() RETURNS trigger AS $$\nBEGIN\n    -- withdrawn is terminal: the discarded draft keeps its status and frozen content for good\n    IF OLD.status = 'withdrawn' THEN\n        IF NEW.status <> 'withdrawn'\n           OR NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id\n           OR NEW.period_end <> OLD.period_end\n           OR NEW.framework <> OLD.framework\n           OR NEW.entity_id IS DISTINCT FROM OLD.entity_id THEN\n            RAISE EXCEPTION 'filing % is withdrawn — it cannot change', OLD.filing_id;\n        END IF;\n    END IF;\n    -- only a filing nothing has signed off may be withdrawn — except an EUDR statement the information system has\n    -- given its reference number, within the window the service checks (IR 2024/3084 Art. 5(1))\n    IF NEW.status = 'withdrawn' AND OLD.status NOT IN ('draft','returned','withdrawn')\n       AND NOT (OLD.framework = 'eudr_dds' AND OLD.status = 'accepted') THEN\n        RAISE EXCEPTION 'filing % is % — only a draft or returned filing can be withdrawn', OLD.filing_id, OLD.status;\n    END IF;\n    IF OLD.status IN ('submitted','accepted') THEN\n        -- content is frozen once filed\n        IF NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id\n           OR NEW.period_end <> OLD.period_end\n           OR NEW.framework <> OLD.framework THEN\n            RAISE EXCEPTION 'filing % is % — its frozen content cannot change (restate via supersession)',\n                            OLD.filing_id, OLD.status;\n        END IF;\n        -- an EUDR statement is accepted by the information system making its reference number available: never\n        -- without one recorded (Art. 4(2), 33; IR 2024/3084)\n        IF NEW.status = 'accepted' AND OLD.status = 'submitted' AND OLD.framework = 'eudr_dds'\n           AND NOT EXISTS (SELECT 1 FROM eudr_dds_reference r WHERE r.filing_id = OLD.filing_id) THEN\n            RAISE EXCEPTION 'filing % is accepted when its reference number is recorded (EUDR → the shipment)', OLD.filing_id;\n        END IF;\n        -- an EUDR statement may be rejected by the authority only before its reference number is available (Art. 8(1))\n        IF NEW.status = 'rejected' AND OLD.framework = 'eudr_dds' AND OLD.status = 'submitted'\n           AND EXISTS (SELECT 1 FROM eudr_dds_event e WHERE e.filing_id = OLD.filing_id AND e.kind = 'reference_received') THEN\n            RAISE EXCEPTION 'filing % has its reference number — it can no longer be rejected (IR 2024/3084 Art. 8(1))',\n                            OLD.filing_id;\n        END IF;\n        -- status may only move forward: submitted→accepted, or either→superseded; an EUDR statement also\n        -- submitted→rejected (Art. 8) and accepted→withdrawn (Art. 5(1))\n        IF NEW.status <> OLD.status\n           AND NOT (OLD.status = 'submitted' AND NEW.status = 'accepted')\n           AND NOT (OLD.framework = 'eudr_dds' AND OLD.status = 'submitted' AND NEW.status = 'rejected')\n           AND NOT (OLD.framework = 'eudr_dds' AND OLD.status = 'accepted' AND NEW.status = 'withdrawn')\n           AND NEW.status <> 'superseded' THEN\n            RAISE EXCEPTION 'filing % is % and can only be accepted or superseded, not changed to %',\n                            OLD.filing_id, OLD.status, NEW.status;\n        END IF;\n    END IF;\n    NEW.updated_at := now();\n    RETURN NEW;\nEND;\n$$ LANGUAGE plpgsql;\n"

GUARD = "\nCREATE OR REPLACE FUNCTION guard_filing_transition() RETURNS trigger AS $$\nBEGIN\n    -- withdrawn is terminal: the discarded draft keeps its status and frozen content for good\n    IF OLD.status = 'withdrawn' THEN\n        IF NEW.status <> 'withdrawn'\n           OR NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id\n           OR NEW.period_end <> OLD.period_end\n           OR NEW.framework <> OLD.framework\n           OR NEW.entity_id IS DISTINCT FROM OLD.entity_id THEN\n            RAISE EXCEPTION 'filing % is withdrawn — it cannot change', OLD.filing_id;\n        END IF;\n    END IF;\n    -- only a filing nothing has signed off may be withdrawn — except an EUDR statement the information system has\n    -- given its reference number, within the window the service checks (IR 2024/3084 Art. 5(1))\n    IF NEW.status = 'withdrawn' AND OLD.status NOT IN ('draft','returned','withdrawn')\n       AND NOT (OLD.framework = 'eudr_dds' AND OLD.status = 'accepted')\n       AND NOT (OLD.framework = 'eudr_simplified' AND OLD.status IN ('submitted', 'accepted')) THEN\n        RAISE EXCEPTION 'filing % is % — only a draft or returned filing can be withdrawn', OLD.filing_id, OLD.status;\n    END IF;\n    IF OLD.status IN ('submitted','accepted') THEN\n        -- content is frozen once filed\n        IF NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id\n           OR NEW.period_end <> OLD.period_end\n           OR NEW.framework <> OLD.framework THEN\n            RAISE EXCEPTION 'filing % is % — its frozen content cannot change (restate via supersession)',\n                            OLD.filing_id, OLD.status;\n        END IF;\n        -- an EUDR statement is accepted by the information system making its reference number available: never\n        -- without one recorded (Art. 4(2), 33; IR 2024/3084)\n        IF NEW.status = 'accepted' AND OLD.status = 'submitted' AND OLD.framework = 'eudr_dds'\n           AND NOT EXISTS (SELECT 1 FROM eudr_dds_reference r WHERE r.filing_id = OLD.filing_id) THEN\n            RAISE EXCEPTION 'filing % is accepted when its reference number is recorded (EUDR → the shipment)', OLD.filing_id;\n        END IF;\n        -- a simplified declaration is accepted by the information system assigning its declaration identifier (IR Art. 7(1))\n        IF NEW.status = 'accepted' AND OLD.status = 'submitted' AND OLD.framework = 'eudr_simplified'\n           AND NOT EXISTS (SELECT 1 FROM eudr_declaration_identifier r WHERE r.filing_id = OLD.filing_id) THEN\n            RAISE EXCEPTION 'filing % is accepted when its declaration identifier is recorded (EUDR → simplified declaration)', OLD.filing_id;\n        END IF;\n        -- nor withdrawn once used as a reference in a grouping (IR Art. 4a(7))\n        IF NEW.status = 'withdrawn' AND OLD.framework = 'eudr_simplified'\n           AND EXISTS (SELECT 1 FROM eudr_dds_event e WHERE e.filing_id = OLD.filing_id AND e.kind = 'grouped') THEN\n            RAISE EXCEPTION 'filing % was used as a reference in a grouping — it can no longer be withdrawn (IR 2024/3084 Art. 4a(7))',\n                            OLD.filing_id;\n        END IF;\n        -- an EUDR statement may be rejected by the authority only before its reference number is available (Art. 8(1))\n        IF NEW.status = 'rejected' AND OLD.framework = 'eudr_dds' AND OLD.status = 'submitted'\n           AND EXISTS (SELECT 1 FROM eudr_dds_event e WHERE e.filing_id = OLD.filing_id AND e.kind = 'reference_received') THEN\n            RAISE EXCEPTION 'filing % has its reference number — it can no longer be rejected (IR 2024/3084 Art. 8(1))',\n                            OLD.filing_id;\n        END IF;\n        -- status may only move forward: submitted→accepted, or either→superseded; an EUDR statement also\n        -- submitted→rejected (Art. 8) and accepted→withdrawn (Art. 5(1)); a simplified declaration rejected (Art. 8)\n        -- or withdrawn (Art. 4a(6)) once submitted\n        IF NEW.status <> OLD.status\n           AND NOT (OLD.status = 'submitted' AND NEW.status = 'accepted')\n           AND NOT (OLD.framework = 'eudr_dds' AND OLD.status = 'submitted' AND NEW.status = 'rejected')\n           AND NOT (OLD.framework = 'eudr_dds' AND OLD.status = 'accepted' AND NEW.status = 'withdrawn')\n           AND NOT (OLD.framework = 'eudr_simplified' AND NEW.status IN ('rejected', 'withdrawn'))\n           AND NEW.status <> 'superseded' THEN\n            RAISE EXCEPTION 'filing % is % and can only be accepted or superseded, not changed to %',\n                            OLD.filing_id, OLD.status, NEW.status;\n        END IF;\n    END IF;\n    NEW.updated_at := now();\n    RETURN NEW;\nEND;\n$$ LANGUAGE plpgsql;\n"

_WORM = """
    CREATE FUNCTION prevent_{t}_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION '{t} is append-only: record it again'; END $$;
    CREATE TRIGGER trg_{t}_worm BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION prevent_{t}_mutation();
"""


def upgrade() -> None:
    op.execute("""
        ALTER TABLE eudr_undertaking_statement ADD COLUMN primary_own_produce BOOLEAN, ADD COLUMN other_system TEXT;
        ALTER TABLE sc_sourcing_plots ADD COLUMN postal_address TEXT;
        CREATE TABLE eudr_declaration_line (
            line_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq                 BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            org_id              UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            reporting_entity_id UUID REFERENCES reporting_entities(entity_id) ON DELETE RESTRICT,
            hs_code             TEXT NOT NULL CONSTRAINT ck_eudr_line_hs CHECK (hs_code ~ '^[0-9]{4,10}$'),
            description         TEXT NOT NULL,
            trade_name          TEXT,
            customs_flow        BOOLEAN NOT NULL,
            est_net_mass_kg     NUMERIC CONSTRAINT ck_eudr_line_mass CHECK (est_net_mass_kg IS NULL OR est_net_mass_kg > 0),
            mass_deviation_pct  NUMERIC CONSTRAINT ck_eudr_line_dev CHECK (mass_deviation_pct IS NULL OR mass_deviation_pct >= 0),
            supplementary_unit  TEXT,
            supplementary_qty   NUMERIC,
            volume_m3           NUMERIC CONSTRAINT ck_eudr_line_vol CHECK (volume_m3 IS NULL OR volume_m3 > 0),
            items_count         INTEGER CONSTRAINT ck_eudr_line_items CHECK (items_count IS NULL OR items_count > 0),
            scope_in            BOOLEAN,
            scope_basis         TEXT,
            CONSTRAINT ck_eudr_line_scope CHECK ((scope_in IS NULL) = (scope_basis IS NULL)),
            recorded_by         UUID,
            recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            removed_at          TIMESTAMPTZ,
            CONSTRAINT ck_eudr_line_quantity CHECK (est_net_mass_kg IS NOT NULL OR volume_m3 IS NOT NULL OR items_count IS NOT NULL)
        );
        CREATE INDEX ix_eudr_declaration_line ON eudr_declaration_line (org_id, reporting_entity_id, seq);
        CREATE TABLE eudr_declaration_identifier (
            identifier_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq                 BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            filing_id           UUID NOT NULL CONSTRAINT ux_eudr_declaration_identifier UNIQUE
                                REFERENCES regulatory_filing(filing_id) ON DELETE RESTRICT,
            declaration_identifier TEXT NOT NULL,
            verification_number TEXT,
            source              TEXT NOT NULL CONSTRAINT ck_eudr_decl_source
                                CHECK (source IN ('information_system', 'manual_entry', 'contingency', 'member_state')),
            received_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            recorded_by         UUID
        );
    """ + _WORM.format(t="eudr_declaration_identifier") + """
        ALTER TABLE regulatory_filing DROP CONSTRAINT ck_filing_period_label;
        ALTER TABLE regulatory_filing ADD CONSTRAINT ck_filing_period_label CHECK (
            CASE WHEN framework IN ('eudr_dds', 'eudr_simplified') THEN period_label LIKE '% · ' || period_end::text
                 ELSE period_label = ('FY'::text || (EXTRACT(year FROM period_end))::integer) END);
    """)
    op.execute(GUARD)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM regulatory_filing WHERE framework = 'eudr_simplified')
               OR EXISTS (SELECT 1 FROM eudr_declaration_line) THEN
                RAISE EXCEPTION 'cannot downgrade eudr_declaration_20261002: simplified declarations are recorded';
            END IF;
        END $$;
    """)
    op.execute(PRIOR_GUARD)
    op.execute("""
        ALTER TABLE regulatory_filing DROP CONSTRAINT ck_filing_period_label;
        ALTER TABLE regulatory_filing ADD CONSTRAINT ck_filing_period_label CHECK (
            CASE WHEN framework = 'eudr_dds' THEN period_label LIKE '% · ' || period_end::text
                 ELSE period_label = ('FY'::text || (EXTRACT(year FROM period_end))::integer) END);
        DROP TABLE eudr_declaration_identifier; DROP FUNCTION prevent_eudr_declaration_identifier_mutation();
        DROP TABLE eudr_declaration_line;
        ALTER TABLE sc_sourcing_plots DROP COLUMN postal_address;
        ALTER TABLE eudr_undertaking_statement DROP COLUMN primary_own_produce, DROP COLUMN other_system;
    """)

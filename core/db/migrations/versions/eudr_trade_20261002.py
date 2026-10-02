"""EUDR Article 5 — what downstream operators and traders keep (E122), and new information / substantiated concerns for
every role (Art. 4(5), 5(5)-(6)). Regulation (EU) 2023/1115 as in force.

  eudr_movement               + supplier_role: what the supplier of the movement is — operator, downstream operator or
                                trader ('only in the event that their supplier is an operator, the reference numbers of the
                                due diligence statements or the declaration identifiers', Art. 5(3)(a)) — NULL: not stated
  eudr_undertaking_statement  + is_registration: the registration of a non-SME downstream operator or trader in the
                                information system (Art. 5(2)) — NULL: not stated
  eudr_trade_record           the Art. 5(3) information of one movement, frozen and hashed when the undertaking keeps it,
                              with the date it is kept until (Art. 5(4): 'for at least five years from the date of the
                              placing or making available on the market or export') — append-only; a correction is a
                              later record of the same movement
  eudr_concern                relevant new information or a substantiated concern about a movement's product (Art. 2(31),
                              4(5), 5(5)-(6)), append-only
  eudr_concern_step           what was done about it: the competent authorities informed, the downstream operators and
                              traders informed, or (non-SME, before placing — Art. 5(6)) the verification and its
                              conclusion — append-only

Revision ID: eudr_trade_20261002
Revises: history_sequences_20261002
"""
from typing import Sequence, Union

from alembic import op

revision: str = "eudr_trade_20261002"
down_revision: Union[str, None] = "history_sequences_20261002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORG = "0bbe0bbe-0000-4000-8000-00000000fefa"
_M = "0bbe0bbe-0000-4000-8000-00000000feaa"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_ORG}', 'refusal probe', 'manufacturer', 'NL');
                 INSERT INTO eudr_movement (movement_id, org_id, kind, actor_role, planned_on, hs_code, description,
                                            customs_flow, net_mass_kg)
                 VALUES ('{_M}', '{_ORG}', 'making_available', 'trader', '2027-01-15', '180100', 'probe', false, 1);
                 INSERT INTO eudr_concern (org_id, movement_id, kind, received_on, detail)
                 VALUES ('{_ORG}', '{_M}', 'substantiated_concern', '2027-01-10', 'probe');""",
    "cleanup": f"""ALTER TABLE eudr_concern DISABLE TRIGGER trg_eudr_concern_worm;
                   DELETE FROM eudr_concern WHERE org_id = '{_ORG}';
                   ALTER TABLE eudr_concern ENABLE TRIGGER trg_eudr_concern_worm;
                   DELETE FROM eudr_movement WHERE movement_id = '{_M}';
                   DELETE FROM organizations WHERE org_id = '{_ORG}';""",
}

_WORM = """
    CREATE FUNCTION prevent_{t}_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION '{t} is append-only: record it again'; END $$;
    CREATE TRIGGER trg_{t}_worm BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION prevent_{t}_mutation();
"""


def upgrade() -> None:
    op.execute("""
        ALTER TABLE eudr_movement ADD COLUMN supplier_role TEXT
            CONSTRAINT ck_eudr_supplier_role CHECK (supplier_role IN ('operator', 'downstream_operator', 'trader'));
        ALTER TABLE eudr_undertaking_statement ADD COLUMN is_registration TEXT;
        CREATE TABLE eudr_trade_record (
            record_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq             BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            org_id          UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            movement_id     UUID NOT NULL REFERENCES eudr_movement(movement_id) ON DELETE RESTRICT,
            payload         JSONB NOT NULL,
            payload_sha256  CHAR(64) NOT NULL,
            keep_until      DATE NOT NULL,
            recorded_by     UUID,
            recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_eudr_trade_record ON eudr_trade_record (movement_id, seq);
    """ + _WORM.format(t="eudr_trade_record") + """
        CREATE TABLE eudr_concern (
            concern_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq             BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            org_id          UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            movement_id     UUID NOT NULL REFERENCES eudr_movement(movement_id) ON DELETE RESTRICT,
            kind            TEXT NOT NULL CONSTRAINT ck_eudr_concern_kind
                            CHECK (kind IN ('new_information', 'substantiated_concern')),
            received_on     DATE NOT NULL,
            detail          TEXT NOT NULL,
            recorded_by     UUID,
            recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_eudr_concern ON eudr_concern (movement_id, seq);
    """ + _WORM.format(t="eudr_concern") + """
        CREATE TABLE eudr_concern_step (
            step_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq             BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            concern_id      UUID NOT NULL REFERENCES eudr_concern(concern_id) ON DELETE RESTRICT,
            kind            TEXT NOT NULL CONSTRAINT ck_eudr_step_kind
                            CHECK (kind IN ('authorities_informed', 'downstream_informed', 'verified')),
            on_date         DATE NOT NULL,
            conclusion      TEXT CONSTRAINT ck_eudr_step_conclusion CHECK (conclusion IN ('negligible', 'not_negligible')),
            detail          TEXT,
            recorded_by     UUID,
            recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_eudr_step_verified CHECK ((kind = 'verified') = (conclusion IS NOT NULL))
        );
        CREATE INDEX ix_eudr_concern_step ON eudr_concern_step (concern_id, seq);
    """ + _WORM.format(t="eudr_concern_step"))


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM eudr_trade_record) OR EXISTS (SELECT 1 FROM eudr_concern) THEN
                RAISE EXCEPTION 'cannot downgrade eudr_trade_20261002: Article 5 records or concerns are kept';
            END IF;
        END $$;
        DROP TABLE eudr_concern_step; DROP FUNCTION prevent_eudr_concern_step_mutation();
        DROP TABLE eudr_concern; DROP FUNCTION prevent_eudr_concern_mutation();
        DROP TABLE eudr_trade_record; DROP FUNCTION prevent_eudr_trade_record_mutation();
        ALTER TABLE eudr_undertaking_statement DROP COLUMN is_registration;
        ALTER TABLE eudr_movement DROP COLUMN supplier_role;
    """)

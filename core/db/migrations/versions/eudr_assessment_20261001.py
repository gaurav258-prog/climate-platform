"""EUDR layer 3 (E94): the evidence and the operator's assessment the statement rests on (Regulation (EU) 2023/1115).

  eudr_legality_evidence  documents showing production 'in accordance with the relevant legislation of the country of
                          production' (Art. 3(b), 9(1)(h)) — each for one plot, supplier or movement and one aspect of
                          Art. 2(40) (a)-(h), or a FLEGT licence (Art. 10(3)); append-only (a document withdrawn is a new
                          row that names the one it withdraws).
  eudr_undertaking_statement.address   the operator's address (Annex II point 1: 'Operator's name, address …'), stated
                          with its status — the organisation record holds none.
  eudr_risk_assessment    the operator's assessment of one movement: either the full one (Art. 10(2) criteria (a)-(n)
                          answered, a conclusion — Art. 10(1): 'no or only a negligible risk' — and the Art. 11
                          mitigation adopted) or the simplified one (Art. 13(1): all produced in low-risk countries, with
                          the assessment of circumvention and mixing it requires). Stated by one person, approved by
                          another; append-only; the latest is the live one.

Revision ID: eudr_assessment_20261001
Revises: obligation_fund_key_20261001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "eudr_assessment_20261001"
down_revision: Union[str, None] = "obligation_fund_key_20261001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORG = "0bbe0bbe-0000-4000-8000-00000000fef2"
_S = "0bbe0bbe-0000-4000-8000-00000000fea3"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_ORG}', 'refusal probe', 'manufacturer', 'NL');
                 INSERT INTO sc_suppliers (supplier_id, org_id, name) VALUES ('{_S}', '{_ORG}', 'probe');
                 INSERT INTO eudr_legality_evidence (org_id, supplier_id, aspect, document_kind)
                 VALUES ('{_ORG}', '{_S}', 'land_use_rights', 'probe');""",
    "cleanup": f"""ALTER TABLE eudr_legality_evidence DISABLE TRIGGER trg_eudr_legality_evidence_worm;
                   DELETE FROM eudr_legality_evidence WHERE org_id = '{_ORG}';
                   ALTER TABLE eudr_legality_evidence ENABLE TRIGGER trg_eudr_legality_evidence_worm;
                   DELETE FROM sc_suppliers WHERE org_id = '{_ORG}'; DELETE FROM organizations WHERE org_id = '{_ORG}';""",
}

_WORM = """
    CREATE FUNCTION prevent_{t}_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION '{t} is append-only: record it again'; END $$;
    CREATE TRIGGER trg_{t}_worm BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION prevent_{t}_mutation();
"""


def upgrade() -> None:
    op.execute("""
        ALTER TABLE eudr_undertaking_statement ADD COLUMN address TEXT;
        CREATE TABLE eudr_legality_evidence (
            evidence_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq              BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            org_id           UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            plot_id          UUID REFERENCES sc_sourcing_plots(plot_id) ON DELETE RESTRICT,
            supplier_id      UUID REFERENCES sc_suppliers(supplier_id) ON DELETE RESTRICT,
            movement_id      UUID REFERENCES eudr_movement(movement_id) ON DELETE RESTRICT,
            aspect           TEXT NOT NULL CONSTRAINT ck_eudr_aspect CHECK (aspect IN (
                                 'land_use_rights', 'environmental_protection', 'forest_rules', 'third_party_rights',
                                 'labour_rights', 'human_rights', 'fpic', 'tax_anticorruption_trade_customs', 'flegt_licence')),
            document_kind    TEXT NOT NULL,
            document_ref     TEXT,
            file_sha256      TEXT,
            issued_by        TEXT,
            valid_from       DATE,
            valid_until      DATE,
            note             TEXT,
            withdraws        UUID REFERENCES eudr_legality_evidence(evidence_id),
            recorded_by      UUID,
            recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_eudr_evidence_subject CHECK (num_nonnulls(plot_id, supplier_id, movement_id) = 1),
            CONSTRAINT ck_eudr_evidence_dates CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_from <= valid_until)
        );
        CREATE INDEX ix_eudr_evidence ON eudr_legality_evidence (org_id, seq DESC);
    """ + _WORM.format(t="eudr_legality_evidence") + """
        CREATE TABLE eudr_risk_assessment (
            assessment_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq                   BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            org_id                UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            movement_id           UUID NOT NULL REFERENCES eudr_movement(movement_id) ON DELETE RESTRICT,
            path                  TEXT NOT NULL CONSTRAINT ck_eudr_path CHECK (path IN ('full', 'simplified')),
            criteria              JSONB NOT NULL DEFAULT '{}'::jsonb,
            conclusion            TEXT NOT NULL CONSTRAINT ck_eudr_conclusion CHECK (conclusion IN ('negligible', 'not_negligible')),
            mitigation            JSONB NOT NULL DEFAULT '{}'::jsonb,
            circumvention_mixing  TEXT,
            requested_by          UUID NOT NULL,
            approved_by           UUID NOT NULL,
            approval_request_id   UUID,
            recorded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_eudr_risk_four_eyes CHECK (requested_by <> approved_by),
            -- Art. 13(1): the simplified path rests on an assessment of circumvention and mixing
            CONSTRAINT ck_eudr_simplified_mixing CHECK (path <> 'simplified' OR circumvention_mixing IS NOT NULL)
        );
        CREATE INDEX ix_eudr_risk ON eudr_risk_assessment (movement_id, seq DESC);
    """ + _WORM.format(t="eudr_risk_assessment"))


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM eudr_legality_evidence) OR EXISTS (SELECT 1 FROM eudr_risk_assessment)
               OR EXISTS (SELECT 1 FROM eudr_undertaking_statement WHERE address IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot downgrade eudr_assessment_20261001: legality evidence or risk assessments are held';
            END IF;
        END $$;
    """)
    op.execute("""
        DROP TABLE eudr_risk_assessment; DROP FUNCTION prevent_eudr_risk_assessment_mutation();
        DROP TABLE eudr_legality_evidence; DROP FUNCTION prevent_eudr_legality_evidence_mutation();
        ALTER TABLE eudr_undertaking_statement DROP COLUMN address;
    """)

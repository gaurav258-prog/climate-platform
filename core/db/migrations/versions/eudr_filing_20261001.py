"""EUDR layer 5 (E108): what happens to a filed due diligence statement, as the information system's rules need it
(Implementing Regulation (EU) 2024/3084 as amended by 2026/1565, Art. 5):

  'Information System users may amend or withdraw Due Diligence Statements within 72 hours after the reference number
  … was made available' (Art. 5(1)) — not after it was used for grouping (5(2)), nor after the user 'was notified about
  the intention to carry out a check … for the period of the check' (5(3)(a)), the product 'was placed on the Union
  market or exported' (5(3)(b)), or the reference number 'was provided or made available to customs authorities'
  (5(3)(c)); competent authorities may extend the window, 'not … longer than 8 calendar days' (5(4)).

  eudr_dds_event   each such event on a statement filing, append-only: reference_received, grouped, check_notified,
                   check_ended, placed_or_exported, given_to_customs, window_extended (with its end), rejected (Art. 8)
  sc_eudr_dds      the statements assembled before the rebuild: kept as they are, read-only from now on
  shipment         an EUDR statement filing always names its shipment (one statement per movement, Art. 4(2))
  guard            an EUDR statement is accepted only with its reference number recorded; the filing guard lets it
                   be withdrawn once accepted (Art. 5(1); the window is the
                   service's) and rejected while submitted, never after its reference number is available (Art. 8(1),
                   as amended by 2026/1565: 'shall no longer be possible once the reference number … has become available')

Revision ID: eudr_filing_20261001
Revises: eudr_scope_statement_20261001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "eudr_filing_20261001"
down_revision: Union[str, None] = "eudr_scope_statement_20261001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORG = "0bbe0bbe-0000-4000-8000-00000000fef4"
_F = "0bbe0bbe-0000-4000-8000-00000000fea4"
_M = "0bbe0bbe-0000-4000-8000-00000000fea5"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_ORG}', 'refusal probe', 'manufacturer', 'NL');
                 INSERT INTO eudr_movement (movement_id, org_id, kind, actor_role, planned_on, hs_code, description,
                                            customs_flow, net_mass_kg)
                 VALUES ('{_M}', '{_ORG}', 'placing', 'operator', '2027-01-15', '180100', 'probe', true, 1);
                 INSERT INTO regulatory_filing (filing_id, org_id, framework, period_end, period_label, status, eudr_movement_id)
                 VALUES ('{_F}', '{_ORG}', 'eudr_dds', '2027-12-31', 'FY2027', 'submitted', '{_M}');
                 INSERT INTO eudr_dds_event (filing_id, kind) VALUES ('{_F}', 'placed_or_exported');""",
    "cleanup": f"""ALTER TABLE eudr_dds_event DISABLE TRIGGER trg_eudr_dds_event_worm;
                   DELETE FROM eudr_dds_event WHERE filing_id = '{_F}';
                   ALTER TABLE eudr_dds_event ENABLE TRIGGER trg_eudr_dds_event_worm;
                   ALTER TABLE regulatory_filing DISABLE TRIGGER USER;
                   DELETE FROM regulatory_filing WHERE filing_id = '{_F}';
                   ALTER TABLE regulatory_filing ENABLE TRIGGER USER;
                   DELETE FROM eudr_movement WHERE movement_id = '{_M}';
                   DELETE FROM organizations WHERE org_id = '{_ORG}';""",
}


# self-contained (E25): the guard as filing_withdrawn_20260929 defined it, restored on downgrade
PRIOR_GUARD = """
CREATE OR REPLACE FUNCTION guard_filing_transition() RETURNS trigger AS $$
BEGIN
    -- withdrawn is terminal: the discarded draft keeps its status and frozen content for good
    IF OLD.status = 'withdrawn' THEN
        IF NEW.status <> 'withdrawn'
           OR NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id
           OR NEW.period_end <> OLD.period_end
           OR NEW.framework <> OLD.framework
           OR NEW.entity_id IS DISTINCT FROM OLD.entity_id THEN
            RAISE EXCEPTION 'filing % is withdrawn — it cannot change', OLD.filing_id;
        END IF;
    END IF;
    -- only a filing nothing has signed off may be withdrawn
    IF NEW.status = 'withdrawn' AND OLD.status NOT IN ('draft','returned','withdrawn') THEN
        RAISE EXCEPTION 'filing % is % — only a draft or returned filing can be withdrawn', OLD.filing_id, OLD.status;
    END IF;
    IF OLD.status IN ('submitted','accepted') THEN
        -- content is frozen once filed
        IF NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id
           OR NEW.period_end <> OLD.period_end
           OR NEW.framework <> OLD.framework THEN
            RAISE EXCEPTION 'filing % is % — its frozen content cannot change (restate via supersession)',
                            OLD.filing_id, OLD.status;
        END IF;
        -- status may only move forward: submitted→accepted, or either→superseded
        IF NEW.status <> OLD.status
           AND NOT (OLD.status = 'submitted' AND NEW.status = 'accepted')
           AND NEW.status <> 'superseded' THEN
            RAISE EXCEPTION 'filing % is % and can only be accepted or superseded, not changed to %',
                            OLD.filing_id, OLD.status, NEW.status;
        END IF;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

GUARD = """
CREATE OR REPLACE FUNCTION guard_filing_transition() RETURNS trigger AS $$
BEGIN
    -- withdrawn is terminal: the discarded draft keeps its status and frozen content for good
    IF OLD.status = 'withdrawn' THEN
        IF NEW.status <> 'withdrawn'
           OR NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id
           OR NEW.period_end <> OLD.period_end
           OR NEW.framework <> OLD.framework
           OR NEW.entity_id IS DISTINCT FROM OLD.entity_id THEN
            RAISE EXCEPTION 'filing % is withdrawn — it cannot change', OLD.filing_id;
        END IF;
    END IF;
    -- only a filing nothing has signed off may be withdrawn — except an EUDR statement the information system has
    -- given its reference number, within the window the service checks (IR 2024/3084 Art. 5(1))
    IF NEW.status = 'withdrawn' AND OLD.status NOT IN ('draft','returned','withdrawn')
       AND NOT (OLD.framework = 'eudr_dds' AND OLD.status = 'accepted') THEN
        RAISE EXCEPTION 'filing % is % — only a draft or returned filing can be withdrawn', OLD.filing_id, OLD.status;
    END IF;
    IF OLD.status IN ('submitted','accepted') THEN
        -- content is frozen once filed
        IF NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id
           OR NEW.period_end <> OLD.period_end
           OR NEW.framework <> OLD.framework THEN
            RAISE EXCEPTION 'filing % is % — its frozen content cannot change (restate via supersession)',
                            OLD.filing_id, OLD.status;
        END IF;
        -- an EUDR statement is accepted by the information system making its reference number available: never
        -- without one recorded (Art. 4(2), 33; IR 2024/3084)
        IF NEW.status = 'accepted' AND OLD.status = 'submitted' AND OLD.framework = 'eudr_dds'
           AND NOT EXISTS (SELECT 1 FROM eudr_dds_reference r WHERE r.filing_id = OLD.filing_id) THEN
            RAISE EXCEPTION 'filing % is accepted when its reference number is recorded (EUDR → the shipment)', OLD.filing_id;
        END IF;
        -- an EUDR statement may be rejected by the authority only before its reference number is available (Art. 8(1))
        IF NEW.status = 'rejected' AND OLD.framework = 'eudr_dds' AND OLD.status = 'submitted'
           AND EXISTS (SELECT 1 FROM eudr_dds_event e WHERE e.filing_id = OLD.filing_id AND e.kind = 'reference_received') THEN
            RAISE EXCEPTION 'filing % has its reference number — it can no longer be rejected (IR 2024/3084 Art. 8(1))',
                            OLD.filing_id;
        END IF;
        -- status may only move forward: submitted→accepted, or either→superseded; an EUDR statement also
        -- submitted→rejected (Art. 8) and accepted→withdrawn (Art. 5(1))
        IF NEW.status <> OLD.status
           AND NOT (OLD.status = 'submitted' AND NEW.status = 'accepted')
           AND NOT (OLD.framework = 'eudr_dds' AND OLD.status = 'submitted' AND NEW.status = 'rejected')
           AND NOT (OLD.framework = 'eudr_dds' AND OLD.status = 'accepted' AND NEW.status = 'withdrawn')
           AND NEW.status <> 'superseded' THEN
            RAISE EXCEPTION 'filing % is % and can only be accepted or superseded, not changed to %',
                            OLD.filing_id, OLD.status, NEW.status;
        END IF;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

def upgrade() -> None:
    op.execute("""
        CREATE TABLE eudr_dds_event (
            event_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq           BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            filing_id     UUID NOT NULL REFERENCES regulatory_filing(filing_id) ON DELETE RESTRICT,
            kind          TEXT NOT NULL CONSTRAINT ck_eudr_event_kind CHECK (kind IN ('reference_received', 'grouped',
                              'check_notified', 'check_ended', 'placed_or_exported', 'given_to_customs', 'window_extended',
                              'rejected')),
            at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            until         TIMESTAMPTZ,
            detail        TEXT,
            recorded_by   UUID,
            CONSTRAINT ck_eudr_event_until CHECK ((kind = 'window_extended') = (until IS NOT NULL))
        );
        CREATE INDEX ix_eudr_dds_event ON eudr_dds_event (filing_id, seq);
        CREATE FUNCTION prevent_eudr_dds_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'eudr_dds_event is append-only: record it again'; END $$;
        CREATE TRIGGER trg_eudr_dds_event_worm BEFORE UPDATE OR DELETE ON eudr_dds_event
            FOR EACH ROW EXECUTE FUNCTION prevent_eudr_dds_event_mutation();

        CREATE FUNCTION prevent_legacy_dds_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'sc_eudr_dds holds statements assembled before the EUDR rebuild: read-only (a statement is now a filing)'; END $$;
        CREATE TRIGGER trg_legacy_dds_readonly BEFORE INSERT OR UPDATE OR DELETE ON sc_eudr_dds
            FOR EACH ROW EXECUTE FUNCTION prevent_legacy_dds_mutation();
    """)
    op.execute(GUARD)
    op.execute("""ALTER TABLE regulatory_filing ADD CONSTRAINT ck_reg_filing_eudr_movement
                  CHECK (framework <> 'eudr_dds' OR eudr_movement_id IS NOT NULL)""")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM eudr_dds_event) THEN
                RAISE EXCEPTION 'cannot downgrade eudr_filing_20261001: events of filed statements are recorded';
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE regulatory_filing DROP CONSTRAINT ck_reg_filing_eudr_movement")
    op.execute(PRIOR_GUARD)
    op.execute("""
        DROP TRIGGER trg_legacy_dds_readonly ON sc_eudr_dds; DROP FUNCTION prevent_legacy_dds_mutation();
        DROP TABLE eudr_dds_event; DROP FUNCTION prevent_eudr_dds_event_mutation();
    """)

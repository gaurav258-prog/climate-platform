"""One counterparty, one figure: the banking book's counterparties (Pillar 3 Template 1 columns i-k; E119).

Annex XL, Template 1, column i (Implementing Regulation (EU) 2022/2453; the same wording under 2024/3172): 'Institutions
shall estimate the scope 3 emissions per sector in a proportionate manner, including by taking into account their
exposures (loans and advances, debt securities and equity holdings) towards the counterparty compared to the total
liabilities (accounting liabilities and shareholders' equity) of the counterparty.' The total liabilities are a fact of
the COUNTERPARTY, so one counterparty carries one figure. p3_t1_liabilities_20261001 stated it per exposure, so two loans
to one company could carry two figures.

The counterparty's identity is the one the loan tape already states (portfolio_entities.borrower_entity_id, 'Counterparty
ID (LEI)': its LEI or the bank's own stable id). bank_counterparties holds, per organisation and that id, what the bank
states about the counterparty through the governed intake (template bank_counterparties): its total liabilities with the
balance-sheet date and where the amount came from (money_source), and its entry in the shared issuer reference (the
issuer whose LEI the id is — this replaces ext_banking.counterparty_issuer_id, a second per-exposure link that nothing
wrote). An exposure reaches its counterparty by (org_id, borrower_entity_id); there is no second link to drift.

Moving the per-exposure figures, honestly:
  * the exposures of one counterparty that state a figure all state the same one (amount in EUR, date, and the amount
    and currency as sent) → it becomes the counterparty's figure, with its money_source entry
  * they state different figures → none is picked: the counterparty keeps no figure and records the statements that
    disagree (liabilities_conflict); Template 1 validation blocks until the bank states the one figure (stating it
    through the intake clears the conflict)
  * an exposure stating a figure or an issuer link without a counterparty id, or exposures of one counterparty linked to
    different issuers → the upgrade refuses, saying what to resolve (nothing is dropped or guessed)
Downgrade gives every exposure of a counterparty its counterparty's figure (and, for a conflict, each exposure its own
recorded statement) and issuer link; it refuses when a counterparty states something no exposure links to.

Revision ID: p3_t1_counterparty_20261002
Revises: eudr_trade_20261002
"""
from typing import Sequence, Union

from alembic import op

revision: str = "p3_t1_counterparty_20261002"
down_revision: Union[str, None] = "eudr_trade_20261002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROBE_ORG = "0bbe0bbe-0000-4000-8000-00000000fe19"
# A counterparty that states its total liabilities while no exposure links to it: the per-exposure shape has nowhere to
# keep the figure, so the downgrade must refuse (scripts/check_migration_roundtrip.py plants this and requires it).
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_PROBE_ORG}', 'refusal probe', 'bank', 'DE');
                 INSERT INTO bank_counterparties (org_id, counterparty_ref, total_liabilities_eur, total_liabilities_date)
                 VALUES ('{_PROBE_ORG}', 'PROBE-CP', 1000000, '2025-12-31');""",
    "cleanup": f"""DELETE FROM bank_counterparties WHERE org_id = '{_PROBE_ORG}';
                   DELETE FROM organizations WHERE org_id = '{_PROBE_ORG}';""",
}

_ENTRY = "x.money_source->'fields'->'counterparty_total_liabilities_eur'"


# Each counterparty once, with the one figure its exposures agree on — or the statements that disagree (a conflict, no
# figure picked). Module-level so tests/integration/test_pillar3_t1.py runs exactly this on its own rows.
MOVE_SQL = f"""
        WITH stated AS (
            SELECT e.org_id, btrim(e.borrower_entity_id) AS ref, x.entity_id, x.counterparty_issuer_id AS issuer_id,
                   x.counterparty_total_liabilities_eur AS eur, x.counterparty_total_liabilities_date AS d, {_ENTRY} AS entry
            FROM ext_banking x JOIN portfolio_entities e ON e.entity_id = x.entity_id
            WHERE NULLIF(btrim(e.borrower_entity_id), '') IS NOT NULL
              AND (x.counterparty_total_liabilities_eur IS NOT NULL OR x.counterparty_issuer_id IS NOT NULL)
        ), cp AS (
            SELECT org_id, ref, (array_agg(issuer_id) FILTER (WHERE issuer_id IS NOT NULL))[1] AS issuer_id,
                   count(DISTINCT jsonb_build_array(eur, d, entry->'amount', entry->'currency')) FILTER (WHERE eur IS NOT NULL) AS n,
                   jsonb_agg(jsonb_build_object('entity_id', entity_id, 'eur', eur, 'date', d, 'source', entry)
                             ORDER BY entity_id) FILTER (WHERE eur IS NOT NULL) AS statements,
                   (array_agg(eur) FILTER (WHERE eur IS NOT NULL))[1] AS eur,
                   (array_agg(d) FILTER (WHERE eur IS NOT NULL))[1] AS d,
                   (array_agg(entry) FILTER (WHERE eur IS NOT NULL AND entry IS NOT NULL))[1] AS entry
            FROM stated GROUP BY org_id, ref
        )
        INSERT INTO bank_counterparties (org_id, counterparty_ref, issuer_id, total_liabilities_eur, total_liabilities_date,
                                         money_source, liabilities_conflict)
        SELECT org_id, ref, issuer_id,
               CASE WHEN n = 1 THEN eur END, CASE WHEN n = 1 THEN d END,
               CASE WHEN n = 1 AND entry IS NOT NULL THEN jsonb_build_object('fields', jsonb_build_object('total_liabilities_eur', entry)) END,
               CASE WHEN n > 1 THEN statements END
        FROM cp;
    """


def upgrade() -> None:
    op.execute("""
        DO $$
        DECLARE n integer;
        BEGIN
            SELECT count(*) INTO n FROM ext_banking x JOIN portfolio_entities e ON e.entity_id = x.entity_id
             WHERE NULLIF(btrim(e.borrower_entity_id), '') IS NULL
               AND (x.counterparty_total_liabilities_eur IS NOT NULL OR x.counterparty_issuer_id IS NOT NULL);
            IF n > 0 THEN
                RAISE EXCEPTION 'cannot upgrade p3_t1_counterparty_20261002: % exposures state the counterparty''s total '
                                'liabilities or issuer without a counterparty id (borrower_entity_id) — state it on the '
                                'loan tape first', n;
            END IF;
            SELECT count(*) INTO n FROM (
                SELECT e.org_id, e.borrower_entity_id FROM ext_banking x JOIN portfolio_entities e ON e.entity_id = x.entity_id
                 WHERE x.counterparty_issuer_id IS NOT NULL GROUP BY 1, 2
                HAVING count(DISTINCT x.counterparty_issuer_id) > 1) d;
            IF n > 0 THEN
                RAISE EXCEPTION 'cannot upgrade p3_t1_counterparty_20261002: % counterparties are linked to different '
                                'issuers by their exposures — resolve the issuer links first', n;
            END IF;
        END $$;
    """)
    op.execute("""
        CREATE TABLE bank_counterparties (
            counterparty_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id                  UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            counterparty_ref        VARCHAR(20) NOT NULL CHECK (btrim(counterparty_ref) <> ''),
            counterparty_name       TEXT,
            issuer_id               UUID REFERENCES issuers(issuer_id),
            total_liabilities_eur   NUMERIC(20,2),
            total_liabilities_date  DATE,
            money_source            JSONB,
            liabilities_conflict    JSONB,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ux_bank_counterparties_ref UNIQUE (org_id, counterparty_ref),
            CONSTRAINT ck_bank_cp_total_liabilities CHECK (
                total_liabilities_eur IS NULL OR (total_liabilities_eur > 0 AND total_liabilities_date IS NOT NULL)),
            CONSTRAINT ck_bank_cp_conflict CHECK (
                liabilities_conflict IS NULL OR (total_liabilities_eur IS NULL
                                                 AND jsonb_typeof(liabilities_conflict) = 'array'))
        );
        CREATE INDEX ix_bank_counterparties_issuer ON bank_counterparties (issuer_id);
        CREATE INDEX ix_portfolio_entities_borrower ON portfolio_entities (org_id, borrower_entity_id);
    """)
    op.execute(MOVE_SQL)
    op.execute("""
        UPDATE ext_banking SET money_source = money_source #- '{fields,counterparty_total_liabilities_eur}'
         WHERE money_source->'fields' ? 'counterparty_total_liabilities_eur';
        ALTER TABLE ext_banking DROP CONSTRAINT IF EXISTS ck_ext_banking_cp_total_liabilities;
        ALTER TABLE ext_banking DROP COLUMN counterparty_total_liabilities_date;
        ALTER TABLE ext_banking DROP COLUMN counterparty_total_liabilities_eur;
        DROP INDEX IF EXISTS ix_ext_banking_counterparty_issuer;
        ALTER TABLE ext_banking DROP COLUMN counterparty_issuer_id;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        DECLARE n integer;
        BEGIN
            SELECT count(*) INTO n FROM bank_counterparties c
             WHERE (c.total_liabilities_eur IS NOT NULL OR c.issuer_id IS NOT NULL OR c.liabilities_conflict IS NOT NULL)
               AND NOT EXISTS (SELECT 1 FROM portfolio_entities e JOIN ext_banking x ON x.entity_id = e.entity_id
                                WHERE e.org_id = c.org_id AND btrim(e.borrower_entity_id) = c.counterparty_ref);
            IF n > 0 THEN
                RAISE EXCEPTION 'cannot downgrade p3_t1_counterparty_20261002: % counterparties state total liabilities '
                                'or an issuer that no exposure links to — the per-exposure shape cannot keep them', n;
            END IF;
        END $$;
    """)
    op.execute("""
        ALTER TABLE ext_banking ADD COLUMN counterparty_issuer_id UUID REFERENCES issuers(issuer_id);
        CREATE INDEX ix_ext_banking_counterparty_issuer ON ext_banking (counterparty_issuer_id);
        ALTER TABLE ext_banking ADD COLUMN counterparty_total_liabilities_eur NUMERIC(20,2);
        ALTER TABLE ext_banking ADD COLUMN counterparty_total_liabilities_date DATE;
        ALTER TABLE ext_banking ADD CONSTRAINT ck_ext_banking_cp_total_liabilities CHECK (
            counterparty_total_liabilities_eur IS NULL OR (counterparty_total_liabilities_eur > 0
            AND counterparty_total_liabilities_date IS NOT NULL));
        UPDATE ext_banking x
           SET counterparty_issuer_id = c.issuer_id,
               counterparty_total_liabilities_eur = c.total_liabilities_eur,
               counterparty_total_liabilities_date = c.total_liabilities_date,
               money_source = CASE WHEN c.money_source->'fields' ? 'total_liabilities_eur' THEN
                   jsonb_build_object('fields', COALESCE(x.money_source->'fields', '{}'::jsonb)
                       || jsonb_build_object('counterparty_total_liabilities_eur', c.money_source->'fields'->'total_liabilities_eur'))
                   ELSE x.money_source END
          FROM portfolio_entities e, bank_counterparties c
         WHERE e.entity_id = x.entity_id AND c.org_id = e.org_id AND c.counterparty_ref = btrim(e.borrower_entity_id);
        UPDATE ext_banking x
           SET counterparty_total_liabilities_eur = CAST(s->>'eur' AS NUMERIC),
               counterparty_total_liabilities_date = CAST(s->>'date' AS DATE),
               money_source = CASE WHEN s->'source' IS NOT NULL AND s->'source' <> 'null'::jsonb THEN
                   jsonb_build_object('fields', COALESCE(x.money_source->'fields', '{}'::jsonb)
                       || jsonb_build_object('counterparty_total_liabilities_eur', s->'source'))
                   ELSE x.money_source END
          FROM bank_counterparties c, jsonb_array_elements(c.liabilities_conflict) s
         WHERE c.liabilities_conflict IS NOT NULL AND x.entity_id = CAST(s->>'entity_id' AS uuid);
        DROP INDEX IF EXISTS ix_portfolio_entities_borrower;
        DROP TABLE bank_counterparties;
    """)

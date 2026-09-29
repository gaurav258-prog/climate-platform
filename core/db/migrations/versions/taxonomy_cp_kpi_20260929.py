"""EU Taxonomy Art. 8 for credit institutions: six objectives, the exposure's counterparty, and the counterparty's KPIs.

Annex V to Delegated Regulation (EU) 2021/2178 values a general-purpose exposure to an undertaking by that
undertaking's own Taxonomy KPIs — its turnover-based and its CapEx-based aligned shares, per environmental objective —
which is why Annex VI is disclosed twice (turnover-based and CapEx-based). So:

  * ext_banking.taxonomy_objective takes all six objectives of Regulation (EU) 2020/852 Art. 9 (ccm, cca, wtr, ce, ppc,
    bio — data/reference/taxonomy/environmental_objectives.json), not only the two climate ones
  * ext_banking.counterparty_issuer_id links an exposure to its counterparty in the shared issuer reference (by LEI)
  * issuer_taxonomy_kpi holds an undertaking's own KPIs per reporting year, basis (turnover / capex / opex) and
    objective: eligible, aligned, transitional and enabling shares (%), as stated by the client (org-scoped, like the
    other issuer facts)

Revision ID: taxonomy_cp_kpi_20260929
Revises: filing_withdrawn_20260929
"""
from typing import Sequence, Union

from alembic import op

revision: str = "taxonomy_cp_kpi_20260929"
down_revision: Union[str, None] = "filing_withdrawn_20260929"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SIX = ("ccm", "cca", "wtr", "ce", "ppc", "bio")      # Regulation (EU) 2020/852 Art. 9 (a)-(f), frozen here
_TWO = ("ccm", "cca")                                 # the check as bank_gar_facts_20260929 defined it


def _objective_check(values: tuple) -> str:
    return (f"ALTER TABLE ext_banking ADD CONSTRAINT ck_ext_banking_taxonomy_objective "
            f"CHECK (taxonomy_objective IN ({', '.join(repr(v) for v in values)}))")


# A row the pre-migration shape cannot hold: scripts/check_migration_roundtrip.py plants it and requires the downgrade
# to refuse, leaving the schema untouched (every refusing downgrade must carry one).
REFUSAL_PROBE = {
    "setup": """INSERT INTO organizations (org_id, name, type, country) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee1', 'refusal probe', 'bank', 'DE');
                INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, primary_value_eur)
                VALUES ('0bbe0bbe-0000-4000-8000-00000000fee3', '0bbe0bbe-0000-4000-8000-00000000fee1', 'banking', 'refusal probe', 1);
                INSERT INTO ext_banking (entity_id, taxonomy_objective) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee3', 'wtr');""",
    "cleanup": """DELETE FROM ext_banking WHERE entity_id = '0bbe0bbe-0000-4000-8000-00000000fee3';
                  DELETE FROM portfolio_entities WHERE entity_id = '0bbe0bbe-0000-4000-8000-00000000fee3';
                  DELETE FROM organizations WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee1';""",
}


def upgrade() -> None:
    op.execute("ALTER TABLE ext_banking DROP CONSTRAINT IF EXISTS ck_ext_banking_taxonomy_objective")
    op.execute(_objective_check(_SIX))
    op.execute("ALTER TABLE ext_banking ADD COLUMN IF NOT EXISTS counterparty_issuer_id UUID REFERENCES issuers(issuer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ext_banking_counterparty_issuer ON ext_banking (counterparty_issuer_id)")
    op.execute(f"""
        CREATE TABLE issuer_taxonomy_kpi (
            kpi_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            issuer_id         UUID NOT NULL REFERENCES issuers(issuer_id) ON DELETE CASCADE,
            org_id            UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            reporting_year    INTEGER NOT NULL CHECK (reporting_year BETWEEN 2021 AND 2100),
            basis             TEXT NOT NULL CHECK (basis IN ('turnover', 'capex', 'opex')),
            objective         TEXT NOT NULL CHECK (objective IN ({', '.join(repr(v) for v in _SIX)})),
            eligible_pct      NUMERIC(7,4) CHECK (eligible_pct BETWEEN 0 AND 100),
            aligned_pct       NUMERIC(7,4) CHECK (aligned_pct BETWEEN 0 AND 100),
            transitional_pct  NUMERIC(7,4) CHECK (transitional_pct BETWEEN 0 AND 100),
            enabling_pct      NUMERIC(7,4) CHECK (enabling_pct BETWEEN 0 AND 100),
            source            TEXT NOT NULL DEFAULT 'client',
            data_vintage      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_issuer_taxonomy_kpi_parts CHECK (
                aligned_pct IS NULL OR eligible_pct IS NULL OR aligned_pct <= eligible_pct),
            CONSTRAINT ck_issuer_taxonomy_kpi_of_aligned CHECK (
                aligned_pct IS NULL OR (COALESCE(transitional_pct, 0) <= aligned_pct AND COALESCE(enabling_pct, 0) <= aligned_pct)),
            CONSTRAINT ux_issuer_taxonomy_kpi UNIQUE (issuer_id, org_id, reporting_year, basis, objective)
        )""")
    op.execute("CREATE INDEX ix_issuer_taxonomy_kpi_org ON issuer_taxonomy_kpi (org_id, reporting_year)")


def downgrade() -> None:
    # the prior check holds only ccm / cca — refuse rather than silently clear the other four objectives
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM ext_banking WHERE taxonomy_objective NOT IN ({', '.join(repr(v) for v in _TWO)})) THEN
                RAISE EXCEPTION 'cannot downgrade taxonomy_cp_kpi_20260929: exposures state objectives other than '
                                'ccm / cca, which the prior check does not allow — resolve them first';
            END IF;
        END $$;
    """)
    op.execute("DROP TABLE IF EXISTS issuer_taxonomy_kpi")
    op.execute("DROP INDEX IF EXISTS ix_ext_banking_counterparty_issuer")
    op.execute("ALTER TABLE ext_banking DROP COLUMN IF EXISTS counterparty_issuer_id")
    op.execute("ALTER TABLE ext_banking DROP CONSTRAINT IF EXISTS ck_ext_banking_taxonomy_objective")
    op.execute(_objective_check(_TWO))

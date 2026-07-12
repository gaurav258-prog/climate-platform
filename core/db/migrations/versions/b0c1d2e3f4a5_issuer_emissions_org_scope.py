"""issuer_emissions_org_scope

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-07-12

Let customers supply the issuer data they already hold (revenue + scope 1/2/3
emissions) so more of the SFDR PAI statement can be computed instead of gap-
flagged. That data is the CLIENT'S private disclosure: two managers can hold the
same issuer and legitimately carry different figures/vintages, so client-
supplied emissions must be org-scoped, not written to a single global row every
tenant shares.

Model:
  * org_id NULL  → a global/estimated figure (our own or a public source), the
    fallback everyone can use.
  * org_id set   → that org's private disclosure, visible only to that org and
    preferred over the global fallback for that org's funds.

NACE/sector stays a global fact on issuers (a company's industry doesn't differ
by who holds it), enriched only when currently unknown — never clobbered.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, None] = "a9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
ALTER TABLE issuer_emissions
    ADD COLUMN org_id UUID REFERENCES organizations(org_id) ON DELETE CASCADE;

-- 'client' = supplied by the holder itself (distinct from a public 'disclosed').
ALTER TABLE issuer_emissions DROP CONSTRAINT issuer_emissions_source_check;
ALTER TABLE issuer_emissions ADD CONSTRAINT issuer_emissions_source_check
    CHECK (source IN ('disclosed','estimated','cdp','vendor','client'));

-- Replace the single global uniqueness with org-aware uniqueness: one global row
-- per (issuer, year, source), and one row per org for the same key.
ALTER TABLE issuer_emissions DROP CONSTRAINT issuer_emissions_issuer_id_reporting_year_source_key;
CREATE UNIQUE INDEX ux_emissions_global ON issuer_emissions (issuer_id, reporting_year, source)
    WHERE org_id IS NULL;
CREATE UNIQUE INDEX ux_emissions_org ON issuer_emissions (issuer_id, reporting_year, source, org_id)
    WHERE org_id IS NOT NULL;
CREATE INDEX ix_emissions_org ON issuer_emissions (org_id);
"""

DOWNGRADE = """
DROP INDEX IF EXISTS ix_emissions_org;
DROP INDEX IF EXISTS ux_emissions_org;
DROP INDEX IF EXISTS ux_emissions_global;
ALTER TABLE issuer_emissions ADD CONSTRAINT issuer_emissions_issuer_id_reporting_year_source_key
    UNIQUE (issuer_id, reporting_year, source);
ALTER TABLE issuer_emissions DROP CONSTRAINT issuer_emissions_source_check;
ALTER TABLE issuer_emissions ADD CONSTRAINT issuer_emissions_source_check
    CHECK (source IN ('disclosed','estimated','cdp','vendor'));
ALTER TABLE issuer_emissions DROP COLUMN org_id;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)

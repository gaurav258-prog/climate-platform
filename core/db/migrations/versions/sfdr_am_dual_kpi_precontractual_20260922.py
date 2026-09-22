"""asset-manager: dual Taxonomy KPI (turnover + CapEx) + SFDR pre-contractual declared store

Revision ID: sfdr_am_dual_kpi_precontractual_20260922
Revises: d9d0702196df
Create Date: 2026-09-22

Two independent audit passes confirmed two asset-manager SFDR/Taxonomy gaps:

1. Dual Taxonomy KPI. Annex III/IV of Del. Reg. (EU) 2021/2178 require a TURNOVER-based
   and a CapEx-based Taxonomy-aligned % shown side by side — never blended into one
   figure. `issuer_esg_metrics.taxonomy_aligned_pct` already holds the issuer's reported
   Article-8 figure "% of revenue" (see taxonomy_align_20260712_issuer_taxonomy.py's own
   docstring and every caller: sfdr_pai.py, sfdr_xbrl.py, sfdr_periodic.py, funds.py,
   vendor_ingest.py) — i.e. it is already the TURNOVER KPI, just ambiguously named. Renaming
   it would break every one of those callers for no benefit, so instead of a rename we
   add the missing CapEx column and deprecate the ambiguous name in a comment only.

2. Pre-contractual disclosure (RTS Annex II / III) does not exist anywhere in the schema.
   It needs fund-level, manager-authored narrative/forward-commitment fields (investment
   strategy, proportion-of-investments-planned %, DNSH methodology, benchmark, etc.) —
   the same "org-level qualitative JSONB, filled by the customer, never fabricated" idiom
   already used for organizations.sfdr_narratives and Pillar 3 Template 10, but scoped to
   the FUND (the pre-contractual template is per-product, not per-manager).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sfdr_am_dualkpi_precon_20260922"
down_revision: Union[str, None] = "d9d0702196df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE issuer_esg_metrics
            ADD COLUMN taxonomy_aligned_capex_pct NUMERIC(6,3);
        COMMENT ON COLUMN issuer_esg_metrics.taxonomy_aligned_pct IS
            'DEPRECATED ambiguous name — this is the TURNOVER-based Taxonomy-aligned %% '
            '(issuer-reported, Article 8 of Reg. (EU) 2020/852). Kept as-is (not renamed) '
            'because every existing caller depends on this exact column name; read it as '
            'taxonomy_aligned_turnover_pct. See taxonomy_aligned_capex_pct for the CapEx KPI.';
        COMMENT ON COLUMN issuer_esg_metrics.taxonomy_aligned_capex_pct IS
            'CapEx-based Taxonomy-aligned %% (issuer-reported, Article 8 of Reg. (EU) '
            '2020/852) — the companion KPI to taxonomy_aligned_pct (turnover-based). '
            'Annex III/IV of Del. Reg. (EU) 2021/2178 require both shown side by side.';
    """)
    op.execute("ALTER TABLE funds ADD COLUMN sfdr_precontractual JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE funds DROP COLUMN IF EXISTS sfdr_precontractual")
    op.execute("""
        ALTER TABLE issuer_esg_metrics
            DROP COLUMN IF EXISTS taxonomy_aligned_capex_pct;
    """)

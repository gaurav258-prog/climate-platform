"""ext_banking.residual_maturity_years — the loan-tape input that enables maturity-matched expected loss.

Residual maturity (remaining life of the loan, in years) is bank-fed from the loan tape — the same integrated
input the Pillar 3 Template 5 maturity columns need. Nullable: absent it, the expected-loss engine falls back to
a disclosed default tenor and flags the source as 'assumed'. Demo books are seeded with a spread of tenors so
maturity-matching is visible; a real deployment overwrites these from the loan tape.

Revision ID: bank_residual_maturity_202608
Revises: p3esg_qualitative_202608
"""
from alembic import op

revision = "bank_residual_maturity_202608"
down_revision = "p3esg_qualitative_202608"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ext_banking ADD COLUMN IF NOT EXISTS residual_maturity_years NUMERIC(5,2)")
    # Demo seed only: a deterministic spread of tenors (2–12y) so maturity-matching is demonstrable. Keyed off
    # the entity_id hash so it's stable across runs; a real loan tape overwrites it. Leaves any already-set value.
    op.execute("""
        UPDATE ext_banking
        SET residual_maturity_years = 2 + (('x' || substr(md5(entity_id::text), 1, 4))::bit(16)::int % 11)
        WHERE residual_maturity_years IS NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE ext_banking DROP COLUMN IF EXISTS residual_maturity_years")
